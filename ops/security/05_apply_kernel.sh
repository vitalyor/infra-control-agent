#!/usr/bin/env bash
set -euo pipefail
if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: apply kernel hardening"
  exit 0
fi
cat > /etc/sysctl.d/99-infra-control-agent-kernel.conf <<'EOF'
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
EOF
sysctl --system
echo "Kernel hardening applied"

