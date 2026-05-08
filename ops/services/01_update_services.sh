#!/usr/bin/env bash
set -euo pipefail
MODE="${MODE:-pull}" # pull|rebuild
DIRS="${DIRS:-/opt/remnawave,/opt/remnanode,/opt/remnawave/subscription}"

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: services update mode=${MODE} dirs=${DIRS}"
  exit 0
fi

IFS=',' read -r -a arr <<< "${DIRS}"
count=0
for d in "${arr[@]}"; do
  d="$(echo "${d}" | xargs)"
  [[ -z "${d}" ]] && continue
  [[ ! -f "${d}/docker-compose.yml" ]] && continue
  count=$((count + 1))
  (
    cd "${d}"
    if [[ "${MODE}" == "rebuild" ]]; then
      docker compose build --no-cache
    else
      docker compose pull
    fi
    docker compose up -d
  )
done
if (( count == 0 )); then
  echo "no valid service dirs" >&2
  exit 2
fi
echo "Services updated: ${count}"

