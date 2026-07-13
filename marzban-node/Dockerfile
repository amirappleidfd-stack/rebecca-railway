# ---------------- BUILD (xray + deps) ----------------
FROM python:3.12-slim AS build

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential curl unzip ca-certificates openssl \
 && rm -rf /var/lib/apt/lists/*

# Xray-core binary (same as the panel uses).
ARG XRAY_VERSION=1.8.23
RUN set -eux; \
    curl -fSL \
    https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip \
    -o /tmp/xray.zip \
    && unzip -o /tmp/xray.zip -d /tmp/xray \
    && mkdir -p /usr/local/bin /usr/local/share/xray \
    && install -m 0755 /tmp/xray/xray /usr/local/bin/xray \
    && cp -r /tmp/xray/* /usr/local/share/xray/ \
    && /usr/local/bin/xray version

COPY requirements.txt /code/
RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt


# ---------------- RUNTIME ----------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    SERVICE_HOST=127.0.0.1 \
    SERVICE_PROTOCOL=rest \
    SERVICE_TLS=true \
    XRAY_EXECUTABLE_PATH=/usr/local/bin/xray \
    XRAY_ASSETS_PATH=/usr/local/share/xray \
    SSL_DIR=/var/lib/marzban-node

WORKDIR /code

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/xray /usr/local/bin/xray
COPY --from=build /usr/local/share/xray /usr/local/share/xray

# ----- Marzban-node application (this folder) -----
COPY marzban-node/ /code/

# ----- Marzban panel (repo root) -----
# The build context is the repo root, so copy the panel sources into /panel.
COPY app /panel/app
COPY cli /panel/cli
COPY xray_api /panel/xray_api
COPY hermes-agent /panel/hermes-agent
COPY main.py /panel/main.py
COPY config.py /panel/config.py
COPY marzban-cli.py /panel/marzban-cli.py
COPY requirements.txt /panel/requirements.txt

RUN groupadd --system --gid 1001 app \
 && useradd --system --uid 1001 --gid app app \
 && mkdir -p /var/lib/marzban-node /code/data /var/lib/marzban \
 && chown -R app:app /code /var/lib/marzban-node /var/lib/marzban \
 && chmod +x /code/start.sh

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
 CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/')"

ENTRYPOINT ["bash", "/code/start.sh"]
