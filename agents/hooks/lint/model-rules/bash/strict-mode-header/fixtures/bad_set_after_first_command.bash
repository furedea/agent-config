#!/usr/bin/env bash

cd "$(dirname "$0")/.."
git submodule update --init --recursive

set -euo pipefail

./scripts/generate.sh
./scripts/test.sh
