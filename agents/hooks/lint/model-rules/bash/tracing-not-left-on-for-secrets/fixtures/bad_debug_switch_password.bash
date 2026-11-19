#!/usr/bin/env bash
set -euo pipefail
if [[ "${TRACE-0}" == "1" ]]; then set -o xtrace; fi

readonly DB_HOST="${DB_HOST:-localhost}"
readonly DB_PASSWORD="${DB_PASSWORD:?DB_PASSWORD is required}"

mysqldump -h "$DB_HOST" -u backup -p"$DB_PASSWORD" app >backup.sql
gzip -f backup.sql
