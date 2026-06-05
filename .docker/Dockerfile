ARG QGIS_TEST_VERSION=latest
FROM qgis/qgis:${QGIS_TEST_VERSION}

RUN apt-get update \
    && apt-get install -y curl

COPY ./requirements.txt /tmp/
RUN apt remove -y python3-pytest python3-pip
# Install the freshes pip version so we can use the break-system-packages option
RUN curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py \
    && python3 get-pip.py --break-system-packages \
    && rm get-pip.py

RUN pip3 install --break-system-packages -r /tmp/requirements.txt

COPY ./requirements_test.txt /tmp/
RUN pip3 install --break-system-packages -r /tmp/requirements_test.txt

ENV LANG=C.UTF-8
ENV IS_DOCKER_CONTAINER=true

WORKDIR /
