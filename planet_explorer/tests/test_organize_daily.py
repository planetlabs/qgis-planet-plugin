# -*- coding: utf-8 -*-
"""
***************************************************************************
    test_organize_daily.py
---------------------
Date                 : September 2019
Author               : Planet Federal
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
import sys
# import logging
import json

from collections import (
    OrderedDict,
)
from typing import (
    List,
)

# noinspection PyPackageRequirements
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
)

from planet_explorer.planet_api.p_client import (
    RESOURCE_DAILY,
)
from planet_explorer.planet_api.p_node import (
    PlanetNode,
    PlanetNodeType as NodeT,
)

plugin_path = os.path.split(os.path.dirname(__file__))[0]

res_file = os.path.join(plugin_path, 'planet_api/thumbnails/thumbs.json')


def load_daily_items(nodes: List[PlanetNode],) -> list:
    # Note: sort_date of nodes should have already been set

    # TODO: Do this without copying anything, i.e. refs from flat results list

    # First, organize in dict by group type
    n_tree = OrderedDict()
    for node in nodes:
        n_date = node.sort_date().date()  # skip time
        n_type = node.item_type()

        if n_date not in n_tree:
            n_tree[n_date] = OrderedDict()
        if n_type not in n_tree[n_date]:
            n_tree[n_date][n_type] = OrderedDict()
        if node.is_base_image():
            n_sat = node.item_properties()['satellite_id']
            if n_sat not in n_tree[n_date][n_type]:
                n_tree[n_date][n_type][n_sat] = list()
            n_tree[n_date][n_type][n_sat].append(node)

    # Then, populate groups as nodes
    scenes = []
    for n_date, n_types in n_tree.items():

        for n_type, n_sats in n_types.items():
            scene = PlanetNode(
                name=n_type,
                resource_type=RESOURCE_DAILY,
                node_type=NodeT.DAILY_SCENE,
            )
            scene_item_type_ids = []

            # TODO: combine geometries for % area coverage of AOI for scene
            for n_sat, n_images in n_sats.items():
                n_images: List[PlanetNode]
                sat_grp = PlanetNode(
                    name=n_sat,
                    resource_type=RESOURCE_DAILY,
                    node_type=NodeT.DAILY_SAT_GROUP,
                )

                sat_grp.add_children(n_images)
                # set_sort_date needs to come before set_item_type_id_list
                sat_grp.set_sort_date(sat_grp.first_child().sort_date())
                sat_grp_type_item_ids = \
                    [n.item_type_id() for n in n_images]
                sat_grp.set_item_type_id_list(sat_grp_type_item_ids)

                scene_item_type_ids.extend(sat_grp_type_item_ids)
                scene.add_child(sat_grp)

            # set_sort_date needs to come before set_item_type_id_list
            scene.set_sort_date(scene.first_child().sort_date())
            scene.set_item_type_id_list(scene_item_type_ids)
            scenes.append(scene)

    return scenes


if __name__ == "__main__":
    with open(res_file, 'r') as fp:
        res_json = json.load(fp)

    app = QApplication(sys.argv)

    apikey = os.getenv('PL_API_KEY')

    feature_nodes = []
    for feature in res_json['features']:
        feature_nodes.append(
            PlanetNode(
                resource_type=RESOURCE_DAILY,
                resource=feature,
                sort_field='acquired'  # <-- this is important to set
            )
        )

    scene_nodes: List[PlanetNode] = load_daily_items(feature_nodes)

    scene_nodes_w_type = []
    if scene_nodes:
        for scene_node in scene_nodes:
            scene_nodes_w_type.append(len(scene_node.children_of_node_type(
                NodeT.DAILY_SCENE_IMAGE)))

    dlg = QDialog()

    dlg.setMaximumHeight(320)

    dlg.show()

    sys.exit(app.exec_())
