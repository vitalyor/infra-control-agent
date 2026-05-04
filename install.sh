#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/infragent}"
REPO_URL="${REPO_URL:-https://github.com/vitalyor/infra-control-agent.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
DEFAULT_PORT="${AGENT_HTTP_PORT:-8091}"

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    return 1
  fi
}

detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return 0
  fi
  return 1
}

write_compose_template() {
  local compose_path="$1"
  if [[ -f "${compose_path}" ]]; then
    echo "docker-compose.yml already exists, keeping it: ${compose_path}"
    return 0
  fi

  cat > "${compose_path}" <<EOF
name: infra-control-agent

services:
  agent:
    build:
      context: ${REPO_URL}#${REPO_BRANCH}
      dockerfile: Dockerfile
    container_name: infra-control-agent
    restart: unless-stopped
    privileged: true
    network_mode: host
    pid: host
    environment:
      AGENT_ID: infra-control-agent
      AGENT_API_TOKEN: paste-token-from-panel
      AGENT_HTTP_PORT: ${DEFAULT_PORT}
      AGENT_LOG_LEVEL: warning
      AGENT_ACCESS_LOG: "false"
      AGENT_ALLOWED_UPGRADES: panel,node,subscription
      AGENT_JOB_MAX_COUNT: 20
      AGENT_JOB_MAX_AGE_S: 3600
      AGENT_MAX_ACTIVE_JOBS: 2
      AGENT_MAX_BODY_BYTES: 65536
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /opt:/host/opt:rw
      - /etc/sysctl.d:/host/etc/sysctl.d:rw
      - /proc:/host/proc:ro
      - infra-control-agent-data:/agent/data

volumes:
  infra-control-agent-data:
EOF
  echo "Created compose template: ${compose_path}"
}

echo "== Infra Control Agent bootstrap =="

require_cmd docker || {
  echo
  echo "Install Docker first, then run this script again:"
  echo "  curl -fsSL https://get.docker.com | sh"
  exit 1
}

COMPOSE_CMD="$(detect_compose)" || {
  echo "docker compose or docker-compose is required" >&2
  exit 1
}

mkdir -p "${INSTALL_DIR}"
write_compose_template "${INSTALL_DIR}/docker-compose.yml"

cat <<EOF

Bootstrap finished.

Next steps:
  1. cd ${INSTALL_DIR}
  2. nano docker-compose.yml
  3. Replace AGENT_API_TOKEN with the token generated in the panel/bot.
  4. Change AGENT_HTTP_PORT if the panel generated another port.
  5. Open the port if UFW is enabled:
     sudo ufw status | grep -qw active && sudo ufw allow ${DEFAULT_PORT}/tcp || true
  6. Start the agent:
     ${COMPOSE_CMD} up -d --build && ${COMPOSE_CMD} logs -f -t

Healthcheck:
  curl -sS http://127.0.0.1:${DEFAULT_PORT}/health
EOF
