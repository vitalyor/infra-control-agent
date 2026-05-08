#!/usr/bin/env bash
set -euo pipefail
SSHD_CONFIG="${SSHD_CONFIG:-/etc/ssh/sshd_config}"
DISABLE_PASSWORD_AUTH="${DISABLE_PASSWORD_AUTH:-true}"

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: harden ssh at ${SSHD_CONFIG}, disable_password_auth=${DISABLE_PASSWORD_AUTH}"
  exit 0
fi

cp "${SSHD_CONFIG}" "${SSHD_CONFIG}.bak.$(date +%s)"
if [[ "${DISABLE_PASSWORD_AUTH}" == "true" ]]; then
  grep -q '^PasswordAuthentication' "${SSHD_CONFIG}" && \
    sed -i -E 's/^#?PasswordAuthentication\s+.*/PasswordAuthentication no/' "${SSHD_CONFIG}" || \
    echo 'PasswordAuthentication no' >> "${SSHD_CONFIG}"
fi
grep -q '^PubkeyAuthentication' "${SSHD_CONFIG}" && \
  sed -i -E 's/^#?PubkeyAuthentication\s+.*/PubkeyAuthentication yes/' "${SSHD_CONFIG}" || \
  echo 'PubkeyAuthentication yes' >> "${SSHD_CONFIG}"
sshd -t
systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null
echo "SSH hardening applied"

