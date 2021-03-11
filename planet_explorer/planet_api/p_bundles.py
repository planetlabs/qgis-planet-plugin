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
import re

from builtins import object
from string import capwords
from collections import OrderedDict

from typing import (
    Optional,
    Union,
    List,
    # Tuple,
)

from .p_specs import (
    ITEM_ASSET_DL_REGEX,
    ITEM_TYPE_SPECS,
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

    _bundles: OrderedDict

    def __init__(self, bundles_spec_file):

        self._spec_file = bundles_spec_file

        if not os.path.exists(self._spec_file):
            log.debug(f'Bundles file does not exist:\n{self._spec_file}')
            return

        with open(self._spec_file, 'r') as fp:
            bundles: OrderedDict = json.load(fp, object_pairs_hook=OrderedDict)

        self._bundles_json = json.dumps(bundles)
        self._bundles: OrderedDict = bundles.get('bundles', OrderedDict())
        self._deprecated = bundles.get('deprecated', OrderedDict())
        self._version: str = bundles.get('version', '')

        # Cache bundles available for a given item type
        self._bundles_per_item_types = OrderedDict()
        for item_type in ITEM_TYPE_SPECS:
            self._bundles_per_item_types[item_type] = \
                self.bundles_for_item_type(item_type)

    def version(self):
        return self._version

    def bundles(self) -> OrderedDict:
        return self._bundles

    def bundles_json(self) -> str:
        return self._bundles_json

    def bundle(self, bundle_name: str) -> Optional[OrderedDict]:
        return self._bundles.get(bundle_name)

    def bundles_per_item_types(self) -> OrderedDict:
        """Get bundles per all item types from cache"""
        return self._bundles_per_item_types

    def bundles_per_item_type(
            self, item_type: str,
            permissions: Optional[List[str]] = None) -> Optional[OrderedDict]:
        """
        Get bundles per an item type from cache, optionally constrained by
        user's permissions.
        :param item_type: Item type, e.g. PSScene3Band
        :param permissions: List of permissions, e.g. assets.udm2:download
        :return: Dict of bundles or None
        """
        bndls_per_it = self._bundles_per_item_types.get(item_type)
        if not permissions:
            return bndls_per_it

        bndls_allowed = self.bundles_per_permissions(permissions)
        if not bndls_allowed:
            return bndls_per_it
        constrained_bndls = OrderedDict()
        for b in bndls_per_it:
            if b in bndls_allowed or b.startswith('all'):
                constrained_bndls[b] = OrderedDict(bndls_per_it[b])

        return constrained_bndls

    def filters_opts_for_bundles(
            self, bundles: OrderedDict,
            item_type: Optional[str] = None) -> Optional[OrderedDict]:
        filters_opts = OrderedDict()
        if not bundles:
            return filters_opts

        for f in self.filters():
            for b_v in bundles.values():
                if f not in b_v:
                    continue
                if f not in filters_opts:
                    filters_opts[f] = []
                if b_v[f] not in filters_opts[f]:
                    filters_opts[f].append(b_v[f])

        if not filters_opts:
            # Set some defaults, though not sure how that resolves if they
            #   don't match up with possibly permission-constrained bundles.
            if item_type and item_type == 'PSScene3Band':
                filters_opts = self.filter_defaults()['PSScene3Band']
            else:
                filters_opts = self.filter_defaults()['default']

        return filters_opts

    @staticmethod
    def _semi_capitalize(val):
        """Capitalizes words separated by ' ' or '-', but not conjunctions"""
        if re.match(r'^[A-Z]', val) is None:
            s = capwords(val)
            return capwords(s, sep='-') if ' ' not in s else s
        return val

    def filter_tree_from_bundles(
            self, bundles: OrderedDict) -> Optional[OrderedDict]:
        if not bundles:
            return None

        filter_vals = []
        for b_v in bundles.values():  # type: OrderedDict
            if not self.bundle_has_all_filters(b_v):
                continue
            filter_vals.append([self._semi_capitalize(b_v[f])
                                for f in reversed(self.filters())])

        if filter_vals:
            # Build tree of unique branching values
            filter_tree = OrderedDict()
            for item in filter_vals:
                curr_tree = filter_tree

                for key in item[::-1]:
                    if key not in curr_tree:
                        curr_tree[key] = OrderedDict()
                    curr_tree = curr_tree[key]

            return filter_tree

        return None

    def filter_keyed_bundles(self, bundles: OrderedDict) -> OrderedDict:
        fk_bundles = OrderedDict()
        for b_k, b_v in bundles.items():
            if not self.bundle_has_all_filters(b_v):
                continue
            fk_bundles[tuple([self._semi_capitalize(b_v.get(f))
                              for f in self.filters()])] = b_k

        return fk_bundles

    def bundle_keyed_filters(self, bundles: OrderedDict) -> OrderedDict:
        fk_bundles = self.filter_keyed_bundles(bundles)
        bndl_filters = OrderedDict()
        for b_k, b_v in fk_bundles.items():
            bndl_filters[b_v] = b_k

        return bndl_filters

    def deprecated_bundles(self) -> OrderedDict:
        return self._deprecated

    def bundle_has_all_filters(self, bundle: OrderedDict) -> bool:
        return all([f in bundle for f in self.filters()])

    def bundles_for_item_type(self, item_type: str) -> OrderedDict:
        item_type_bundles = OrderedDict()
        for b_k, b_v in self._bundles.items():  # type: str, OrderedDict
            assets = b_v.get('assets')
            if assets is None:
                log.debug(f'No assets for bundle "{b_k}"')
                continue

            has_all_filters = (self.bundle_has_all_filters(b_v)
                               or b_k.startswith('all'))
            exclude_dn = (item_type in ['PSScene3Band', 'PSScene4Band']
                          and b_v.get('radiometry') == 'digital numbers')
            # TODO: Remove "udm and udm2" filter once that's vetted
            #       (Note from Planet Explorer web app team)
            exclude_udm2 = b_v.get('auxiliaryFiles') == 'udm and udm2'
            exclude_all_bands = (item_type == 'PSScene3Band'
                                 and b_v.get('bands') == 'all')

            # FIXME: Supposed to have 'and not deprecated' in conditional
            #        below, but deprecated are still in bundles specs
            # deprecated = (b_k in self._deprecated
            #               and 'assets' in self._deprecated[b_k]
            #               and item_type in self._deprecated[b_k]['assets'])

            if (item_type in assets
                    and not exclude_udm2
                    and not exclude_dn
                    and not exclude_all_bands
                    and has_all_filters):
                # Copy bundle...
                item_type_bundles[b_k] = OrderedDict(b_v)
                #   but flatly override assets relative to item type
                item_type_bundles[b_k]['assets'] = assets[item_type]

        return item_type_bundles

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
        for b_k, b_v in self._bundles.items():  # type: str, OrderedDict
            assets = b_v.get('assets')
            if assets is None:
                continue
            for it_k, it_v in assets.items():
                if asset in it_v:
                    bundles.append(b_k)
                    if first_found:
                        return bundles
        # Remove dup values, but preserve order
        return list(OrderedDict.fromkeys(bundles))

    def bundle_for_permission(self, permission: str) -> Optional[str]:
        """
        :param permission: e.g. assets.analytic_xml:download
        :return: First found matching bundle name
        """
        bundles = self.bundles_for_permission(permission, first_found=True)
        return bundles[0] if bundles else None

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
        item_bundle = self.default_bundles().get(item_type)
        if not item_bundle:
            return ''
        return item_bundle

    def filter_option_description(
            self, filter_index: Union[str, int], option: str) -> str:
        opt_desc = ''

        if type(filter_index) == int:
            keys = list(self.filter_descriptions().keys())
            if filter_index < 0 or len(keys) < filter_index + 1:  # index error
                return opt_desc
            key = keys[filter_index]
        else:
            key = filter_index

        filter_desc = self.filter_descriptions().get(key)
        if filter_desc:
            opt_desc = filter_desc.get(option)

        return opt_desc

    @staticmethod
    def filters():
        return ['bands', 'radiometry', 'rectification', 'fileType']

    @staticmethod
    def filter_descriptions():
        """
        From Planet Eplorer web app team.
        Note: _semi_capitalize applied to filter option description keys
        """
        return OrderedDict([
            ('bands', {
                'All': 'Includes all available bands (recommended)',
                '3-Band': 'Includes red, green, and blue (visual) bands only',
                'Panchromatic': 'Includes panchromatic band only',
            }),
            ('radiometry', {
                'Surface Reflectance':
                    'Processed to ensure consistency in spectral response ('
                    'including atmospheric corrections); recommended for '
                    'analytic processing',
                'At-Sensor':
                    'Calibrated to at-sensor radiance; recommended for '
                    'custom radiometric processing',
                'Visual':
                    'Processed for human visualization; recommended for '
                    'visual inspection or as a backdrop layer',
                'Digital Numbers': 'No radiometric corrections or '
                                   'calibrations applied',
            }),
            ('rectification', {
                'Orthorectified':
                    'Corrects for geometric distortions; recommended for '
                    'most applications',
                'Non-Orthorectified':
                    'No geometric corrections applied; recommended for '
                    'custom orthorectification',
            }),
            ('fileType', {
                'GeoTIFF': 'TIFF embedded with georeferencing information ('
                           'recommended)',
                'TIFF and RPCs': 'TIFF and rational polynomial coefficients '
                                 '(recommended)',
                'NITF': 'National Imagery Transmission Format',
            }),
            ('auxiliaryFiles', {
                'udm': 'Planet legacy cloud mask',
                'udm and udm2':
                    'Planet usable data mask (identifies cloud, haze, cloud '
                    'shadow, snow, and clear pixels) and legacy cloud mask ('
                    'recommended)',
            })
        ])

    @staticmethod
    def filter_defaults():
        return {
            'PSScene3Band': {
                'bands': ['3-band'],
                'radiometry': ['visual'],
                'rectification': ['orthorectified'],
                'fileType': ['GeoTIFF'],
            },
            'default': {
                'bands': ['all'],
                'radiometry': ['at-sensor', 'surface reflectance'],
                'rectification': ['orthorectified'],
                'fileType': ['GeoTIFF', 'TIFF and RPCs'],
            },
        }

    @staticmethod
    def default_bundles():
        return {
            'PSScene4Band': 'analytic',
            'PSScene3Band': 'visual',
            'REOrthoTile': 'analytic',
            'SkySatCollect': 'analytic',
            'Landsat8L1G': 'analytic',
            'SkySatScene': 'analytic',
            'REScene': 'analytic',
            'Sentinel2L1C': 'analytic',
            'PSOrthoTile': 'analytic',
        }

    @staticmethod
    def tools():
        return [
            ('clip', 'Clip items to AOI'),
            # ('bandmath', 'Band math'),
            # ('composite', 'Composite rasters into one'),
            # ('reproject', 'Reproject'),
            # ('tile', 'Tiled output'),
            # ('tiff_optimize', 'TIFF optimization'),
            # ('toar', 'Top of Atmosphere Reflectance'),
            # ('harmonize', 'Harmonization'),
        ]


if __name__ == "__main__":
    import sys
    from qgis.PyQt.QtWidgets import (
        QApplication,
    )

    from planet_explorer.planet_api.p_specs import (
        ITEM_TYPE_SPECS,
    )

    cur_dir = os.path.dirname(__file__)
    plugin_path = os.path.split(cur_dir)[0]
    print(plugin_path)
    sys.path.insert(0, plugin_path)

    app = QApplication(sys.argv)

    bundles_json_file = os.path.join(cur_dir, 'resources', 'bundles.json')

    order_bundles = PlanetOrdersV2Bundles(bundles_json_file)

    # bundles_for_perm: List[str] = order_bundles.bundles_for_permission(
    #     'assets.analytic_xml:download', first_found=True)
    #
    # has_allfilters = False
    # if bundles_for_perm:
    #     a_bundle = order_bundles.bundle(bundles_for_perm[0])
    #     has_allfilters = \
    #         order_bundles.bundle_has_all_filters(a_bundle)

    perms_json_file = os.path.join(
        cur_dir, 'request-result-samples', 'item-perms-specs.json')
    perms_sorted_json_file = os.path.join(
        cur_dir, 'request-result-samples', 'item-perms-specs_sorted.json')

    with open(perms_json_file, 'r') as pj_fp:
        perms = json.load(pj_fp, object_pairs_hook=OrderedDict)
    with open(perms_sorted_json_file, 'r') as psj_fp:
        perms_sorted = json.load(psj_fp, object_pairs_hook=OrderedDict)

    bundle_results = OrderedDict()
    for itemtype in ITEM_TYPE_SPECS:
        bundle_results[itemtype] = OrderedDict()

        bundle_results[itemtype]['per_item'] = \
            order_bundles.bundles_per_item_type(itemtype)

        # bundle_results[itemtype]['per_item_w_perms'] = \
        #     order_bundles.bundles_per_item_type(
        #         itemtype, permissions=perms[itemtype])

        bundles_w_perms = order_bundles.bundles_per_item_type(
            itemtype, permissions=perms_sorted[itemtype])
        bundle_results[itemtype]['per_item_w_perms_sorted'] = bundles_w_perms

        bundle_results[itemtype]['filters_w_perms_sorted'] = \
            order_bundles.filters_opts_for_bundles(bundles_w_perms,
                                                   item_type=itemtype)

        bundle_results[itemtype]['filter_tree_w_perms_sorted'] = \
            order_bundles.filter_tree_from_bundles(bundles_w_perms)

        bundle_results[itemtype]['filterkeyed_tree_w_perms_sorted'] = \
            order_bundles.filter_keyed_bundles(bundles_w_perms)

        bundle_results[itemtype]['tree_w_perms_sorted_keyed_filters'] = \
            order_bundles.bundle_keyed_filters(bundles_w_perms)

    sys.exit(app.exec_())
