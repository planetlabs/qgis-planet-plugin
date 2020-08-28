import os
import json
import datetime

from qgis.core import (
    QgsApplication
)

from ..pe_utils import (
    orders_download_folder
)

class OrderAlreadyExistsException(Exception):
    pass

def _quad_orders_file():
    folder = os.path.join(os.path.dirname(
            QgsApplication.qgisUserDatabaseFilePath()), 
            "planetexplorer")
    os.makedirs(folder, exist_ok = True)
    file = os.path.join(folder, "quadorders.json")
    return file

NAME = "name"
DATE = "date"
QUADS = "quads"
LOAD_AS_VIRTUAL = "load_as_virtual"
DESCRIPTION = "description"

ID = "id"
LINKS = "_links"
DOWNLOAD = "download"

def quad_orders():
    if os.path.exists(_quad_orders_file()):
        with open(_quad_orders_file()) as f: 
            definitions = json.load(f)
        orders = []
        for orderdef in definitions:
            order = QuadOrder(orderdef[NAME], orderdef[DESCRIPTION], 
                                orderdef[QUADS], orderdef[LOAD_AS_VIRTUAL],
                                orderdef[DATE])
            orders.append(order)
        return orders
    else:
        return []

def create_quad_order_from_quads(name, description, quads, load_as_virtual):
    order = QuadOrder(name, description, quads, load_as_virtual)
    all_orders = [order]
    all_orders.extend(quad_orders())
    with open(_quad_orders_file(), "w") as f:
        json.dump(all_orders, f, default=lambda x: x.__dict__)

class QuadOrder():

    def __init__(self, name, description, quads, 
                load_as_virtual, date=None):
        self.quads = quads 
        self.load_as_virtual = load_as_virtual
        self.name = name
        self.description = description
        self.date = date or (datetime.datetime.now()
                            .replace(microsecond=0).isoformat())

    def locations(self):
        locations = {}
        for mosaic, mosaicquads in self.quads.items():
            mosaiclocations = []
            for quad in mosaicquads:
                mosaiclocations.append((quad[LINKS][DOWNLOAD], quad[ID]))
            locations[mosaic] = mosaiclocations
        return locations

    def download_folder(self):
        return os.path.join(orders_download_folder(), "basemaps", self.name)

    def downloaded(self):        
        return os.path.exists(self.download_folder())