#!/usr/bin/env bash
set -euo pipefail

AGENT_STACK_DIR="${AGENT_STACK_DIR:-/opt/infragent}"
UPDATE_DELAY_SEC="${UPDATE_DELAY_SEC:-2}"
AGENT_SERVICE_NAME="${AGENT_SERVICE_NAME:-agent}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-infra-control-agent}"

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: agent self-update dir=${AGENT_STACK_DIR} delay=${UPDATE_DELAY_SEC}s"
  exit 0
fi

[[ -d "${AGENT_STACK_DIR}" ]] || { echo "DIAG_AGENT_UPDATE_DIR_NOT_FOUND dir=${AGENT_STACK_DIR}" >&2; exit 2; }
[[ -f "${AGENT_STACK_DIR}/docker-compose.yml" ]] || { echo "DIAG_AGENT_UPDATE_COMPOSE_MISSING dir=${AGENT_STACK_DIR}" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || { echo "DIAG_AGENT_UPDATE_DOCKER_MISSING" >&2; exit 2; }
if [[ -z "${AGENT_SERVICE_NAME}" ]]; then
  echo "DIAG_AGENT_UPDATE_SERVICE_INVALID" >&2
  exit 2
fi
if [[ -z "${AGENT_CONTAINER_NAME}" ]]; then
  echo "DIAG_AGENT_UPDATE_CONTAINER_INVALID" >&2
  exit 2
fi

if ! [[ "${UPDATE_DELAY_SEC}" =~ ^[0-9]+$ ]]; then
  echo "DIAG_AGENT_UPDATE_DELAY_INVALID delay=${UPDATE_DELAY_SEC}" >&2
  exit 2
fi

UPDATE_CMD="sleep ${UPDATE_DELAY_SEC}; \
cd '${AGENT_STACK_DIR}' && \
echo '[self-update] start' && \
docker rm -f '${AGENT_CONTAINER_NAME}' >/dev/null 2>&1 || true; \
docker compose rm -sf '${AGENT_SERVICE_NAME}' >/dev/null 2>&1 || true; \
docker compose up -d --build --force-recreate --remove-orphans '${AGENT_SERVICE_NAME}' && \
docker compose ps && \
echo '[self-update] done'"

if command -v systemd-run >/dev/null 2>&1; then
  unit="infra-agent-self-update-$(date +%s)"
  systemd-run --unit "${unit}" --collect /bin/bash -lc "${UPDATE_CMD}" >/tmp/infra-agent-self-update.log 2>&1 || {
    echo "DIAG_AGENT_UPDATE_SYSTEMDRUN_FAILED" >&2
    exit 2
  }
else
  nohup /bin/bash -lc "${UPDATE_CMD}" >/tmp/infra-agent-self-update.log 2>&1 &
fi
echo "Agent self-update scheduled: dir=${AGENT_STACK_DIR} delay=${UPDATE_DELAY_SEC}s log=/tmp/infra-agent-self-update.log"
