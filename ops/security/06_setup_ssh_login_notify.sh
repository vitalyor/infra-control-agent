#!/usr/bin/env bash
set -euo pipefail
TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-}"

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: setup ssh login notify"
  exit 0
fi

if [[ -z "${TOKEN}" || -z "${CHAT_ID}" ]]; then
  echo "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required" >&2
  exit 2
fi

cat > /etc/profile.d/ssh-login-notify.sh <<'EOF'
#!/usr/bin/env bash
if [[ -n "${SSH_CONNECTION:-}" ]]; then
  HOST="$(hostname)"
  USER_NAME="$(whoami)"
  IP="$(echo "${SSH_CONNECTION}" | awk '{print $1}')"
  MSG="SSH login on ${HOST}: user=${USER_NAME}, ip=${IP}"
  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    -d text="${MSG}" >/dev/null 2>&1 || true
fi
EOF
chmod +x /etc/profile.d/ssh-login-notify.sh
echo "SSH login notify configured"

