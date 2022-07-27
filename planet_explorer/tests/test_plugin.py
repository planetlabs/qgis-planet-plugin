import requests
from urllib.parse import urljoin
from planet_explorer.tests.utils import get_recent_release_from_changelog

REPO_URL = "https://api.github.com/repos/planetlabs/qgis-planet-plugin/"


def test_import_planet():
    try:
        import planet  # noqa: F401

        assert True
    except ImportError:
        assert False


def test_changelog_up_to_date():
    """
    Verifies:
        - PLQGIS-TC19
    """
    most_recent_release_on_github = requests.get(
        urljoin(REPO_URL, "releases?per_page=1")
    ).json()[0]["name"]
    most_recent_release_in_changelog = get_recent_release_from_changelog()
    assert (
        most_recent_release_in_changelog == most_recent_release_on_github
    ), "Release on Github does not match the most recent changelog entry!"
