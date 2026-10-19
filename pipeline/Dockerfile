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

# kicad-happy — vendor-копия на конкретном коммите (спека §9: воспроизводимость,
# без пина на HEAD). Обновление — точечное и ревьюится.
ARG KICAD_HAPPY_SHA=6a91aaaea124152b2923326c1cf77278e0999cd4
RUN git init -q /opt/kicad-happy \
    && cd /opt/kicad-happy \
    && git remote add origin https://github.com/aklofas/kicad-happy.git \
    && git fetch -q --depth 1 origin "$KICAD_HAPPY_SHA" \
    && git checkout -q FETCH_HEAD \
    && rm -rf /opt/kicad-happy/.git

COPY verify/ /opt/pipeline/verify/
COPY entrypoint.sh /usr/local/bin/entrypoint

RUN chmod 0755 /usr/local/bin/entrypoint \
    && printf '%s\n' \
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

ENTRYPOINT ["/usr/local/bin/entrypoint"]
# По умолчанию — фикстура (работает «из коробки»); свой проект:
# docker compose run verify <project-dir>
CMD ["fixtures/simple-divider"]

USER kicad
