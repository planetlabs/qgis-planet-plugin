# -*- coding: utf-8 -*-
"""
***************************************************************************
    __init__.py
    ---------------------
    Date                 : August 2019
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
from __future__ import absolute_import

__author__ = "Planet Federal"
__date__ = "August 2019"
__copyright__ = "(C) 2019 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

import os
import sys

extlibs = os.path.abspath(os.path.dirname(__file__) + "/extlibs")
if os.path.exists(extlibs) and extlibs not in sys.path:
    sys.path.insert(0, extlibs)


# noinspection PyPep8Naming
def classFactory(iface):
    from planet_explorer.pe_plugin import PlanetExplorer

    return PlanetExplorer(iface)

