#!/usr/bin/env bash
set -euo pipefail
FULL_UPDATE="${FULL_UPDATE:-false}"
if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: system update full=${FULL_UPDATE}"
  exit 0
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
if [[ "${FULL_UPDATE}" == "true" ]]; then
  DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade
  apt-get -y autoremove --purge
  apt-get clean
fi
echo "System update completed"

