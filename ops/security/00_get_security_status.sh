#!/usr/bin/env bash
set -euo pipefail
echo "== ssh =="
systemctl is-active sshd 2>/dev/null || systemctl is-active ssh 2>/dev/null || true
echo
echo "== ufw =="
if command -v ufw >/dev/null 2>&1; then
  ufw status verbose || true
else
  echo "ufw not installed"
fi
echo
echo "== fail2ban =="
if command -v fail2ban-client >/dev/null 2>&1; then
  fail2ban-client status || true
else
  echo "fail2ban not installed"
fi

