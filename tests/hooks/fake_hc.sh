#!/usr/bin/env bash
set -euo pipefail
exec cat "${HC_TEST_DIRECTORY}/${1}-${2}.json"
