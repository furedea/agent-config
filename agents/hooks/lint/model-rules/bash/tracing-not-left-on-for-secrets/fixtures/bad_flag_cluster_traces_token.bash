#!/usr/bin/env bash
set -euxo pipefail

readonly REGISTRY="registry.example.com"
readonly PASSWORD="${REGISTRY_PASSWORD:?REGISTRY_PASSWORD is required}"

printf '%s\n' "$PASSWORD" | docker login "$REGISTRY" --username deploy --password-stdin
docker push "$REGISTRY/app:latest"
