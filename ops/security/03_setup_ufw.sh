#!/usr/bin/env bash
set -euo pipefail
UFW_ACTION="${UFW_ACTION:-enable}" # install|enable|disable|start|stop|restart
UFW_RULE_ACTION="${UFW_RULE_ACTION:-}" # optional: allow|deny|reject|delete
UFW_RULE="${UFW_RULE:-}" # optional raw ufw rule

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: ufw action=${UFW_ACTION} rule_action=${UFW_RULE_ACTION} rule=${UFW_RULE}"
  exit 0
fi

case "${UFW_ACTION}" in
  install)
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get -y install ufw
    systemctl enable ufw || true
    systemctl start ufw || true
    ;;
  enable) ufw --force enable ;;
  disable) ufw disable ;;
  start) systemctl start ufw ;;
  stop) systemctl stop ufw ;;
  restart) systemctl restart ufw ;;
  *) echo "invalid UFW_ACTION" >&2; exit 2 ;;
esac

if [[ -n "${UFW_RULE_ACTION}" && -n "${UFW_RULE}" ]]; then
  if [[ "${UFW_RULE_ACTION}" == "delete" ]]; then
    ufw --force delete ${UFW_RULE}
  else
    ufw "${UFW_RULE_ACTION}" ${UFW_RULE}
  fi
fi
echo "UFW operation completed"

