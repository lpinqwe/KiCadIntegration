FROM kicad/kicad:10.0

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-pip \
        python3-venv \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

ENV PATH="/opt/venv/bin:$PATH"

RUN git clone --depth 1 https://github.com/aklofas/kicad-happy.git /opt/kicad-happy

COPY verify/ /opt/pipeline/verify/

RUN printf '%s\n' \
        '#!/bin/sh' \
        'exec /opt/venv/bin/python3 /opt/pipeline/verify/__main__.py "$@"' \
        > /usr/local/bin/verify \
    && chmod 0755 /usr/local/bin/verify

RUN chown -R kicad:kicad /opt/venv /opt/kicad-happy /opt/pipeline

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    HAPPY_ROOT=/opt/kicad-happy \
    NGSPICE_TIMEOUT=120

WORKDIR /work

USER kicad
