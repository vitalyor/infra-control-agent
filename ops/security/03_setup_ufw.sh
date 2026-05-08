#!/usr/bin/env bash
set -euo pipefail
UFW_ACTION="${UFW_ACTION:-enable}"          # install|status|enable|disable|start|stop|restart|reset
UFW_RULE_ACTION="${UFW_RULE_ACTION:-}"      # optional: allow|deny|reject|limit|delete
UFW_RULE="${UFW_RULE:-}"                    # optional raw ufw rule
UFW_RULE_NUM="${UFW_RULE_NUM:-}"            # optional numbered rule for delete
UFW_PORT="${UFW_PORT:-}"                    # optional structured rule field
UFW_PROTO="${UFW_PROTO:-tcp}"               # optional structured rule field
UFW_FROM="${UFW_FROM:-}"                    # optional structured rule field
UFW_TO="${UFW_TO:-}"                        # optional structured rule field

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: ufw action=${UFW_ACTION} rule_action=${UFW_RULE_ACTION} rule=${UFW_RULE} num=${UFW_RULE_NUM} port=${UFW_PORT} proto=${UFW_PROTO} from=${UFW_FROM} to=${UFW_TO}"
  exit 0
fi

case "${UFW_ACTION}" in
  install)
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get -y install ufw
    systemctl enable ufw || true
    systemctl start ufw || true
    ;;
  status) ufw status verbose ;;
  enable) ufw --force enable ;;
  disable) ufw disable ;;
  start) systemctl start ufw ;;
  stop) systemctl stop ufw ;;
  restart) systemctl restart ufw ;;
  reset) ufw --force reset ;;
  *) echo "invalid UFW_ACTION" >&2; exit 2 ;;
esac

if [[ -n "${UFW_RULE_ACTION}" ]]; then
  if [[ "${UFW_RULE_ACTION}" == "delete" && -n "${UFW_RULE_NUM}" ]]; then
    ufw --force delete "${UFW_RULE_NUM}"
  elif [[ -n "${UFW_RULE}" ]]; then
    if [[ "${UFW_RULE_ACTION}" == "delete" ]]; then
      ufw --force delete ${UFW_RULE}
    else
      ufw "${UFW_RULE_ACTION}" ${UFW_RULE}
    fi
  elif [[ -n "${UFW_PORT}" ]]; then
    if [[ -n "${UFW_FROM}" ]]; then
      if [[ -n "${UFW_TO}" ]]; then
        ufw "${UFW_RULE_ACTION}" from "${UFW_FROM}" to "${UFW_TO}" port "${UFW_PORT}" proto "${UFW_PROTO}"
      else
        ufw "${UFW_RULE_ACTION}" from "${UFW_FROM}" to any port "${UFW_PORT}" proto "${UFW_PROTO}"
      fi
    elif [[ -n "${UFW_TO}" ]]; then
      ufw "${UFW_RULE_ACTION}" to "${UFW_TO}" port "${UFW_PORT}" proto "${UFW_PROTO}"
    else
      ufw "${UFW_RULE_ACTION}" "${UFW_PORT}/${UFW_PROTO}"
    fi
  else
    echo "rule_action provided but no rule/port/number specified" >&2
    exit 2
  fi
fi
echo "UFW operation completed"
