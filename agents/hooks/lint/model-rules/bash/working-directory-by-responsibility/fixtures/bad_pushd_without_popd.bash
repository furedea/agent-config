#!/usr/bin/env bash
# Builds the project in the current directory with the templates shipped next to this script.
set -euo pipefail

pushd "$(dirname "$0")" >/dev/null
cp templates/Makefile.in ./Makefile.in
make -f Makefile.in build
