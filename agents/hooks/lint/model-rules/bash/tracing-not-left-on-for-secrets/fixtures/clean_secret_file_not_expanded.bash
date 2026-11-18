#!/usr/bin/env bash
set -euo pipefail
set -o xtrace

readonly KEY_FILE="${HOME}/.config/app/deploy_key"

ssh -i "$KEY_FILE" deploy@app.example.com 'systemctl restart app'
ssh -i "$KEY_FILE" deploy@app.example.com 'systemctl is-active app'
