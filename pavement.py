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

from pathlib import Path
from dataclasses import dataclass
import httpx

import datetime as dt

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
            version = "".join(
                c for c in options.package.version if c.isdigit() or c == "."
            )
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


@dataclass
class GithubRelease:
    """
    Class for defining plugin releases details.
    """
    pre_release: bool
    tag_name: str
    url: str
    published_at: dt.datetime


@task
def generate_plugin_repo_xml():
    """ Generates the plugin repository xml file, from which users
        can use to install the plugin in QGIS.

    :param context: Application context
    :type context: typer.Context
   """
    repo_base_dir = Path(__file__).parent.resolve() / "docs" / "repository"
    repo_base_dir.mkdir(parents=True, exist_ok=True)

    metadata_filename = os.path.join(
        os.path.dirname(__file__), "planet_explorer", "metadata.txt"
    )
    metadata = SafeConfigParser()
    metadata.optionxform = str
    metadata.read(metadata_filename)

    fragment_template = """
            <pyqgis_plugin name="{name}" version="{version}">
                <description><![CDATA[{description}]]></description>
                <about><![CDATA[{about}]]></about>
                <version>{version}</version>
                <qgis_minimum_version>{qgis_minimum_version}</qgis_minimum_version>
                <homepage><![CDATA[{homepage}]]></homepage>
                <file_name>{filename}</file_name>
                <icon>{icon}</icon>
                <author_name><![CDATA[{author}]]></author_name>
                <download_url>{download_url}</download_url>
                <update_date>{update_date}</update_date>
                <experimental>{experimental}</experimental>
                <deprecated>{deprecated}</deprecated>
                <tracker><![CDATA[{tracker}]]></tracker>
                <repository><![CDATA[{repository}]]></repository>
                <tags><![CDATA[{tags}]]></tags>
                <server>False</server>
            </pyqgis_plugin>
    """.strip()
    contents = "<?xml version = '1.0' encoding = 'UTF-8'?>\n<plugins>"
    all_releases = _get_existing_releases()
    for release in [r for r in _get_latest_releases(all_releases) if r is not None]:
        tag_name = release.tag_name
        fragment = fragment_template.format(
            name=metadata.get("general", "name"),
            version=tag_name.replace("v", ""),
            description=metadata.get("general", "description"),
            about=metadata.get("general", "about"),
            qgis_minimum_version=metadata.get("general", "qgisMinimumVersion"),
            homepage=metadata.get("general", "homepage"),
            filename=release.url.rpartition("/")[-1],
            icon=metadata.get("general", "icon"),
            author=metadata.get("general", "author"),
            download_url=release.url,
            update_date=release.published_at,
            experimental=release.pre_release,
            deprecated=metadata.get("general", "deprecated"),
            tracker=metadata.get("general", "tracker"),
            repository=metadata.get("general", "repository"),
            tags=metadata.get("general", "tags"),
        )
        contents = "\n".join((contents, fragment))
    contents = "\n".join((contents, "</plugins>"))
    repo_index = repo_base_dir / "plugins.xml"
    repo_index.write_text(contents, encoding="utf-8")

    return contents


def _get_existing_releases():
    """ Gets the existing plugin releases in  available in the Github repository.

    :param context: Application context
    :type context: typer.Context

    :returns: List of github releases
    :rtype: List[GithubRelease]
    """
    base_url = "https://api.github.com/repos/" \
               "samweli/qgis-planet-plugin/releases"
    response = httpx.get(base_url)
    result = []
    if response.status_code == 200:
        payload = response.json()
        for release in payload:
            for asset in release["assets"]:
                if '.zip' in asset.get("name"):
                    zip_download_url = asset.get("browser_download_url")
                    break
            else:
                zip_download_url = None
            if zip_download_url is not None:
                result.append(
                    GithubRelease(
                        pre_release=release.get("prerelease", True),
                        tag_name=release.get("tag_name"),
                        url=zip_download_url,
                        published_at=dt.datetime.strptime(
                            release["published_at"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    )
                )
    return result


def _get_latest_releases(
        current_releases
):
    """ Searches for the latest plugin releases from the Github plugin releases.

    :param current_releases: Existing plugin releases
     available in the Github repository.
    :type current_releases: list

    :returns: Tuple containing the latest stable and experimental releases
    :rtype: tuple
    """
    latest_experimental = None
    latest_stable = None
    for release in current_releases:
        if release.pre_release:
            if latest_experimental is not None:
                if release.published_at > latest_experimental.published_at:
                    latest_experimental = release
            else:
                latest_experimental = release
        else:
            if latest_stable is not None:
                if release.published_at > latest_stable.published_at:
                    latest_stable = release
            else:
                latest_stable = release
    return latest_stable, latest_experimental

