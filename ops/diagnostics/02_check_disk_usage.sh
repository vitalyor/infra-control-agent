#!/usr/bin/env bash
set -euo pipefail
echo "== disk usage =="
df -h /
echo
echo "== top /var dirs =="
du -xh --max-depth=1 /var 2>/dev/null | sort -hr | head -n 20 || true

