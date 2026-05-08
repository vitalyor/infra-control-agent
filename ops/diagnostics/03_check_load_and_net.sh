#!/usr/bin/env bash
set -euo pipefail
echo "== load =="
uptime
echo
echo "== top cpu =="
ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -n 20
echo
echo "== ip addr =="
ip addr || true
echo
echo "== ip route =="
ip route || true

