#!/usr/bin/env bash
set -euo pipefail
exec cat "${HERDR_TEST_DIRECTORY}/${1}s.json"
