#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Install a plugin from a zip file into QGIS. This script is meant to be run inside of QGIS:

.. code-block:: bash

    qgis --noplugins --code install_plugin.py

The package zip file for the plugin is expected to be present in current working directory.

Verifies:
    - PLQGIS-TC01
    - PLQGIS-TC02
"""
import logging
import os
import pathlib
import traceback

from qgis import utils
from qgis.core import QgsApplication

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s:%(levelname)s:%(message)s",
    encoding="utf-8",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=logging.DEBUG,
)


class PluginInstallException(Exception):
    pass


ERROR_OCCURRED = False
ERROR_MSG = ""
PLUGIN_KEY = "planet_explorer"


def error_catcher(msg, tag, level):
    """
    Catch a python error and raise a PluginInstallException

    Args:
        msg (str): The log message text.
        tag (str): The tag or category of log message.
        level (int): The log severity level.
    """
    global ERROR_OCCURRED, ERROR_MSG
    if tag == "Python error" and level != 0:
        ERROR_OCCURRED = True
        ERROR_MSG = msg


def find_plugin_zip_file():
    cwd = pathlib.Path(".").absolute()
    zip_files = list(cwd.glob("*.zip"))
    zip_files_str = (
        ", ".join(str(file) for file in zip_files) if zip_files else "(none)"
    )

    if not zip_files:
        raise PluginInstallException(f"No plugin zip file found at {cwd}.")
    else:
        logger.info(
            f"Found the following zip files in the current directory: {zip_files_str}"
        )

    if len(zip_files) > 1:
        raise PluginInstallException(
            f"More than one plugin zip file found at {cwd}." f" Found {zip_files_str}."
        )
    else:
        plugin_install_zip = str(zip_files[0].absolute())
        logger.info(f"Using plugin zip file: {plugin_install_zip}")

    return plugin_install_zip


def uninstall_plugin():
    # Uninstall the plugin
    plugin_installer.uninstallPlugin(PLUGIN_KEY, quiet=True)
    if PLUGIN_KEY in pyplugin_installer.installer_data.plugins.all():
        raise PluginInstallException(f"Plugin '{PLUGIN_KEY}' failed to uninstall.")
    else:
        logger.info(f"Plugin '{PLUGIN_KEY}' uninstalled successfully.")


def unload_plugin():
    # Unload the plugin
    if not utils.unloadPlugin(PLUGIN_KEY):
        raise PluginInstallException(f"Plugin '{PLUGIN_KEY}' failed to unload.")
    else:
        logger.info(f"Plugin '{PLUGIN_KEY}' unloaded successfully.")
    if PLUGIN_KEY in utils.active_plugins:
        raise PluginInstallException(
            f"Plugin '{PLUGIN_KEY}' failed to unload and is still an active plugin."
        )
    else:
        logger.info(
            f"Plugin '{PLUGIN_KEY}' is no longer active as expected after unload."
        )


def start_load_plugin():
    # Start/Load the plugin
    if not utils.loadPlugin(PLUGIN_KEY):
        raise PluginInstallException(f"Plugin '{PLUGIN_KEY}' failed to load.")
    else:
        logger.info(f"Plugin '{PLUGIN_KEY}' loaded successfully!")

    if not utils.startPlugin(PLUGIN_KEY):
        raise PluginInstallException(f"Plugin '{PLUGIN_KEY}' failed to start.")
    else:
        logger.info(f"Plugin '{PLUGIN_KEY}' started successfully!")

    if PLUGIN_KEY not in utils.active_plugins:
        raise PluginInstallException(
            f"Plugin '{PLUGIN_KEY}' not found in active_plugins, found: {utils.active_plugins}"
        )
    else:
        logger.info(f"Plugin '{PLUGIN_KEY}' is active as expected after startup.")


try:
    try:
        import pyplugin_installer
    except ImportError as e:
        logger.exception("Failed to import pyplugin_installer")
        raise PluginInstallException(
            "Cannot install plugin as 'pyplugin_installer' could not be imported."
            " Is the script running in the QGIS env?"
        ) from e

    plugin_installer = pyplugin_installer.instance()

    # Make sure plugin is not installed
    if PLUGIN_KEY in pyplugin_installer.installer_data.plugins.all():
        logger.info(f"Uninstalling existing plugin: {PLUGIN_KEY}")
        plugin_installer.uninstallPlugin(PLUGIN_KEY)
        logger.info(f"Plugin {PLUGIN_KEY} uninstalled successfully!")

    # Attach the error catcher
    QgsApplication.messageLog().messageReceived.connect(error_catcher)

    plugin_install_zip = find_plugin_zip_file()

    # Install from the zip file
    logger.info(
        f"Installing the plugin {PLUGIN_KEY} from the zip file {plugin_install_zip} ..."
    )
    plugin_installer.installFromZipFile(plugin_install_zip)
    if PLUGIN_KEY in pyplugin_installer.installer_data.plugins.all():
        logger.info(f"Plugin '{PLUGIN_KEY}' installed successfully!")
    else:
        raise PluginInstallException(f"Plugin '{PLUGIN_KEY}' failed to install.")

    if PLUGIN_KEY in utils.active_plugins:
        unload_plugin()

    if ERROR_OCCURRED:
        raise PluginInstallException(
            f"Python exception hit during plugin install: \n {ERROR_MSG}"
        )

    start_load_plugin()
    unload_plugin()
    uninstall_plugin()

    if ERROR_OCCURRED:
        raise PluginInstallException(
            f"Python exception hit during plugin uninstall: \n {ERROR_MSG}"
        )
except Exception:  # noqa
    # Print the error so we know where it failed,
    # and exit with a non-zero status code so CI will fail.
    logger.error(
        "FAIL: Plugin install, load, unload, and uninstall failed "
        f"with the following: \n {traceback.format_exc()}"
    )
    os._exit(1)
else:
    # The install and uninstall worked! Exit QGIS with a 0 status code.
    logger.info(
        f"PASS: Plugin install, load, unload, and "
        f"uninstall successful for {str(plugin_install_zip)}"
    )
    os._exit(0)
