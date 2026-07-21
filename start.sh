#!/usr/bin/env bash

set -euo pipefail

cd /app

export HOST="0.0.0.0"
export PORT="${PORT:-8080}"

echo "================================="
echo " Rebecca Panel Railway Startup "
echo " Host: $HOST"
echo " Port: $PORT"
echo "================================="


if [ -f "./rebecca-server" ]; then

    chmod +x ./rebecca-server

    echo "Starting rebecca-server..."

    exec ./rebecca-server \
        --host "$HOST" \
        --port "$PORT"

fi


if [ -f "./rebecca-cli" ]; then

    chmod +x ./rebecca-cli

    echo "Starting rebecca-cli..."

    exec ./rebecca-cli \
        --host "$HOST" \
        --port "$PORT"

fi


echo "ERROR: Rebecca binary not found"
ls -la /app

exit 1
