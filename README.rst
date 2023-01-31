.. [![Build Status](https://travis-ci.com/boundlessgeo/qgis-planet-explorer-plugin.svg?token=oVeBdhfrozuuFBhVreJA&branch=master)](https://travis-ci.com/boundlessgeo/qgis-planet-explorer-plugin)

Planet Plugin for QGIS
===============================

.. image:: https://github.com/planetlabs/qgis-planet-plugin/actions/workflows/testing.yml/badge.svg?branch=master

Browse, filter, preview and download `Planet Inc <https://www.planet.com/>`_ imagery in QGIS.

Official documentation can be found `here <https://developers.planet.com/integrations/>`_

Requirements
************

QGIS 3.10 (minimum)

Development Setup
*****************

**Note**, if you just need to install the plugin, jump to Plugin Setup (below).

A quick setup of the development environment needed for the plugin and to work
with the `Planet API tutorials <https://developers.planet.com/planetschool/>`_ is available via the ``conda`` packaging system.

The dev environ provides:

- QGIS desktop app
- Python package of bindings for QGIS
- Python package of bindings to Qt (LTS version) via PyQt
- ``paver`` Python package
- ``planet`` Python package
- ``pip`` Python package for installing packages
  (try to use ``conda`` packages first, if available)
- Python packages necessary for Planet API tutorials

Install
-------


Install from source
++++++++++++++

First, clone this repository.

Using an install of ``conda`` (from `miniconda3 <https://docs.conda.io/en/latest/miniconda.html>`_ or `anaconda <https://www.anaconda.com/distribution/>`_), load this environment file: `qgis3-conda-forge-env.yml <./qgis3-conda-forge-env.yml>`_ (see `Managing conda environments <https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html>`_)

     conda env create -f=/path/to/qgis3-conda-forge-env.yml

This will create a ``conda`` environment named ``qgis3-conda-forge``, which you
can activate in a Terminal session:

    conda activate qgis3-conda-forge

Or, you can use the environ as a basis for your Python interpreter within
VSCode, PyCharm or similar IDE that natively supports parsing ``conda``
environs.

Then, install the following into the ``qgis3-conda-forge`` environ:

    conda install --force-reinstall -n qgis3-conda-forge -c conda-forge conda-wrappers

The ``conda-wrappers`` utility creates ``conda`` environ wrappers for ALL executables/scripts in ``qgis3-conda-forge/bin``, so needs to be run *after* setting up the environment. The same ``install --force-reinstall`` command needs re-run if you install any *new* packages that add executables/scripts to ``qgis3-conda-forge/bin``, so they can also be wrapped.

The wrapped executables/scripts are available at this path (note added ``wrappers/conda`` subdirectories):

    qgis3-conda-forge/bin/wrappers/conda/(exe|script)

For example, you should use the following `python3` exe path for IDE setups:

    /path/to/your/miniconda3/envs/qgis3-conda-forge/bin/wrappers/conda/python3


Install from QGIS plugin repository
++++++++++++++

- Open QGIS application and open plugin manager.
- Search for `Planet` in the All page of the plugin manager.
- From the found results, click on the `Planet_Explorer` result item and a page with plugin information will show up.

- Click the `Install Plugin` button at the bottom of the dialog to install the plugin.


Install from ZIP file
++++++++++++++

Alternatively the plugin can be installed using **Install from ZIP** option on the
QGIS plugin manager.

- Download zip file from the required plugin released version `planet_explorer.zip <https://github.com/planetlabs/qgis-planet-plugin/releases/download/{tagname}/planet_explorer.zip>`_
- From the **Install from ZIP** page, select the zip file and click the **Install** button to install plugin

Install from planet plugin repository
++++++++++++++

Planet plugin repository is available `here <https://raw.githubusercontent.com/planetlabs/qgis-planet-plugin/release/docs/repository/plugins.xml>`_

- Open the QGIS plugin manager, then select the **Settings** page

- Click **Add** button on the **Plugin Repositories** group box and use the above url to create the new plugin repository.

- The plugin should now be available from the list of all plugins that can be installed.


Plugin Setup
************

To install the latest version of the plugin:

- Clone this repository or download and unzip the latest code of the plugin, if you have not already.

- If you do not have `paver <https://github.com/paver/paver>`_ installed, install
  it by typing the following in a console
  (*contributor note*: it is already in the dev environment):

    pip install paver

- Open a console in the folder created in the first step, and type

    paver setup

  This will get all the dependencies needed by the plugin.

- Install into QGIS by running

    paver install

  That will copy the code into your QGIS user plugin folder, or create a
  symlink in it, depending on your OS.

  **NOTE**: This ``paver`` task only installs to the 'default' QGIS profile; so, you will have to ensure that is the active profile in order to see the plugin. You will also need to initially activate the plugin inside of the QGIS plugin manager.

- To package the plugin (*not needed during development*), run

    paver package

  Documentation will be built in the `docs` folder and added to the resulting
  zip file. It includes dependencies as well, but it will not download them, so
  the `setup` task has to be run before packaging.
