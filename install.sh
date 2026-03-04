#!/bin/bash
# OAK Installer — auto-detect hardware and start stack
# Usage: curl -sL https://raw.githubusercontent.com/SharathSPhD/oak/main/install.sh | bash
# Or:    bash install.sh [dgx|mini|cloud|aio]
set -euo pipefail

echo "OAK Installer — detecting hardware..."

DETECTED_MODE="dgx"
if command -v nvidia-smi &> /dev/null; then
    DETECTED_MODE="dgx"
    echo "NVIDIA GPU detected — using DGX mode"
elif [[ "${OSTYPE:-}" == "darwin"* ]]; then
    DETECTED_MODE="mini"
    echo "macOS detected — using Mini mode"
fi

MODE="${1:-$DETECTED_MODE}"

if [ "$MODE" = "aio" ]; then
    echo "Starting OAK All-in-One container..."
    docker run -d \
        --name oak-aio \
        -p 8501:8501 \
        -p 8000:8000 \
        -p 9000:9000 \
        -v oak-data:/var/lib/postgresql/data \
        -v oak-ollama:/root/.ollama \
        -v oak-workspace:/workspace \
        ghcr.io/sharathsphd/oak-aio:latest
    echo ""
    echo "OAK All-in-One started!"
    echo "Hub: http://localhost:8501"
    echo "API: http://localhost:8000"
    echo "Note: First startup may take a few minutes to initialize the database and pull models."
    exit 0
fi

echo "Starting OAK in $MODE mode (multi-service)..."

if [ ! -d ".git" ]; then
    COMPOSE_URL="https://raw.githubusercontent.com/SharathSPhD/oak/main/docker/docker-compose.prebuilt.yml"
    echo "Downloading compose file..."
    curl -sL "$COMPOSE_URL" -o docker-compose.yml
else
    echo "Using local compose file..."
    cp docker/docker-compose.prebuilt.yml docker-compose.yml 2>/dev/null || true
fi

docker compose --profile "$MODE" up -d

echo ""
echo "OAK is ready!"
echo "Hub: http://localhost:8501"
echo "API: http://localhost:8000"
echo "Proxy: http://localhost:9000"
