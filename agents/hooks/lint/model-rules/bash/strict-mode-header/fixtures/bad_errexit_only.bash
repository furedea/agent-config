#!/usr/bin/env bash
set -e

readonly LOG_FILE="deploy.log"

git pull --ff-only | tee -a "$LOG_FILE"
npm ci | tee -a "$LOG_FILE"
npm run build | tee -a "$LOG_FILE"
