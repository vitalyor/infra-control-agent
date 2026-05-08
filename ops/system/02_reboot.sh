#!/usr/bin/env bash
set -euo pipefail

REBOOT_DELAY_SEC="${REBOOT_DELAY_SEC:-2}"
REBOOT_MODE="${REBOOT_MODE:-hard}"                  # hard|soft
REBOOT_WAIT_TIMEOUT_SEC="${REBOOT_WAIT_TIMEOUT_SEC:-600}"
REBOOT_POLL_SEC="${REBOOT_POLL_SEC:-5}"

is_int() { [[ "$1" =~ ^[0-9]+$ ]]; }

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: reboot host mode=${REBOOT_MODE} delay=${REBOOT_DELAY_SEC}s wait_timeout=${REBOOT_WAIT_TIMEOUT_SEC}s poll=${REBOOT_POLL_SEC}s"
  exit 0
fi

if ! is_int "${REBOOT_DELAY_SEC}"; then
  echo "REBOOT_DELAY_SEC must be integer seconds >= 0" >&2
  exit 2
fi
if ! is_int "${REBOOT_WAIT_TIMEOUT_SEC}"; then
  echo "REBOOT_WAIT_TIMEOUT_SEC must be integer seconds >= 0" >&2
  exit 2
fi
if ! is_int "${REBOOT_POLL_SEC}" || [[ "${REBOOT_POLL_SEC}" == "0" ]]; then
  echo "REBOOT_POLL_SEC must be integer seconds > 0" >&2
  exit 2
fi
if [[ "${REBOOT_MODE}" != "hard" && "${REBOOT_MODE}" != "soft" ]]; then
  echo "REBOOT_MODE must be hard or soft" >&2
  exit 2
fi

if [[ "${REBOOT_MODE}" == "soft" ]]; then
  command -v curl >/dev/null 2>&1 || { echo "curl is required for soft reboot mode" >&2; exit 2; }
  AGENT_PORT="${AGENT_HTTP_PORT:-8091}"
  AUTH_HEADER=()
  if [[ -n "${AGENT_API_TOKEN:-}" ]]; then
    AUTH_HEADER=(-H "Authorization: Bearer ${AGENT_API_TOKEN}")
  fi

  started_ts="$(date +%s)"
  while true; do
    actions_json="$(curl -fsS "${AUTH_HEADER[@]}" "http://127.0.0.1:${AGENT_PORT}/v1/actions" || true)"
    running_count="$(printf '%s' "${actions_json}" | grep -Eo '"status": "(queued|running)"' | wc -l | tr -d ' ')"
    # Exclude current reboot job itself.
    active_other=0
    if [[ "${running_count}" -gt 1 ]]; then
      active_other=$((running_count - 1))
    fi
    if [[ "${active_other}" -le 0 ]]; then
      echo "Soft reboot: no active jobs, proceeding"
      break
    fi
    now_ts="$(date +%s)"
    elapsed=$((now_ts - started_ts))
    if [[ "${elapsed}" -ge "${REBOOT_WAIT_TIMEOUT_SEC}" ]]; then
      echo "Soft reboot timeout reached (${REBOOT_WAIT_TIMEOUT_SEC}s), forcing reboot"
      break
    fi
    echo "Soft reboot: waiting active jobs=${active_other}, elapsed=${elapsed}s"
    sleep "${REBOOT_POLL_SEC}"
  done
fi

# Trigger reboot asynchronously so caller gets immediate response.
nohup /bin/bash -lc "sleep ${REBOOT_DELAY_SEC}; systemctl reboot || reboot" >/dev/null 2>&1 &
echo "Host reboot scheduled mode=${REBOOT_MODE} in ${REBOOT_DELAY_SEC}s"
