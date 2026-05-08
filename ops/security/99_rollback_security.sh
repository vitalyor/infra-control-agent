#!/usr/bin/env bash
set -euo pipefail
if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: rollback security"
  exit 0
fi

SSHD_CONFIG="/etc/ssh/sshd_config"
if [[ -f "${SSHD_CONFIG}" ]]; then
  grep -q '^PasswordAuthentication' "${SSHD_CONFIG}" && \
    sed -i -E 's/^#?PasswordAuthentication\s+.*/PasswordAuthentication yes/' "${SSHD_CONFIG}" || \
    echo 'PasswordAuthentication yes' >> "${SSHD_CONFIG}"
  sshd -t || true
fi
systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || true
ufw disable || true
systemctl stop fail2ban 2>/dev/null || true
systemctl disable fail2ban 2>/dev/null || true
echo "Security rollback completed"

