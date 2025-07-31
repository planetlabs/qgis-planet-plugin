ARG QGIS_TEST_VERSION=latest
FROM qgis/qgis:${QGIS_TEST_VERSION}

RUN apt-get update \
    && apt-get install -y python3-pip

COPY ./requirements.txt /tmp/
RUN apt remove python3-pytest
RUN pip3 install --break-system-packages -r /tmp/requirements.txt

COPY ./requirements_test.txt /tmp/
RUN pip3 install --break-system-packages -r /tmp/requirements_test.txt

ENV LANG=C.UTF-8
ENV IS_DOCKER_CONTAINER=true

WORKDIR /
