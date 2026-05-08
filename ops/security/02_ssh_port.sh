#!/usr/bin/env bash
set -euo pipefail
ACTION="${ACTION:-set}"   # set|add|remove
PORT="${PORT:-22}"
SSHD_CONFIG="${SSHD_CONFIG:-/etc/ssh/sshd_config}"

if ! [[ "${PORT}" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "DIAG_SSH_PORT_INVALID port=${PORT}" >&2
  echo "invalid PORT" >&2
  exit 2
fi
if [[ "${ACTION}" == "remove" && "${PORT}" == "22" ]]; then
  echo "DIAG_SSH_PORT_REMOVE22_DENIED" >&2
  echo "refusing to remove default SSH port 22" >&2
  exit 2
fi

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: ssh port action=${ACTION} port=${PORT}"
  exit 0
fi

cp "${SSHD_CONFIG}" "${SSHD_CONFIG}.bak.$(date +%s)"
case "${ACTION}" in
  set)
    grep -q '^Port ' "${SSHD_CONFIG}" && \
      sed -i -E "s/^#?Port\s+.*/Port ${PORT}/" "${SSHD_CONFIG}" || \
      echo "Port ${PORT}" >> "${SSHD_CONFIG}"
    ;;
  add)
    grep -q "^Port ${PORT}$" "${SSHD_CONFIG}" || echo "Port ${PORT}" >> "${SSHD_CONFIG}"
    ;;
  remove)
    sed -i -E "/^#?Port\s+${PORT}$/d" "${SSHD_CONFIG}"
    grep -q '^Port ' "${SSHD_CONFIG}" || echo "Port 22" >> "${SSHD_CONFIG}"
    ;;
  *)
    echo "DIAG_SSH_ACTION_UNSUPPORTED action=${ACTION}" >&2
    echo "invalid ACTION" >&2
    exit 2
    ;;
esac

mkdir -p /run/sshd
sshd -t
systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${PORT}/tcp" || true
fi
echo "SSH port action applied: ${ACTION} ${PORT}"
