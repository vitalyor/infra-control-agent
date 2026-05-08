#!/usr/bin/env bash
set -euo pipefail
ENABLE_BBR="${ENABLE_BBR:-}"
ENABLE_CAKE="${ENABLE_CAKE:-}"

if [[ -z "${ENABLE_BBR}" && -z "${ENABLE_CAKE}" ]]; then
  echo "ENABLE_BBR and/or ENABLE_CAKE must be provided" >&2
  exit 2
fi

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: bbr=${ENABLE_BBR:-skip} cake=${ENABLE_CAKE:-skip}"
  exit 0
fi

CONF=/etc/sysctl.d/99-infra-control-agent-net.conf
touch "${CONF}"

set_kv() {
  local key="$1" value="$2"
  if grep -q "^${key}\s*=" "${CONF}"; then
    sed -i -E "s|^${key}\s*=.*|${key} = ${value}|" "${CONF}"
  else
    echo "${key} = ${value}" >> "${CONF}"
  fi
}

if [[ -n "${ENABLE_BBR}" ]]; then
  if [[ "${ENABLE_BBR}" == "true" ]]; then
    set_kv net.ipv4.tcp_congestion_control bbr
  else
    set_kv net.ipv4.tcp_congestion_control cubic
  fi
fi

if [[ -n "${ENABLE_CAKE}" ]]; then
  if [[ "${ENABLE_CAKE}" == "true" ]]; then
    set_kv net.core.default_qdisc cake
  else
    set_kv net.core.default_qdisc fq_codel
  fi
fi

sysctl --system
echo "Network tuning applied"

