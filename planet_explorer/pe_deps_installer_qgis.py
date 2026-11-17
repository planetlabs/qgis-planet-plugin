# -*- coding: utf-8 -*-
"""
***************************************************************************
    pe_deps_installer_qgis.py
    -------------------------
    Date                 : July 2026
    Copyright            : (C) 2026 Planet Inc, https://planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = "Planet Federal"
__date__ = "July 2026"
__copyright__ = "(C) 2026 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import importlib.metadata
import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

from qgis.PyQt.QtCore import QEventLoop, Qt, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
)

LOG_LEVEL = os.environ.get("PYTHON_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)


def is_nixos() -> bool:
    try:
        info = platform.freedesktop_os_release()
        return info.get("ID") == "nixos"
    except (AttributeError, OSError):
        # Fallback for non-Linux OSs or standard library limitations
        return False


def is_flatpak() -> bool:
    return os.environ.get("FLATPAK_ID") == "org.qgis.qgis"


class PipMissingDialog(QDialog):
    """
    Dialog shown when pip is missing in QGIS's Python environment
    """

    def __init__(self, python_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("pip not available")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(420)
        self.setMinimumHeight(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        if is_nixos() and not is_flatpak():
            install_helper = (
                "QGIS on NixOS requires pip to be installed as an extra python package. "
                "See https://qgis.org/resources/installation-guide/#running-with-extra-python-packages"
            )
        elif is_flatpak():
            install_helper = (
                "To enable pip in QGIS Flatpak, run this command in your system terminal:\n\n"
                "<code>flatpak run --command=python3 org.qgis.qgis -m ensurepip --default-pip --user</code>"
            )
        else:
            install_helper = ""

        label = QLabel(
            "This plugin needs to install additional Python packages, "
            "but pip is not available in QGIS's Python environment:\n"
            f"{python_path}\n\n"
            "Please enable or install pip for this Python environment, "
            "then click Retry. \n\n"
            f"{install_helper}"
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Retry
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Retry).clicked.connect(
            self.accept
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class DependencyNoticeDialog(QDialog):
    """
    Dialog shown when additional dependencies are
    required in QGIS's Python environment.
    """

    def __init__(self, missing: list[str], parent=None, extlibs: Path = None):
        super().__init__(parent)
        self.setWindowTitle("Additional dependencies required")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(420)
        self.setMinimumHeight(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        extlibs_display = extlibs or "the plugin's dependency folder"
        if isinstance(extlibs_display, Path):
            extlibs_display = str(extlibs_display)
        label = QLabel(
            "This plugin requires the following Python packages, "
            "which are currently not installed in:\n"
            f"{extlibs_display}:"
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        list_widget = QListWidget()
        list_widget.addItems(missing)
        list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        row_height = list_widget.sizeHintForRow(0) if list_widget.count() else 20
        visible_rows = min(list_widget.count(), 6)
        list_widget.setFixedHeight(row_height * visible_rows + 10)
        layout.addWidget(list_widget)

        note = QLabel(
            f"Click OK to install them now. \n"
            f"The packages will be installed into the folder {extlibs_display}. \n"
            "This may take a few minutes depending on your connection."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class PipInstallWorker(QThread):
    """Worker thread for installing Python packages using pip."""

    progress = pyqtSignal(int, str)  # step index, message
    finished_ok = pyqtSignal()
    finished_err = pyqtSignal(str)
    pip_missing = pyqtSignal(str)

    def __init__(self, extlibs: str, reqs: list[str], parent=None):
        super().__init__(parent)
        self.extlibs = extlibs
        self.reqs = reqs
        self.creation_flags = self.get_creation_flags()

    def get_creation_flags(self):
        if platform.system() == "Windows":
            return subprocess.CREATE_NO_WINDOW
        else:
            return 0

    def get_python_path(self):
        # Derived from qpip

        # python is normally found at sys.executable,
        # but there is an issue on windows qgis so use 'python'
        # instead: https://github.com/qgis/QGIS/issues/45646
        # 'python' doesnt seem to work, using this method instead
        if platform.system() == "Windows":
            python_dir = Path(sys.prefix)
            for file in ["python.exe", "python3.exe"]:
                python_path = python_dir / file
                if python_path.is_file():
                    log.info(f"Attempt Windows install at {str(python_path)}")
                    return str(python_path)

            python_dir = Path(sys.executable).parent
            for file in ["python.exe", "python3.exe"]:
                python_path = python_dir / file
                if python_path.is_file():
                    log.info(f"Attempting Windows install at {str(python_path)}")
                    return str(python_path)

        # Same bug on mac as windows:
        # https://github.com/opengisch/qpip/issues/34#issuecomment-2995221985
        if platform.system() == "Darwin":  # Mac
            base_paths = [
                Path(sys.prefix),
                Path(sys.prefix) / "bin",
                Path(sys.executable).parent,
            ]
            for base_path in base_paths:
                for file in ["python", "python3"]:
                    path = base_path / file
                    if path.is_file():
                        log.info(f"Attempt MacOS install at {str(path)}")
                        return str(path)
            path = sys.executable
            log.info(f"Attempt MacOS install at {str(path)}")
            return path

        else:  # Fallback attempt
            path = sys.executable
            log.info(f"Attempt fallback install at {str(path)}")
            return path

    def check_pip_available(self, python_path: str) -> bool:

        check = subprocess.run(
            [python_path, "-m", "pip", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=self.creation_flags,
        )  # nosec B603 -- args passed as list,
        # no shell involved; python_path is derived internally,
        # not user input

        return check.returncode == 0

    def run(self):
        try:
            os.makedirs(self.extlibs, exist_ok=True)
            python_path = self.get_python_path()
            if not self.check_pip_available(python_path):
                self.pip_missing.emit(python_path)
                return

            total = len(self.reqs)
            for i, req in enumerate(self.reqs, start=1):
                self.progress.emit(i, f"Installing {req} ({i}/{total})...")

                cmd = [
                    python_path,
                    "-um",
                    "pip",
                    "install",
                    "--no-deps",
                    "--upgrade",
                    # "--only-binary=:all:",
                    "-t",
                    self.extlibs,
                    req,
                ]

                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=self.creation_flags,
                )  # nosec B603 -- args passed as list, no shell involved;
                # python_path is derived internally, not user input

            self.finished_ok.emit()
        except subprocess.CalledProcessError as e:
            output = e.stdout or str(e)
            self.finished_err.emit(output)
        except Exception as e:
            self.finished_err.emit(str(e))


def read_requirements(file_path: Path) -> list[str]:
    """
    Returns a list of runtime requirements

    Args:
        file_path (Path): File path to the requrements.txt file

    Returns:
        list[str]: A list of runtime requirements
    """
    file_path = Path(file_path).resolve()
    with open(file_path, "r") as f:
        lines = [ln.strip() for ln in f.readlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    return lines


def missing_requirements(requirements: list[str]) -> list[str]:
    """
    Check if the required dependencies are missing.

    Args:
        requirements (list[str]): A list of requirements to check.

    Returns:
        list[str]: A list of missing dependencies.
    """
    if hasattr(importlib.metadata, "invalidate_caches"):
        importlib.metadata.invalidate_caches()

    missing = []
    for req in requirements:
        pkg_name = re.split(r"[<>=!~\[]", req.strip())[0].strip()
        try:
            importlib.metadata.distribution(pkg_name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(req)
    return missing


def _run_install_attempt(extlibs: str, reqs: list[str], parent_widget=None) -> dict:
    """
    Run a single install attempt via PipInstallWorker, blocking until it
    finishes, and report the outcome.

    Args:
        extlibs (str): Target install directory.
        reqs (list[str]): Full requirements to install.
        parent_widget (optional): Parent widget for dialogs. Defaults to None.

    Returns:
        dict: Result dict with keys "ok", "err", "pip_missing", "python_path".
    """
    dlg = QProgressDialog(
        "Preparing dependency installation...", None, 0, len(reqs), parent_widget
    )
    dlg.setWindowTitle("Installing plugin dependencies")
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setCancelButton(None)
    dlg.setValue(0)
    dlg.show()

    loop = QEventLoop()
    result = {"ok": False, "err": "", "pip_missing": False, "python_path": ""}

    worker = PipInstallWorker(extlibs, reqs, parent=dlg)

    def on_progress(step, msg):
        dlg.setLabelText(msg)
        dlg.setValue(step)

    def on_ok():
        dlg.setValue(len(reqs))
        result["ok"] = True
        loop.quit()

    def on_err(err):
        result["ok"] = False
        result["err"] = err
        loop.quit()

    def on_pip_missing(python_path):
        result["pip_missing"] = True
        result["python_path"] = python_path
        loop.quit()

    worker.progress.connect(on_progress)
    worker.finished_ok.connect(on_ok)
    worker.finished_err.connect(on_err)
    worker.pip_missing.connect(on_pip_missing)
    worker.finished.connect(worker.deleteLater)
    worker.start()
    loop.exec()
    dlg.close()

    return result


def ensure_deps_with_dialog(plugin_dir: str, parent_widget=None) -> bool:
    """
    Run the dependency check and installation process with a dialog.

    Args:
        plugin_dir (str): Path to the plugin directory.
        parent_widget (optional): Parent widget for dialogs. Defaults to None.

    Returns:
        bool: True if dependencies are present/installed, False if failed/cancelled.
    """
    plugin_dir = Path(plugin_dir).resolve()
    extlibs = plugin_dir.joinpath("extlibs")
    requirements_file = plugin_dir.joinpath("requirements.txt")

    # Make extlibs importable first (for already-installed local deps)
    if extlibs.is_dir() and str(extlibs) not in sys.path:
        sys.path.insert(0, str(extlibs))

    reqs = read_requirements(requirements_file)
    missing = missing_requirements(reqs)
    if not missing:
        return True

    # If any package is missing do a reinstall of all the
    # requirements.
    notice = DependencyNoticeDialog(reqs, parent_widget, extlibs)
    if notice.exec() != QDialog.DialogCode.Accepted:
        return False  # user cancelled, don't install

    while True:  # allows retry loop after pip is manually enabled
        result = _run_install_attempt(extlibs, reqs, parent_widget)

        if result["ok"]:
            if str(extlibs) not in sys.path:
                sys.path.insert(0, str(extlibs))
            QMessageBox.information(
                parent_widget, "Plugin setup", "Dependencies installed successfully."
            )
            return True

        if result["pip_missing"]:
            pip_dlg = PipMissingDialog(result["python_path"], parent_widget)
            if pip_dlg.exec() == QDialog.DialogCode.Accepted:
                continue  # user clicked Retry
            return False

        QMessageBox.critical(
            parent_widget,
            "Dependency installation failed",
            "Could not install required Python packages.\n\n" f"{result['err'][:1500]}",
        )
        return False
