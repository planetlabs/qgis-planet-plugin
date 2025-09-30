#!/usr/bin/python
"""
Install a plugin from a zip file into QGIS. This script is meant to be run inside of QGIS:

.. code-block:: bash

    qgis --noplugins --code install_plugin.py

The package zip file for the plugin is expected to be present in current working directory.

Verifies:
    - PLQGIS-TC01
    - PLQGIS-TC02
"""
import os
import pathlib
import traceback


class PluginInstallException(Exception):
    pass


ERROR_OCCURRED = False
ERROR_MSG = ""
PLUGIN_KEY = "planet_explorer"


def error_catcher(msg, tag, level):
    """
    Catch a python error and raise a PluginInstallException
    """
    global ERROR_OCCURRED, ERROR_MSG
    if tag == "Python error" and level != 0:
        ERROR_OCCURRED = True
        ERROR_MSG = msg


try:
    try:
        import pyplugin_installer
        from qgis import utils
        from qgis.core import QgsApplication
    except ImportError:
        raise PluginInstallException(
            "Cannot install plugin as 'pyplugin_installer' could not be imported."
            " Is the script running in the QGIS env?"
        )

    zip_files = [file for file in pathlib.Path("./").glob("*.zip")]

    if not zip_files:
        raise PluginInstallException(
            f"ERROR: No plugin zip file found at {pathlib.Path('./').absolute()}."
        )

    if len(zip_files) > 1:
        raise PluginInstallException(
            f"ERROR: More than one plugin zip file found at {pathlib.Path('./').absolute()}."
            f" Found {[str(f) for f in zip_files]}."
        )

    plugin_install_zip = zip_files[0]
    plugin_installer = pyplugin_installer.instance()
    # Make sure plugin is not installed
    if PLUGIN_KEY in pyplugin_installer.installer_data.plugins.all():
        plugin_installer.uninstallPlugin(PLUGIN_KEY)

    # Attach the error catcher
    QgsApplication.messageLog().messageReceived.connect(error_catcher)

    # Install from the zip file
    plugin_installer.installFromZipFile(str(plugin_install_zip.absolute()))
    # unload plugin so we can test load/unload
    if PLUGIN_KEY in utils.active_plugins:
        utils.unloadPlugin(PLUGIN_KEY)

    if PLUGIN_KEY not in pyplugin_installer.installer_data.plugins.all().keys():
        raise PluginInstallException("Planet plugin failed to install!")

    if ERROR_OCCURRED:
        raise PluginInstallException(
            f"Python exception hit during plugin install: \n {ERROR_MSG}"
        )

    # Start/Load the plugin
    if not utils.loadPlugin(PLUGIN_KEY):
        raise PluginInstallException(f"Failed to load plugin '{PLUGIN_KEY}'")
    if not utils.startPlugin(PLUGIN_KEY):
        raise PluginInstallException(f"'{PLUGIN_KEY}' failed to start!")
    if PLUGIN_KEY not in utils.active_plugins:
        raise PluginInstallException(
            f"'{PLUGIN_KEY}' missing in active_plugins, found: {utils.active_plugins}"
        )

    # Unload the plugin
    if not utils.unloadPlugin(PLUGIN_KEY):
        raise PluginInstallException("'planet_explorer' failed to unload")
    if PLUGIN_KEY in utils.active_plugins:
        raise PluginInstallException(
            "'planet_explorer' still in active_plugins after unload"
        )

    # Uninstall the plugin
    plugin_installer.uninstallPlugin(PLUGIN_KEY, quiet=True)
    if PLUGIN_KEY in pyplugin_installer.installer_data.plugins.all().keys():
        raise PluginInstallException("Planet plugin failed to uninstall!")

    if ERROR_OCCURRED:
        raise PluginInstallException(
            f"Python exception hit during plugin uninstall: \n {ERROR_MSG}"
        )
except Exception:  # noqa
    # Print the error so we know where it failed,
    # and exit with a non-zero status code so CI will fail.
    print(
        "FAIL: Plugin install, load, unload, and uninstall failed with the following:"
    )
    print(traceback.format_exc())
    os._exit(1)
finally:
    # The install and uninstall worked! Exit QGIS with a 0 status code.
    print(
        f"PASS: Plugin install, load, unload, and "
        f"uninstall successful for {str(plugin_install_zip)}"
    )
    os._exit(0)
