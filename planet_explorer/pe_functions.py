# -*- coding: utf-8 -*-
"""
***************************************************************************
    extent_maptool.py
    ---------------------
    Date                 : March 2017, August 2019
    Author                : Alex Bruy, Planet Federal
    Copyright            : (C) 2017 Boundless, http://boundlessgeo.com
                         : (C) 2019 Planet Inc, https://planet.com
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
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

from qgis.utils import qgsfunction
from qgis.core import QgsExpression


# noinspection PyPep8Naming,PyBroadException
@qgsfunction(1, "PlanetExplorer")
def metadataValue(values, feature, parent):
    """Returns metadata value from the "metadata" field of the
    Planet Inc catalog layer.

    <h4>Syntax</h4>
    <p>metadataValue(<i>metadata</i>)</p>
    <h4>Arguments</h4>
    <p><i>  metadata</i> &rarr; a string. Must be a valid name of the
    metadata entry.<br/></p>
    <h4>Example</h4>
    <p><!-- Show example of function.-->
         metadataValue('provider')</p>
    """
    fieldName = "metadata"
    idx = feature.fieldNameIndex(fieldName)
    if idx == -1:
        parent.setEvalErrorString(
            "Required '{0}' field not found".format(fieldName))
        return None

    text = feature[fieldName]
    if text is None or text == "":
        return None

    metadata = {k: v for k, v in (i.split("=") for i in text.split("\n"))}
    if values[0] not in metadata:
        return None

    value = metadata[values[0]]
    try:
        v = int(value)
        return v
    except ValueError:
        try:
            v = int(value)
            return v
        except:
            return value


functions = [metadataValue]


# noinspection PyPep8Naming,PyArgumentList
def registerFunctions():
    for func in functions:
        if QgsExpression.registerFunction(func):
            yield func.name()


# noinspection PyPep8Naming,PyArgumentList
def unregisterFunctions():
    for func in functions:
        QgsExpression.unregisterFunction(func.name())
