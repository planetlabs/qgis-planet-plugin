import os

from planet_explorer import pe_utils


def patch_iface():
    pe_utils.iface.messageTimeout.return_value = 5


def get_testing_credentials():
    return os.environ["PLANET_USER"], os.environ["PLANET_PASSWORD"]
