#!/usr/bin/env bash
set -euo pipefail
echo "== load =="
uptime
echo
echo "== memory =="
free -h || true
echo
echo "== memory /proc =="
grep -E "MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree" /proc/meminfo || true
echo
echo "== top cpu =="
ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -n 20
echo
echo "== ip addr =="
ip addr || true
echo
echo "== ip route =="
ip route || true
