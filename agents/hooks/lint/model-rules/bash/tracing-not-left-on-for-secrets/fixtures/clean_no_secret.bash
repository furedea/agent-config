#!/usr/bin/env bash
set -euo pipefail
if [[ "${TRACE-0}" == "1" ]]; then set -o xtrace; fi

readonly BUILD_DIR="build"

cmake -S . -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR" --parallel
ctest --test-dir "$BUILD_DIR" --output-on-failure
