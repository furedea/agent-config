#!/usr/bin/env bash

readonly BUILD_DIR="build"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
make -C src install DESTDIR="$BUILD_DIR"
tar -czf dist.tar.gz -C "$BUILD_DIR" .
