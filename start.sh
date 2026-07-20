#!/usr/bin/env bash

set -e


cd /app


export HOST="0.0.0.0"
export PORT="${PORT:-8080}"


echo "================================="
echo " Rebecca Panel Railway Startup "
echo " Host: $HOST"
echo " Port: $PORT"
echo "================================="


# پیدا کردن فایل اجرایی

if [ -f "./rebecca" ]; then

    chmod +x ./rebecca

    echo "Starting Rebecca..."

    exec ./rebecca \
        --host "$HOST" \
        --port "$PORT"

fi


# اگر داخل پوشه بود

if [ -f "./Rebecca" ]; then

    chmod +x ./Rebecca

    echo "Starting Rebecca..."

    exec ./Rebecca \
        --host "$HOST" \
        --port "$PORT"

fi


echo "ERROR: Rebecca binary not found"

ls -la /app

exit 1
