#!/usr/bin/env bash
set -euo pipefail

STACK="${STACK:-auto}"            # auto|panel|node
ACTION="${ACTION:-status}"        # status|start|stop|restart|update|logs
SERVICE="${SERVICE:-}"            # optional docker compose service name
LOG_LINES="${LOG_LINES:-200}"

resolve_dir() {
  case "${STACK}" in
    panel) echo "/opt/remnawave" ;;
    node) echo "/opt/remnanode" ;;
    auto)
      if [[ -d "/opt/remnawave" ]]; then
        echo "/opt/remnawave"
      elif [[ -d "/opt/remnanode" ]]; then
        echo "/opt/remnanode"
      else
        return 1
      fi
      ;;
    *) return 1 ;;
  esac
}

DIR="$(resolve_dir)" || { echo "stack dir not found for STACK=${STACK}" >&2; exit 2; }
[[ -f "${DIR}/docker-compose.yml" ]] || { echo "docker-compose.yml not found in ${DIR}" >&2; exit 2; }

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: remnawave stack action=${ACTION} stack=${STACK} dir=${DIR} service=${SERVICE} lines=${LOG_LINES}"
  exit 0
fi

cd "${DIR}"
case "${ACTION}" in
  status)
    docker compose ps
    ;;
  start)
    if [[ -n "${SERVICE}" ]]; then
      docker compose up -d "${SERVICE}"
    else
      docker compose up -d
    fi
    ;;
  stop)
    if [[ -n "${SERVICE}" ]]; then
      docker compose stop "${SERVICE}"
    else
      docker compose down
    fi
    ;;
  restart)
    if [[ -n "${SERVICE}" ]]; then
      docker compose restart "${SERVICE}"
    else
      docker compose down
      docker compose up -d
    fi
    ;;
  update)
    docker compose pull
    if [[ -n "${SERVICE}" ]]; then
      docker compose up -d "${SERVICE}"
    else
      docker compose up -d
    fi
    docker image prune -f >/dev/null 2>&1 || true
    ;;
  logs)
    if [[ -n "${SERVICE}" ]]; then
      docker compose logs --tail "${LOG_LINES}" "${SERVICE}"
    else
      docker compose logs --tail "${LOG_LINES}"
    fi
    ;;
  *)
    echo "unsupported ACTION=${ACTION}" >&2
    exit 2
    ;;
esac

echo "OK: action=${ACTION} stack=${STACK} dir=${DIR}"
