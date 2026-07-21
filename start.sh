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


chmod +x ./rebecca-server ./rebecca-cli || true


echo "Rebecca version:"
./rebecca-server --version || true


echo "Starting rebecca-server..."


exec ./rebecca-server
