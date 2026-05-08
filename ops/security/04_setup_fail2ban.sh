#!/usr/bin/env bash
set -euo pipefail
F2B_ACTION="${F2B_ACTION:-install}" # install|start|stop|restart|enable|disable|config
F2B_BANTIME="${F2B_BANTIME:-30m}"
F2B_FINDTIME="${F2B_FINDTIME:-10m}"
F2B_MAXRETRY="${F2B_MAXRETRY:-10}"

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: fail2ban action=${F2B_ACTION}"
  exit 0
fi

case "${F2B_ACTION}" in
  install)
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get -y install fail2ban
    ;;
  start|stop|restart|enable|disable)
    systemctl "${F2B_ACTION}" fail2ban
    ;;
  config)
    mkdir -p /etc/fail2ban
    cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
bantime = ${F2B_BANTIME}
findtime = ${F2B_FINDTIME}
maxretry = ${F2B_MAXRETRY}
backend = systemd

[sshd]
enabled = true
port = ssh
filter = sshd
EOF
    systemctl restart fail2ban
    ;;
  *)
    echo "invalid F2B_ACTION" >&2
    exit 2
    ;;
esac

echo "Fail2ban operation completed"

