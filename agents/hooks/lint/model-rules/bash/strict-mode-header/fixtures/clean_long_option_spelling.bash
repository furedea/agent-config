#!/usr/bin/env bash
set -o errexit -o nounset -o pipefail
shopt -s nullglob

for archive in incoming/*.tar.gz; do
  tar -xzf "$archive" -C staging/
done
