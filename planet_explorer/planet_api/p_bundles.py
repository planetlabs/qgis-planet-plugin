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

        with open(self._spec_file, 'r') as fp:
            self._bundles_per_item_types = json.load(fp, object_pairs_hook=OrderedDict)

        self._bundles = OrderedDict()
        for b_it in self._bundles_per_item_types.values():
            for b in b_it:
                self._bundles[b["id"]] = b


    def bundles_per_item_types(self) -> OrderedDict:
        """Get bundles per all item types from cache"""
        return self._bundles_per_item_types

    def bundles_per_item_type(
            self, item_type: str,
            permissions: Optional[List[str]] = None) -> Optional[list]:
        """
        Get bundles per an item type from cache, optionally constrained by
        user's permissions.
        :param item_type: Item type, e.g. PSScene3Band
        :param permissions: List of permissions, e.g. assets.udm2:download
        :return: Dict of bundles or None
        """
        bndls_per_it = [b for b in self._bundles_per_item_types.get(item_type)
                        if b.get("fileType") != "NITF" and b.get("auxiliaryFiles") != "UDM"]

        return bndls_per_it

        #TODO: check permissions
        '''
        if not permissions:
            return bndls_per_it

        bndls_allowed = self.bundles_per_permissions(permissions)
        if not bndls_allowed:
            return bndls_per_it
        constrained_bndls = [b for b in bndls_per_it if b["id"] in bndls_allowed]

        return constrained_bndls
        '''


    def bundles_for_permission(
            self, permission: str, first_found: bool = False) -> List[str]:
        """
        Matches bundles in spec order, i.e. general -> specific.
        Example: matches 'analytic' before 'analytic_udm2'
        :param permission: e.g. assets.analytic_xml:download
        :param first_found: Return a single-item list of first found bundle
        :return: Ordered list of matching bundle names for the given permission
        """
        bundles = []
        match = ITEM_ASSET_DL_REGEX.match(permission)
        if match is None:
            return bundles
        asset = match.group(1)
        for b_k, b_v in self._bundles.items():
            assets = b_v.get('assets', [])
            if asset in assets:
                bundles.append(b_k)
                if first_found:
                    return bundles
        # Remove dup values, but preserve order
        return list(OrderedDict.fromkeys(bundles))

    def bundles_per_permissions(self, permissions: List[str]) -> List[str]:
        """
        :param permissions: List of permissions, e.g. assets.udm2:download
        :return: Sorted list of matching bundle names for given permissions
        """
        bundles_per_perm = []
        if not permissions:
            return bundles_per_perm

        for perm in permissions:
            bs = self.bundles_for_permission(perm)
            for b in bs:
                if b and b not in bundles_per_perm:  # ensure unique
                    bundles_per_perm.append(b)

        return sorted(bundles_per_perm)

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

