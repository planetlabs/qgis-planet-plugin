#!/bin/bash

cd "$(dirname "$0")/.." || exit
export GITHUB_WORKSPACE=$PWD
docker-compose -f .docker/docker-compose.gh.yml run -e "QGIS_TEST_VERSION=latest" -e "PLANET_USER=${PLANET_USER}" -e "PLANET_PASSWORD=${PLANET_PASSWORD}" qgis /usr/src/.docker/run-docker-tests.sh "$@"
docker-compose -f .docker/docker-compose.gh.yml rm -s -f
