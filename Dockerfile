
FROM ubuntu:22.04

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-minimal \
    python3-distutils \
    python3-aiohttp \
    python3-numpy

WORKDIR /tmp

COPY murrayserver murrayserver
COPY setup.py .
RUN python3 setup.py install

EXPOSE 80
ENTRYPOINT ["/usr/bin/bash", "-c"]
CMD ["/usr/bin/python3 -u -m murrayserver"]
