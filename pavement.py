# -*- coding: utf-8 -*-
"""
***************************************************************************
    pavement.py
    ---------------------
    Date                 : August 2019
    Copyright            : (C) 2019 Planet Inc, https://planet.com
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
__date__ = "August 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import fnmatch
import os
import subprocess
import sys
import zipfile
from configparser import SafeConfigParser
from io import StringIO

from paver.easy import Bunch, cmdopts, error, options, path, task

options(
    plugin=Bunch(
        name="planet_explorer",
        ext_libs=path("planet_explorer/extlibs"),
        ext_src=path("planet_explorer/ext-src"),
        source_dir=path("planet_explorer"),
        package_dir=path("."),
        tests=["test", "tests"],
        excludes=[
            "*.pyc",
            ".git",
            ".DS_Store",
            "bin",
            "pe_options.png",
            "request-result-samples",
            "thumbnails",
            "metadata.txt",
            "qgis_resources.py",
            "pe_analytics.py",
            "pe_utils.py",
        ],
        path_to_settings="Raster --> Planet Explorer --> Settings...",
        # skip certain files inadvertently found by exclude pattern globbing
        skip_exclude=[],
    ),
)


@task
@cmdopts(
    [
        ("clean", "c", "clean out dependencies first"),
    ]
)
def setup():
    clean = getattr(options, "clean", False)
    ext_libs = options.plugin.ext_libs
    if clean:
        ext_libs.rmtree()
    ext_libs.makedirs()
    reqs = read_requirements()
    os.environ["PYTHONPATH"] = ext_libs.abspath()
    for req in reqs:
        try:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--upgrade",
                    "-t",
                    f"{ext_libs.abspath()}",
                    req,
                ]
            )
        except subprocess.CalledProcessError:
            error(f"Error installing {req} with pip.")
            sys.exit(1)


@task
def install(options):
    """install plugin to qgis"""
    plugin_name = options.plugin.name
    src = path(__file__).dirname() / plugin_name
    if os.name == "nt":
        default_profile_plugins = (
            "~/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins"
        )
    elif sys.platform == "darwin":
        default_profile_plugins = (
            "~/Library/Application Support/QGIS/QGIS3"
            "/profiles/default/python/plugins"
        )
    else:
        default_profile_plugins = (
            "~/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
        )

    dst_plugins = path(default_profile_plugins).expanduser()
    if not dst_plugins.exists():
        os.makedirs(dst_plugins, exist_ok=True)
    dst = dst_plugins / plugin_name
    src = src.abspath()
    dst = dst.abspath()
    if not hasattr(os, "symlink"):
        dst.rmtree()
        src.copytree(dst)
    elif not dst.exists():
        src.symlink(dst)


def read_requirements():
    """Return a list of runtime requirements"""
    lines = open("requirements.txt").readlines()
    lines = [l for l in [l.strip() for l in lines] if l]
    return lines


@task
@cmdopts(
    [
        ("tests", "t", "Package tests with plugin"),
        ("segments=", "s", "Segments write key"),
        ("sentry=", "d", "Sentry dns"),
        ("version=", "v", "Plugin version number"),
    ]
)
def package(options):
    """Create plugin package"""
    package_file = options.plugin.package_dir / ("%s.zip" % options.plugin.name)
    if os.path.exists(package_file):
        os.remove(package_file)
    with zipfile.ZipFile(package_file, "w", zipfile.ZIP_DEFLATED) as zf:
        if not hasattr(options.package, "tests"):
            options.plugin.excludes.extend(options.plugin.tests)
        _make_zip(zf, options)


def _make_zip(zipfile, options):
    excludes = set(options.plugin.excludes)
    skips = options.plugin.skip_exclude

    src_dir = options.plugin.source_dir

    exclude = lambda p: any([fnmatch.fnmatch(p, e) for e in excludes])

    def filter_excludes(some_files):
        if not some_files:
            return []
        # to prevent descending into dirs, modify the list in place
        for i in range(len(some_files) - 1, -1, -1):
            some_f = some_files[i]
            if exclude(some_f) and some_f not in skips:
                some_files.remove(some_f)
        return some_files

    for root, dirs, files in os.walk(src_dir):
        for f in filter_excludes(files):
            relpath = os.path.relpath(root, ".")
            zipfile.write(path(root) / f, path(relpath) / f)
        filter_excludes(dirs)

    analytics_filename = os.path.join(
        os.path.dirname(__file__), "planet_explorer", "pe_analytics.py"
    )
    with open(analytics_filename) as f:
        txt = f.read()
        if hasattr(options.package, "segments"):
            txt = txt.replace(
                "# [set_segments_write_key]",
                f"os.environ['SEGMENTS_WRITE_KEY'] = '{options.package.segments}'",
            )
        else:
            print("WARNING: No Segments write key provided.")
        if hasattr(options.package, "sentry"):
            txt = txt.replace(
                "# [set_sentry_dsn]",
                f"os.environ['SENTRY_DSN'] = '{options.package.sentry}'",
            )
        else:
            print("WARNING: No Sentry DSN write key provided.")

        zipfile.writestr("planet_explorer/pe_analytics.py", txt)

    metadata_filename = os.path.join(
        os.path.dirname(__file__), "planet_explorer", "metadata.txt"
    )
    cfg = SafeConfigParser()
    cfg.optionxform = str
    cfg.read(metadata_filename)

    if hasattr(options.package, "version"):
        if options.package.version.startswith("v"):
            version = "".join(c for c in options.package.version if c.isdigit() or c == ".")
        else:
            version = f"{cfg.get('general', 'version')}-{options.package.version}"
        cfg.set("general", "version", version)
    buf = StringIO()
    cfg.write(buf)
    zipfile.writestr("planet_explorer/metadata.txt", buf.getvalue())

    utils_filename = os.path.join(
        os.path.dirname(__file__), "planet_explorer", "pe_utils.py"
    )
    with open(utils_filename) as f:
        txt = f.read()
        commitid = (
            subprocess.check_output(["git", "rev-parse", "HEAD"])
            .decode("utf-8")
            .strip()
        )
        txt = txt.replace(
            'COMMIT_ID = ""',
            f'COMMIT_ID = "{commitid}"',
        )

        zipfile.writestr("planet_explorer/pe_utils.py", txt)
