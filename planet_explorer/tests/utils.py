from qgis.testing import start_app
from qgis import utils


class QgisInterfaceDummy(object):
    def __getattr__(self, name):
        # return an function that accepts any arguments and does nothing
        def dummy(*args, **kwargs):
            return None
        return dummy


if utils.iface is None:
    utils.iface = QgisInterfaceDummy()
    start_app()
