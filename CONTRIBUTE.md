# Contributing

## Contributing to Planet Explorer QGIS plugin

Planet Explorer QGIS plugin is an open source project and we appreciate
contributions very much.

## Proper formatting

Before making a pull request, please make sure your code is properly formatted.
To check for formatting errors use

    paver pep8

to automatically format your code run following command **before** issuing
`git commit`

    paver autopep8

## Pre-commit QA checks

There are a number of pre-commit checks that should all pass before committing
new code or submitting a PR. You can manually run these using the following
command:

   pre-commit run --all-files -v

You can run a specific check e.g. markdown linting like this:

    pre-commit run markdownlint --all-files -v
