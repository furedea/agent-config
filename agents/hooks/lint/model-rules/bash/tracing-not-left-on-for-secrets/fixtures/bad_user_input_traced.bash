#!/usr/bin/env bash
set -euo pipefail

function create_account() {
  local _user="$1"
  local _password
  read -r -s -p "Password for $_user: " _password
  echo
  set -x
  htpasswd -b /etc/nginx/.htpasswd "$_user" "$_password"
  systemctl reload nginx
}

create_account "${1:?user is required}"
