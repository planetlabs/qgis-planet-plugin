-- PLANET nvim project configuration
-- Auto-sourced by nvim when exrc is enabled, or source manually with:
--   :source .nvim.lua

-- Guard against re-sourcing
if vim.g.planet_loaded then
	return
end
vim.g.planet_loaded = true

-- Helper to run commands in a floating terminal
local function float_term(cmd, opts)
	opts = opts or {}
	local buf = vim.api.nvim_create_buf(false, true)
	local width = opts.width or math.floor(vim.o.columns * 0.8)
	local height = opts.height or math.floor(vim.o.lines * 0.8)
	local row = math.floor((vim.o.lines - height) / 2)
	local col = math.floor((vim.o.columns - width) / 2)

	local win = vim.api.nvim_open_win(buf, true, {
		relative = "editor",
		width = width,
		height = height,
		row = row,
		col = col,
		style = "minimal",
		border = "rounded",
		title = opts.title or " Terminal ",
		title_pos = "center",
	})

	if cmd then
		vim.fn.termopen(cmd, {
			on_exit = function(_, exit_code)
				if opts.close_on_success and exit_code == 0 then
					vim.defer_fn(function()
						if vim.api.nvim_win_is_valid(win) then
							vim.api.nvim_win_close(win, true)
						end
					end, 1000)
				end
			end,
		})
	else
		vim.fn.termopen(vim.o.shell)
	end
	vim.cmd("startinsert")
end

-- Helper to open a bottom split terminal tailing the PLANET log file
local function open_log_tail()
	local tmp_dir = os.getenv("TMPDIR") or os.getenv("TMP") or os.getenv("TEMP") or "/tmp"
	local datestamp = os.date("%Y%m%d")
	local log_file = tmp_dir .. "/planet_logfile_" .. datestamp .. ".log"

	-- Check if GEEST_LOG env var is set
	local planet_log_env = os.getenv("GEEST_LOG")
	if planet_log_env and planet_log_env ~= "" and planet_log_env ~= "0" then
		log_file = planet_log_env
	end

	-- Create a horizontal split at the bottom
	vim.cmd("botright 12split")
	local buf = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_win_set_buf(0, buf)
	vim.api.nvim_buf_set_name(buf, "PLANET Log")

	-- Set buffer options
	vim.bo[buf].buftype = "nofile"
	vim.bo[buf].bufhidden = "wipe"
	vim.bo[buf].swapfile = false

	-- Start tailing the log file (create if it doesn't exist)
	vim.fn.termopen(string.format('touch "%s" && tail -f "%s"', log_file, log_file), {
		on_exit = function()
			-- Buffer will be wiped automatically due to bufhidden setting
		end,
	})

	-- Set window title
	vim.wo.winfixheight = true
	vim.wo.statusline = "%#StatusLine# PLANET Log: " .. log_file .. " %="

	-- Return to the previous window
	vim.cmd("wincmd p")
end

-- Helper to launch QGIS with log tail (QGIS runs in background)
local function launch_qgis_with_log(cmd, title)
	-- Open the log tail panel first
	open_log_tail()
	-- Launch QGIS as a background job (not in a terminal)
	vim.fn.jobstart(cmd, {
		detach = true,
		on_exit = function(_, exit_code)
			if exit_code ~= 0 then
				vim.notify(title .. " exited with code " .. exit_code, vim.log.levels.WARN)
			end
		end,
	})
	vim.notify("Started" .. title .. "(background)", vim.log.levels.INFO)
end

-- Project-specific commands
vim.api.nvim_create_user_command("GeestQgis", function()
	launch_qgis_with_log(
		"GEEST_DEBUG=0 GEEST_EXPERIMENTAL=0 RUNNING_ON_LOCAL=1 nix run .#default -- --profile GEEST2",
		" QGIS "
	)
end, { desc = "Launch QGIS (normal mode)" })

vim.api.nvim_create_user_command("GeestQgisDebug", function()
	launch_qgis_with_log(
		"GEEST_DEBUG=1 GEEST_EXPERIMENTAL=0 RUNNING_ON_LOCAL=1 nix run .#default -- --profile GEEST2",
		" QGIS Debug "
	)
end, { desc = "Launch QGIS (debug mode)" })

vim.api.nvim_create_user_command("GeestQgisExperimental", function()
	launch_qgis_with_log(
		"GEEST_DEBUG=0 GEEST_EXPERIMENTAL=1 RUNNING_ON_LOCAL=1 nix run .#default -- --profile GEEST2",
		" QGIS Experimental "
	)
end, { desc = "Launch QGIS (experimental features)" })

vim.api.nvim_create_user_command("GeestQgisLtr", function()
	launch_qgis_with_log("RUNNING_ON_LOCAL=1 nix run .#qgis-ltr", " QGIS LTR ")
end, { desc = "Launch QGIS LTR" })

vim.api.nvim_create_user_command("GeestPrecommit", function()
	float_term("pre-commit run --all-files", { title = " Pre-commit " })
end, { desc = "Run pre-commit checks" })

vim.api.nvim_create_user_command("GeestPrecommitStaged", function()
	float_term("pre-commit run", { title = " Pre-commit (staged) " })
end, { desc = "Run pre-commit on staged files" })

vim.api.nvim_create_user_command("GeestTests", function()
	float_term("./scripts/run-tests.sh", { title = " Tests " })
end, { desc = "Run tests" })

vim.api.nvim_create_user_command("GeestClean", function()
	float_term("./scripts/clean.sh", { title = " Clean " })
end, { desc = "Clean build artifacts" })

vim.api.nvim_create_user_command("GeestRemovePycache", function()
	float_term("./scripts/remove_pycache.sh", { title = " Remove __pycache__ " })
end, { desc = "Remove __pycache__ directories" })

vim.api.nvim_create_user_command("GeestDocstrings", function()
	float_term("./scripts/docstrings_check.sh", { title = " Docstrings Check " })
end, { desc = "Check docstrings" })

vim.api.nvim_create_user_command("GeestEncoding", function()
	float_term("./scripts/encoding_check.sh", { title = " Encoding Check " })
end, { desc = "Check file encodings" })

vim.api.nvim_create_user_command("GeestGource", function()
	float_term("./scripts/gource.sh", { title = " Gource " })
end, { desc = "Run gource visualization" })

vim.api.nvim_create_user_command("GeestCompileStrings", function()
	float_term("./scripts/compile-strings.sh", { title = " Compile Strings " })
end, { desc = "Compile translation strings" })

vim.api.nvim_create_user_command("GeestUpdateStrings", function()
	float_term("./scripts/update-strings.sh", { title = " Update Strings " })
end, { desc = "Update translation strings" })

vim.api.nvim_create_user_command("GeestTerm", function()
	float_term(nil, { title = " Terminal " })
end, { desc = "Open floating terminal" })

vim.api.nvim_create_user_command("GeestLogTail", function()
	open_log_tail()
end, { desc = "Open PLANET log tail panel" })

vim.api.nvim_create_user_command("GeestGitStatus", function()
	float_term('git status && echo "\\n--- Recent commits ---\\n" && git log --oneline -10', { title = " Git Status " })
end, { desc = "Git status and recent commits" })

vim.api.nvim_create_user_command("GeestGitDiff", function()
	float_term("git diff", { title = " Git Diff " })
end, { desc = "Git diff" })

vim.api.nvim_create_user_command("GeestGitLog", function()
	float_term("git log --oneline --graph --decorate -30", { title = " Git Log " })
end, { desc = "Git log (graph)" })

vim.api.nvim_create_user_command("GeestLazygit", function()
	float_term("lazygit", { title = " Lazygit " })
end, { desc = "Open lazygit" })

-- Build & Release commands
vim.api.nvim_create_user_command("GeestBuild", function()
	float_term("python admin.py build", { title = " Build Plugin " })
end, { desc = "Build plugin to build/" })

vim.api.nvim_create_user_command("GeestGenerateZip", function()
	float_term("python admin.py generate-zip", { title = " Generate ZIP " })
end, { desc = "Generate plugin ZIP" })

vim.api.nvim_create_user_command("GeestInstall", function()
	float_term("python admin.py --qgis-profile GEEST2 install", { title = " Install Plugin " })
end, { desc = "Install plugin to QGIS profile" })

vim.api.nvim_create_user_command("GeestUninstall", function()
	float_term("python admin.py --qgis-profile GEEST2 uninstall", { title = " Uninstall Plugin " })
end, { desc = "Uninstall plugin from QGIS profile" })

vim.api.nvim_create_user_command("GeestSymlink", function()
	float_term("python admin.py --qgis-profile GEEST2 symlink", { title = " Symlink Plugin " })
end, { desc = "Symlink plugin to QGIS profile" })

vim.api.nvim_create_user_command("GeestGenerateRepoXml", function()
	float_term("python admin.py generate-plugin-repo-xml", { title = " Generate Repo XML " })
end, { desc = "Generate plugin repository XML" })

vim.api.nvim_create_user_command("GeestBundleDeps", function()
	float_term("python admin.py bundle-deps", { title = " Bundle Dependencies " })
end, { desc = "Bundle vendored dependencies (h3, etc.)" })

vim.api.nvim_create_user_command("GeestCleanExtlibs", function()
	float_term("python admin.py clean-extlibs", { title = " Clean Extlibs " })
end, { desc = "Clean vendored dependencies" })

vim.api.nvim_create_user_command("GeestReleaseDraft", function()
	float_term("gh release create --draft --generate-notes", { title = " Draft Release " })
end, { desc = "Create draft GitHub release" })

vim.api.nvim_create_user_command("GeestReleaseList", function()
	float_term("gh release list", { title = " Releases " })
end, { desc = "List GitHub releases" })

vim.api.nvim_create_user_command("GeestTagList", function()
	float_term("git tag -l --sort=-v:refname | head -20", { title = " Tags " })
end, { desc = "List recent tags" })

vim.api.nvim_create_user_command("GeestTagCreate", function()
	vim.ui.input({ prompt = "Tag version (e.g., v2.0.1): " }, function(tag)
		if tag and tag ~= "" then
			vim.ui.input({ prompt = "Tag message: " }, function(msg)
				if msg and msg ~= "" then
					float_term(
						string.format(
							'git tag -a %s -m "%s" && echo "Tag %s created. Push with: git push origin %s"',
							tag,
							msg,
							tag,
							tag
						),
						{ title = " Create Tag " }
					)
				end
			end)
		end
	end)
end, { desc = "Create annotated tag" })

-- Register with which-key under <leader>p (Project)
local wk_ok, wk = pcall(require, "which-key")
if wk_ok then
	wk.add({
		{ "<leader>p", group = "Project" },
		-- QGIS launchers
		{ "<leader>pq", group = "QGIS" },
		{ "<leader>pqq", "<cmd>GeestQgis<cr>", desc = "Launch QGIS" },
		{ "<leader>pqd", "<cmd>GeestQgisDebug<cr>", desc = "Launch QGIS (debug)" },
		{ "<leader>pqe", "<cmd>GeestQgisExperimental<cr>", desc = "Launch QGIS (experimental)" },
		{ "<leader>pql", "<cmd>GeestQgisLtr<cr>", desc = "Launch QGIS LTR" },
		-- Pre-commit / Quality
		{ "<leader>pc", group = "Checks" },
		{ "<leader>pcc", "<cmd>GeestPrecommit<cr>", desc = "Pre-commit (all files)" },
		{ "<leader>pcs", "<cmd>GeestPrecommitStaged<cr>", desc = "Pre-commit (staged)" },
		{ "<leader>pcd", "<cmd>GeestDocstrings<cr>", desc = "Check docstrings" },
		{ "<leader>pce", "<cmd>GeestEncoding<cr>", desc = "Check encodings" },
		-- Tests
		{ "<leader>pt", "<cmd>GeestTests<cr>", desc = "Run tests" },
		-- Clean
		{ "<leader>px", group = "Clean" },
		{ "<leader>pxc", "<cmd>GeestClean<cr>", desc = "Clean build artifacts" },
		{ "<leader>pxp", "<cmd>GeestRemovePycache<cr>", desc = "Remove __pycache__" },
		-- Translations
		{ "<leader>pi", group = "i18n" },
		{ "<leader>pic", "<cmd>GeestCompileStrings<cr>", desc = "Compile strings" },
		{ "<leader>piu", "<cmd>GeestUpdateStrings<cr>", desc = "Update strings" },
		-- Git
		{ "<leader>pg", group = "Git" },
		{ "<leader>pgs", "<cmd>GeestGitStatus<cr>", desc = "Status + recent commits" },
		{ "<leader>pgd", "<cmd>GeestGitDiff<cr>", desc = "Diff" },
		{ "<leader>pgl", "<cmd>GeestGitLog<cr>", desc = "Log (graph)" },
		{ "<leader>pgg", "<cmd>GeestLazygit<cr>", desc = "Lazygit" },
		-- Build & Package
		{ "<leader>pb", group = "Build" },
		{ "<leader>pbb", "<cmd>GeestBuild<cr>", desc = "Build plugin" },
		{ "<leader>pbz", "<cmd>GeestGenerateZip<cr>", desc = "Generate ZIP" },
		{ "<leader>pbi", "<cmd>GeestInstall<cr>", desc = "Install to QGIS" },
		{ "<leader>pbu", "<cmd>GeestUninstall<cr>", desc = "Uninstall from QGIS" },
		{ "<leader>pbs", "<cmd>GeestSymlink<cr>", desc = "Symlink to QGIS" },
		{ "<leader>pbx", "<cmd>GeestGenerateRepoXml<cr>", desc = "Generate repo XML" },
		{ "<leader>pbd", "<cmd>GeestBundleDeps<cr>", desc = "Bundle dependencies" },
		{ "<leader>pbc", "<cmd>GeestCleanExtlibs<cr>", desc = "Clean extlibs" },
		-- Release
		{ "<leader>pr", group = "Release" },
		{ "<leader>prd", "<cmd>GeestReleaseDraft<cr>", desc = "Draft GitHub release" },
		{ "<leader>prl", "<cmd>GeestReleaseList<cr>", desc = "List releases" },
		{ "<leader>prt", "<cmd>GeestTagList<cr>", desc = "List tags" },
		{ "<leader>prn", "<cmd>GeestTagCreate<cr>", desc = "Create new tag" },
		-- Misc
		{ "<leader>pv", "<cmd>GeestGource<cr>", desc = "Gource visualization" },
		{ "<leader>pp", "<cmd>GeestTerm<cr>", desc = "Floating terminal" },
		{ "<leader>pl", "<cmd>GeestLogTail<cr>", desc = "Tail PLANET log" },
	})
end

vim.notify("PLANET: Project commands and <leader>p menu loaded", vim.log.levels.INFO)
