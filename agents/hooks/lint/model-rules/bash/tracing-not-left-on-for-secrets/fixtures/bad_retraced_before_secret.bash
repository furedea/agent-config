#!/usr/bin/env bash
set -euo pipefail
set -x

readonly REGISTRY="registry.example.com"

docker build -t "$REGISTRY/app:latest" .
set +x
echo "logging in"
set -x
docker login "$REGISTRY" -u ci -p "$REGISTRY_PASSWORD"
docker push "$REGISTRY/app:latest"
