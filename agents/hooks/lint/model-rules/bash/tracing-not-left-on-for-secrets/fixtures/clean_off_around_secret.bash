#!/usr/bin/env bash
set -euo pipefail
set -x

readonly REGISTRY="registry.example.com"

docker build -t "$REGISTRY/app:latest" .
set +x
printf '%s\n' "$REGISTRY_PASSWORD" | docker login "$REGISTRY" -u ci --password-stdin
set -x
docker push "$REGISTRY/app:latest"
