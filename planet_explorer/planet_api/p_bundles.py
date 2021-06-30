# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_bundles.py
    ---------------------
    Date                 : September 2019
    Copyright            : (C) 2019 Planet Inc, https://planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
__author__ = 'Planet Federal'
__date__ = 'September 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import os
import logging
import json

from builtins import object
from collections import OrderedDict

from typing import (
    Optional,
    List,
    # Tuple,
)

from .p_specs import (
    ITEM_ASSET_DL_REGEX
)


LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)


class PlanetOrdersV2Bundles(object):
    """
    Parses a bundles.json spec for Orders v2, maintaining its bundle order,
    and provides views and functions into the relationships between bundles,
    item types, assets and user permissions.
    """

    def __init__(self, bundles_spec_file):

        self._spec_file = bundles_spec_file

        if not os.path.exists(self._spec_file):
            log.debug(f'Bundles file does not exist:\n{self._spec_file}')
            return

        print(1)
        with open(self._spec_file, 'r', encoding="utf-8") as fp:
            self._bundles_per_item_types = json.load(fp, object_pairs_hook=OrderedDict)

        self._bundles = OrderedDict()
        for b_it in self._bundles_per_item_types.values():
            for b in b_it:
                self._bundles[b["id"]] = b


    def bundles_for_item_type(
            self, item_type: str,
            permissions: List[List[str]]) -> Optional[list]:
        """
        Get bundles per an item type from cache, optionally constrained by
        user's permissions.
        :param item_type: Item type, e.g. PSScene3Band
        :param permissions: List of permissions, e.g. assets.udm2:download
        :return: Dict of bundles or None
        """
        bndls_per_it = [b for b in self._bundles_per_item_types.get(item_type)
                        if b.get("fileType") != "NITF" and b.get("auxiliaryFiles") != "UDM"]


        permissions_cleaned = []
        for img_permissions in permissions:
            img_permissions_cleaned = []
            for p in img_permissions:
                match = ITEM_ASSET_DL_REGEX.match(p)
                if match is not None:
                    img_permissions_cleaned.append(match.group(1))
            permissions_cleaned.append(img_permissions_cleaned)

        bndls_allowed = []
        for b in bndls_per_it:
            add_bundle = True
            assets = b.get('assets', [])
            for asset in assets:
                for img_permissions in permissions_cleaned:
                    if asset not in img_permissions:
                        add_bundle = False
            if add_bundle:
                bndls_allowed.append(b)

        return bndls_allowed

    def item_default_bundle_name(self, item_type: str) -> str:
        return self.default_bundles().get(item_type, '')

    @staticmethod
    def default_bundles():
        return {
            'PSScene4Band': 'analytic_sr_udm2',
            'PSScene3Band': 'visual',
            'REOrthoTile': 'analytic_sr_udm2',
            'SkySatCollect': 'pansharpened_udm2',
            'Landsat8L1G': 'analytic',
            'SkySatScene': 'pansharpened_udm2',
            'REScene': 'basic_analytic',
            'Sentinel2L1C': 'analytic',
            'PSOrthoTile': 'analytic_sr_udm2',
        }

