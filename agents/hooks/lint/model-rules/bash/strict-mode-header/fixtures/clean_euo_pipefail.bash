#!/usr/bin/env bash
set -euo pipefail

readonly BUILD_DIR="build"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
make -C src install DESTDIR="$BUILD_DIR"
