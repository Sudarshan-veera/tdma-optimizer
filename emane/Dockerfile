# Part 2 image: only the EMANE pieces the TDMA demo needs (Ubuntu 24.04, EMANE 1.5.3)
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget ca-certificates iproute2 iputils-ping iperf3 procps python3 python3-networkx

RUN wget -q https://adjacentlink.com/downloads/emane/emane-1.5.3-release-1.ubuntu-24_04.amd64.tar.gz -O /tmp/emane.tgz \
    && tar xzf /tmp/emane.tgz -C /tmp

RUN D=/tmp/emane-1.5.3-release-1/debs/ubuntu-24_04/amd64 \
    && apt-get install -y --no-install-recommends \
        $D/emane-dtds_*.deb $D/emane-manifest_*.deb $D/emane-libs_*.deb $D/emane_*.deb \
        $D/emane-model-tdmaeventscheduler_*.deb $D/emane-trans-virtual_*.deb \
        $D/emane-trans-common_*.deb $D/emane-eventservice_*.deb $D/emane-gen-eel_*.deb \
        $D/python3-emane_*.deb \
    && rm -rf /tmp/emane* /var/lib/apt/lists/*

WORKDIR /work
CMD ["bash"]
