ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS build

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

# Build dependencies: compile wheels (grpcio, cryptography, psycopg2, psutil, ...)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential curl unzip gcc python3-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install the Xray-core binary (used by Marzban's own core).
RUN curl -L https://github.com/Gozargah/Marzban-scripts/raw/master/install_latest_xray.sh | bash

# Install the official Xray-core for the Spider integration at /app/xray-core.
RUN mkdir -p /app/xray-core \
    && curl -L -o /tmp/xray.zip \
        https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip \
    && unzip -o /tmp/xray.zip -d /app/xray-core \
    && chmod +x /app/xray-core/xray \
    && rm -f /tmp/xray.zip \
    && /app/xray-core/xray version

COPY ./requirements.txt /code/
RUN python3 -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /code/requirements.txt

# ---------------------------------------------------------------------------
# Final runtime image (single container, no compose)
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHON_LIB_PATH=/usr/local/lib/python${PYTHON_VERSION%.*}/site-packages \
    HOST=0.0.0.0 \
    PORT=8000 \
    UVICORN_HOST=0.0.0.0 \
    SQLALCHEMY_DATABASE_URL=sqlite:////code/db.sqlite3 \
    XRAY_EXECUTABLE_PATH=/usr/local/bin/xray \
    XRAY_ASSETS_PATH=/usr/local/share/xray \
    XRAY_BINARY_PATH=/app/xray-core/xray \
    XRAY_CONFIG_PATH=/app/xray-config/config.json \
    TZ=UTC

WORKDIR /code

# Runtime deps for the Xray binary + database drivers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python packages + binaries + xray assets from the build stage.
COPY --from=build $PYTHON_LIB_PATH $PYTHON_LIB_PATH
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /usr/local/share/xray /usr/local/share/xray
# Spider Xray-core binary (installed + verified in the build stage).
COPY --from=build /app/xray-core /app/xray-core

# Application source (respects .dockerignore).
COPY . /code

# CLI convenience symlink + completion (non-fatal if completion install fails).
RUN ln -s /code/marzban-cli.py /usr/bin/marzban-cli \
    && chmod +x /usr/bin/marzban-cli \
    && (marzban-cli completion install --shell bash || true)

# Run as a non-root user for safety.
RUN useradd -m -u 1000 appuser \
    && mkdir -p /code/data /var/lib/marzban /app/xray-config /app/xray-logs \
    && chown -R appuser:appuser /code /var/lib/marzban /app
USER appuser

EXPOSE 8000

# Railway injects $PORT at runtime; the startup script binds to it.
# The healthcheck hits the root HTML page (always served, auth-free).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/" || exit 1

CMD ["bash", "/code/start-railway.sh"]
