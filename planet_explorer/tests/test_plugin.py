import unittest
from urllib.parse import urljoin

import defusedxml.ElementTree as ET
import requests

from planet_explorer.tests.utils import get_recent_release_from_changelog

REPO_URL = "https://api.github.com/repos/planetlabs/qgis-planet-plugin/"

CUSTOM_REPOSITORY_URL = (
    "https://raw.githubusercontent.com/planetlabs/qgis-planet-plugin"
    "/release/docs/repository/plugins.xml"
)


class TestPlugin(unittest.TestCase):
    def test_import_planet(self):
        try:
            import planet  # noqa: F401

            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import 'planet' module")

    def test_changelog_up_to_date(self):
        """
        Verifies:
            - PLQGIS-TC19
        """
        # This test assumes pytest's request fixture is not used.
        # You may need to adapt root_dir for your environment.
        import pathlib

        root_dir = pathlib.Path(__file__).parent.parent.parent
        if root_dir.name == "tests":
            root_dir = root_dir.parent.parent
        most_recent_release_on_github = requests.get(
            urljoin(REPO_URL, "releases?per_page=1"), timeout=10
        ).json()[0]["name"]
        most_recent_release_in_changelog = get_recent_release_from_changelog(root_dir)
        self.assertEqual(
            most_recent_release_in_changelog,
            most_recent_release_on_github,
            "Release on Github does not match the most recent changelog entry!",
        )

    def test_plugin_repository_content(self):
        repo_content_resp = requests.get(CUSTOM_REPOSITORY_URL, timeout=10)
        self.assertEqual(repo_content_resp.status_code, 200)

        root = ET.fromstring(repo_content_resp.text)
        plugin = root.find("pyqgis_plugin")

        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.find("qgis_minimum_version").text, "3.10")
        self.assertEqual(plugin.find("icon").text, "resources/planet-logo-p.png")
        self.assertEqual(
            plugin.find("homepage").text,
            "https://developers.planet.com/docs/integrations/qgis/",
        )
        self.assertEqual(
            plugin.find("repository").text,
            "https://github.com/planetlabs/qgis-planet-plugin",
        )
        self.assertEqual(
            plugin.find("tracker").text,
            "https://github.com/planetlabs/qgis-planet-plugin/issues",
        )
        self.assertEqual(
            plugin.find("tags").text, "landsat, raster, analytics, remote sensing"
        )

        self.assertIsNotNone(plugin.find("file_name").text)
        self.assertIsNotNone(plugin.find("version"))
        self.assertIsNotNone(plugin.find("experimental"))
        self.assertIsNotNone(plugin.find("deprecated"))
        self.assertIsNotNone(plugin.find("about"))
        self.assertIsNotNone(plugin.find("description"))
