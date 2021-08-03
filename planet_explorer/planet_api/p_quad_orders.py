import os
import json
import datetime
import uuid

from qgis.core import (
    QgsApplication
)

from planet.api.models import (
     MosaicQuads
)
from ..pe_utils import (
    orders_download_folder
)

from .p_client import (
    PlanetClient
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
MOSAICS = "mosaics"

ID = "id"
LINKS = "_links"
DOWNLOAD = "download"


def quad_orders():
    if os.path.exists(_quad_orders_file()):
        try:
            orders = []
            with open(_quad_orders_file()) as f:
                definitions = json.load(f)
            for orderdef in definitions:
                if QUADS in orderdef:
                    order = QuadOrder(orderdef[NAME], orderdef[DESCRIPTION],
                                    orderdef[QUADS], orderdef[LOAD_AS_VIRTUAL],
                                    orderdef[DATE])
                else:
                    order = QuadCompleteOrder(orderdef[NAME], orderdef[DESCRIPTION],
                                    orderdef[MOSAICS], orderdef[LOAD_AS_VIRTUAL],
                                    orderdef[DATE])
                orders.append(order)
        except Exception:
            pass # will return an empty array if the file is corrupted
        return orders
    else:
        return []


def _add_order(order):
    all_orders = [order]
    all_orders.extend(quad_orders())
    with open(_quad_orders_file(), "w") as f:
        json.dump(all_orders, f,
            default=lambda x: {k:v for k,v in x.__dict__.items()
                               if not k.startswith("_")})


def create_quad_order_from_quads(name, description, quads, load_as_virtual):
    order = QuadOrder(name, description, quads, load_as_virtual)
    _add_order(order)


def create_quad_order_from_mosaics(name, description, mosaics, load_as_virtual):
    order = QuadCompleteOrder(name, description, mosaics, load_as_virtual)
    _add_order(order)


class QuadOrder():

    def __init__(self, name, description, quads,
                 load_as_virtual, date=None):
        self.quads = quads
        self.load_as_virtual = load_as_virtual
        self.name = name
        self.description = description
        self.date = date or (datetime.date.today().isoformat())
        self._id = uuid.uuid4()

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

    def id(self):
        return self._id

    def numquads(self):
        return sum([len(m) for m in self.quads.values()])


class QuadCompleteOrder(QuadOrder):

    def __init__(self, name, description, mosaics,
                load_as_virtual, date=None):
        self.mosaics = mosaics
        self.load_as_virtual = load_as_virtual
        self.name = name
        self.description = description
        self.date = date or (datetime.datetime.now()
                            .replace(microsecond=0).isoformat())
        self._id = uuid.uuid4()

    def locations(self):
        p_client = PlanetClient.getInstance()
        locations = {}
        for mosaic in self.mosaics:
            json_quads = []
            quads = p_client.get_quads_for_mosaic(mosaic, minimal=True)
            for page in quads.iter():
                json_quads.extend(page.get().get(MosaicQuads.ITEM_KEY))
            locations[mosaic[NAME]] = [(quad[LINKS][DOWNLOAD], quad[ID]) for quad in json_quads]
        return locations

    def id(self):
        return self._id

    def numquads(self):
        return f"{len(self.mosaics)} complete mosaics"