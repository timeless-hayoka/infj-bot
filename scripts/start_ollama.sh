#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Install Docker to run Ollama locally." >&2
  exit 2
fi

echo "Starting Ollama via docker-compose..."
if [ ! -f docker-compose.yml ]; then
  echo "docker-compose.yml missing in project root." >&2
  exit 1
fi

# Prefer `docker compose` but fall back to `docker-compose` if needed
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose up -d ollama
else
  docker-compose up -d ollama
fi

echo "Ollama container started. Host: http://localhost:11434"
