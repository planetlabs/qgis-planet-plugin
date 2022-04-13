import os

from planet_explorer import pe_utils


def patch_iface():
    pe_utils.iface.messageTimeout.return_value = 5


def test_aoi():
    return (
        '{"coordinates":[[[-0.334369,40.151264],[-0.276291,40.151264],'
        "[-0.276291,40.172081],[-0.334369,40.172081],[-0.334369,40.151264]]]"
        ',"type":"Polygon"}'
    )


def get_testing_credentials():
    if (
        os.environ.get("PLANET_USER") is None
        or os.environ.get("PLANET_PASSWORD") is None
    ):
        raise ValueError(
            "PLANET_USER and PLANET_PASSWORD env vars are undefined! Cannot run tests."
        )
    return os.environ["PLANET_USER"], os.environ["PLANET_PASSWORD"]


def qgis_debug_wait(qtbot, qgis_debug_enabled, wait=1000):
    """Helper function to see what is going on when running tests."""
    if qgis_debug_enabled:
        qtbot.wait(wait)
