#!/usr/bin/env bash
# Regenerates the fixtures that live next to this script.
set -euo pipefail

cd "$(dirname "$0")"

rm -rf generated
mkdir generated
python3 generate.py --out generated
