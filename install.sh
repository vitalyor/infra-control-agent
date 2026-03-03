#!/usr/bin/env bash
set -euo pipefail

REPO_URL_DEFAULT="https://github.com/your-org/infra-control-agent.git"
BRANCH_DEFAULT="main"
INSTALL_DIR_DEFAULT="/opt/infra-control-agent"

prompt() {
  local var_name="$1"
  local prompt_text="$2"
  local default_value="${3:-}"
  local secret="${4:-false}"
  local input=""

  if [[ "${secret}" == "true" ]]; then
    read -r -s -p "${prompt_text}${default_value:+ [${default_value}]}: " input
    echo
  else
    read -r -p "${prompt_text}${default_value:+ [${default_value}]}: " input
  fi
  if [[ -z "${input}" ]]; then
    input="${default_value}"
  fi
  printf -v "${var_name}" "%s" "${input}"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
}

echo "== Infra Control Agent installer =="
require_cmd git
require_cmd docker

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "docker compose (or docker-compose) is required" >&2
  exit 1
fi

NONINTERACTIVE="${INSTALL_NONINTERACTIVE:-false}"

prompt REPO_URL "GitHub repo URL" "${REPO_URL:-$REPO_URL_DEFAULT}"
prompt REPO_BRANCH "Git branch/tag" "${REPO_BRANCH:-$BRANCH_DEFAULT}"
prompt INSTALL_DIR "Install directory" "${INSTALL_DIR:-$INSTALL_DIR_DEFAULT}"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
  echo "Updating existing repo in ${INSTALL_DIR} ..."
  git -C "${INSTALL_DIR}" fetch --all --tags --prune
  git -C "${INSTALL_DIR}" checkout "${REPO_BRANCH}"
  git -C "${INSTALL_DIR}" pull --ff-only origin "${REPO_BRANCH}"
else
  if [[ -e "${INSTALL_DIR}" ]]; then
    echo "Directory exists but is not a git repo: ${INSTALL_DIR}" >&2
    exit 1
  fi
  echo "Cloning ${REPO_URL} (${REPO_BRANCH}) to ${INSTALL_DIR} ..."
  git clone --depth 1 --branch "${REPO_BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi

if [[ ! -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
  echo "docker-compose.yml not found in ${INSTALL_DIR}" >&2
  exit 1
fi

AGENT_ID_DEFAULT="$(hostname | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-._')"

if [[ "${NONINTERACTIVE}" == "1" || "${NONINTERACTIVE,,}" == "true" || "${NONINTERACTIVE,,}" == "yes" ]]; then
  CONTROL_API_URL="${CONTROL_API_URL:-}"
  AGENT_ENROLL_TOKEN="${AGENT_ENROLL_TOKEN:-}"
  AGENT_NODE_UUID="${AGENT_NODE_UUID:-}"
  AGENT_ID="${AGENT_ID:-$AGENT_ID_DEFAULT}"
  AGENT_DISPLAY_NAME="${AGENT_DISPLAY_NAME:-$AGENT_ID_DEFAULT}"
  AGENT_VERIFY_TLS="${AGENT_VERIFY_TLS:-true}"
  if [[ -z "${CONTROL_API_URL}" || -z "${AGENT_ENROLL_TOKEN}" || -z "${AGENT_NODE_UUID}" ]]; then
    echo "For non-interactive install set: CONTROL_API_URL, AGENT_ENROLL_TOKEN, AGENT_NODE_UUID" >&2
    exit 1
  fi
else
  prompt CONTROL_API_URL "Control API URL (http://host:8090)" "${CONTROL_API_URL:-}"
  prompt AGENT_ENROLL_TOKEN "Agent enroll token" "${AGENT_ENROLL_TOKEN:-}" "true"
  prompt AGENT_NODE_UUID "Node UUID (target UUID for jobs)" "${AGENT_NODE_UUID:-}"
  prompt AGENT_ID "Agent ID" "${AGENT_ID:-$AGENT_ID_DEFAULT}"
  prompt AGENT_DISPLAY_NAME "Agent display name" "${AGENT_DISPLAY_NAME:-$AGENT_ID_DEFAULT}"
  prompt AGENT_VERIFY_TLS "Verify TLS (true/false)" "${AGENT_VERIFY_TLS:-true}"
fi

cat > "${INSTALL_DIR}/.env" <<EOF
CONTROL_API_URL=${CONTROL_API_URL}
AGENT_ID=${AGENT_ID}
AGENT_NODE_UUID=${AGENT_NODE_UUID}
AGENT_DISPLAY_NAME=${AGENT_DISPLAY_NAME}
AGENT_ENROLL_TOKEN=${AGENT_ENROLL_TOKEN}
AGENT_ACCESS_TOKEN=
AGENT_POLL_INTERVAL_S=8
AGENT_HEARTBEAT_INTERVAL_S=20
AGENT_STATE_PATH=/agent/data/state.json
AGENT_VERIFY_TLS=${AGENT_VERIFY_TLS}
EOF

echo "Starting agent with ${COMPOSE_CMD} ..."
(cd "${INSTALL_DIR}" && ${COMPOSE_CMD} up -d --build)

echo
echo "Installed successfully."
echo "Location: ${INSTALL_DIR}"
echo "Logs: (cd ${INSTALL_DIR} && ${COMPOSE_CMD} logs -f agent)"
