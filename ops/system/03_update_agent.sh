#!/usr/bin/env bash
set -euo pipefail

AGENT_STACK_DIR="${AGENT_STACK_DIR:-/opt/infragent}"
UPDATE_DELAY_SEC="${UPDATE_DELAY_SEC:-2}"

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: agent self-update dir=${AGENT_STACK_DIR} delay=${UPDATE_DELAY_SEC}s"
  exit 0
fi

[[ -d "${AGENT_STACK_DIR}" ]] || { echo "DIAG_AGENT_UPDATE_DIR_NOT_FOUND dir=${AGENT_STACK_DIR}" >&2; exit 2; }
[[ -f "${AGENT_STACK_DIR}/docker-compose.yml" ]] || { echo "DIAG_AGENT_UPDATE_COMPOSE_MISSING dir=${AGENT_STACK_DIR}" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || { echo "DIAG_AGENT_UPDATE_DOCKER_MISSING" >&2; exit 2; }

if ! [[ "${UPDATE_DELAY_SEC}" =~ ^[0-9]+$ ]]; then
  echo "DIAG_AGENT_UPDATE_DELAY_INVALID delay=${UPDATE_DELAY_SEC}" >&2
  exit 2
fi

nohup /bin/bash -lc "sleep ${UPDATE_DELAY_SEC}; cd '${AGENT_STACK_DIR}' && docker compose up -d --build --force-recreate --remove-orphans" >/tmp/infra-agent-self-update.log 2>&1 &
echo "Agent self-update scheduled: dir=${AGENT_STACK_DIR} delay=${UPDATE_DELAY_SEC}s log=/tmp/infra-agent-self-update.log"
