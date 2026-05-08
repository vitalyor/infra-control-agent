#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${DOCKER_CONTAINER:-}"
ACTION="${DOCKER_ACTION:-}"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "required command not found: $1" >&2; exit 2; }; }

need_cmd docker

if [[ -z "${CONTAINER}" ]]; then
  echo "DIAG_DOCKER_CONTAINER_REQUIRED" >&2
  exit 2
fi

case "${ACTION}" in
  start|stop|restart) ;;
  *)
    echo "DIAG_DOCKER_ACTION_UNSUPPORTED action=${ACTION}" >&2
    exit 2
    ;;
esac

if ! docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER}"; then
  echo "DIAG_DOCKER_CONTAINER_NOT_FOUND container=${CONTAINER}" >&2
  exit 1
fi

docker "${ACTION}" "${CONTAINER}"
docker ps -a --filter "name=^${CONTAINER}$" --format '{{json .}}'
