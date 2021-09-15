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
    return os.environ["PLANET_USER"], os.environ["PLANET_PASSWORD"]
