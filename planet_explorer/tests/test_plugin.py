import requests
from urllib.parse import urljoin
from planet_explorer.tests.utils import get_recent_release_from_changelog

import xml.etree.ElementTree as ET

REPO_URL = "https://api.github.com/repos/planetlabs/qgis-planet-plugin/"

CUSTOM_REPOSITORY_URL = (
    "https://raw.githubusercontent.com/planetlabs/qgis-planet-plugin"
    "/release/docs/repository/plugins.xml"
)


def test_import_planet():
    try:
        import planet  # noqa: F401

        assert True
    except ImportError:
        assert False


def test_changelog_up_to_date(request):
    """
    Verifies:
        - PLQGIS-TC19
    """
    root_dir = request.config.rootdir
    if root_dir.basename == "tests":
        root_dir = root_dir / ".." / ".."
    most_recent_release_on_github = requests.get(
        urljoin(REPO_URL, "releases?per_page=1")
    ).json()[0]["name"]
    most_recent_release_in_changelog = get_recent_release_from_changelog(root_dir)
    assert (
        most_recent_release_in_changelog == most_recent_release_on_github
    ), "Release on Github does not match the most recent changelog entry!"


def test_plugin_repository_content():
    repo_content_resp = requests.get(CUSTOM_REPOSITORY_URL)

    assert repo_content_resp.status_code == 200

    root = ET.fromstring(repo_content_resp.text)
    plugin = root.find("pyqgis_plugin")

    assert plugin is not None
    assert plugin.find("qgis_minimum_version").text == "3.10"
    assert plugin.find("icon").text == "resources/planet-logo-p.png"

    assert (
        plugin.find("homepage").text
        == "https://developers.planet.com/docs/integrations/qgis/"
    )
    assert (
        plugin.find("repository").text
        == "https://github.com/planetlabs/qgis-planet-plugin"
    )
    assert (
        plugin.find("tracker").text
        == "https://github.com/planetlabs/qgis-planet-plugin/issues"
    )
    assert plugin.find("tags").text == "landsat, raster, analytics, remote sensing"

    assert plugin.find("file_name").text is not None
    assert plugin.find("version") is not None
    assert plugin.find("experimental") is not None
    assert plugin.find("deprecated") is not None
    assert plugin.find("about") is not None
    assert plugin.find("description") is not None
