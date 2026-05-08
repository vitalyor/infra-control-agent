#!/usr/bin/env bash
set -euo pipefail

IPV6_ACTION="${IPV6_ACTION:-status}"   # status|enable|disable
CONF="/etc/sysctl.d/99-infra-control-agent-ipv6.conf"

print_status() {
  echo "net.ipv6.conf.all.disable_ipv6=$(sysctl -n net.ipv6.conf.all.disable_ipv6 2>/dev/null || echo unknown)"
  echo "net.ipv6.conf.default.disable_ipv6=$(sysctl -n net.ipv6.conf.default.disable_ipv6 2>/dev/null || echo unknown)"
  echo "net.ipv6.conf.lo.disable_ipv6=$(sysctl -n net.ipv6.conf.lo.disable_ipv6 2>/dev/null || echo unknown)"
}

if [[ "${IPV6_ACTION}" == "status" ]]; then
  print_status
  exit 0
fi

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: ipv6 action=${IPV6_ACTION}"
  exit 0
fi

case "${IPV6_ACTION}" in
  enable)
    cat > "${CONF}" <<'EOF'
net.ipv6.conf.all.disable_ipv6=0
net.ipv6.conf.default.disable_ipv6=0
net.ipv6.conf.lo.disable_ipv6=0
EOF
    ;;
  disable)
    cat > "${CONF}" <<'EOF'
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1
net.ipv6.conf.lo.disable_ipv6=1
EOF
    ;;
  *)
    echo "unsupported IPV6_ACTION=${IPV6_ACTION}" >&2
    exit 2
    ;;
esac

sysctl --system >/dev/null
print_status
