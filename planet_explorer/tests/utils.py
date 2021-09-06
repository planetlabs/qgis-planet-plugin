from qgis import utils


class QgisInterfaceDummy(object):
    def __getattr__(self, name):
        # return an function that accepts any arguments and does nothing
        def dummy(*args, **kwargs):
            return None
        return dummy


def set_dummy_iface():
    utils.iface = QgisInterfaceDummy()
