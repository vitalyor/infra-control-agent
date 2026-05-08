#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${DOCKER_CONTAINER:-}"
LINES="${LOG_LINES:-300}"
SINCE="${LOG_SINCE:-}"
TIMESTAMPS="${LOG_TIMESTAMPS:-false}"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "required command not found: $1" >&2; exit 2; }; }

need_cmd docker

if [[ -z "${CONTAINER}" ]]; then
  echo "DIAG_DOCKER_CONTAINER_REQUIRED" >&2
  exit 2
fi

if ! [[ "${LINES}" =~ ^[0-9]+$ ]]; then
  LINES=300
fi

if (( LINES < 1 )); then
  LINES=1
fi
if (( LINES > 5000 )); then
  LINES=5000
fi

if ! docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER}"; then
  echo "DIAG_DOCKER_CONTAINER_NOT_FOUND container=${CONTAINER}" >&2
  exit 1
fi

args=(logs --tail "${LINES}")
if [[ "${TIMESTAMPS}" == "true" ]]; then
  args+=(--timestamps)
fi
if [[ -n "${SINCE}" ]]; then
  args+=(--since "${SINCE}")
fi
args+=("${CONTAINER}")

docker "${args[@]}"
