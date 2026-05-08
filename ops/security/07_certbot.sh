#!/usr/bin/env bash
set -euo pipefail

CERT_ACTION="${CERT_ACTION:-status}"     # status|renew|issue
CERT_METHOD="${CERT_METHOD:-http}"       # http|cloudflare
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"

status_all() {
  local d
  if [[ ! -d /etc/letsencrypt/live ]]; then
    echo "no certificates directory"
    return 0
  fi
  for d in /etc/letsencrypt/live/*; do
    [[ -d "${d}" ]] || continue
    local cert="${d}/fullchain.pem"
    [[ -f "${cert}" ]] || continue
    local name
    name="$(basename "${d}")"
    local end epoch now days
    end="$(openssl x509 -in "${cert}" -noout -enddate | sed 's/notAfter=//')"
    epoch="$(date -d "${end}" +%s 2>/dev/null || echo 0)"
    now="$(date +%s)"
    days=$(( (epoch - now) / 86400 ))
    echo "${name}: expires_in_days=${days}"
  done
}

if [[ "${CERT_ACTION}" == "status" ]]; then
  status_all
  exit 0
fi

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: certbot action=${CERT_ACTION} method=${CERT_METHOD} domain=${DOMAIN}"
  exit 0
fi

diagnose_certbot_failure() {
  local combined="${1:-}"
  if echo "${combined}" | grep -qi "too many certificates"; then
    echo "CERTBOT_DIAG=rate_limit_exact_set"
  elif echo "${combined}" | grep -qi "failed to authenticate"; then
    echo "CERTBOT_DIAG=auth_failed_http_or_dns"
  elif echo "${combined}" | grep -qi "connection refused"; then
    echo "CERTBOT_DIAG=port_80_unreachable_or_blocked"
  elif echo "${combined}" | grep -qi "no start line"; then
    echo "CERTBOT_DIAG=invalid_pem_content"
  else
    echo "CERTBOT_DIAG=unknown"
  fi
  [[ -f /var/log/letsencrypt/letsencrypt.log ]] && tail -n 60 /var/log/letsencrypt/letsencrypt.log || true
}

run_cmd_with_diag() {
  set +e
  local output
  output="$("$@" 2>&1)"
  local rc=$?
  set -e
  echo "${output}"
  if [[ ${rc} -ne 0 ]]; then
    diagnose_certbot_failure "${output}"
    exit ${rc}
  fi
}

command -v certbot >/dev/null 2>&1 || { echo "DIAG_CERTBOT_NOT_INSTALLED" >&2; echo "certbot not installed" >&2; exit 2; }

case "${CERT_ACTION}" in
  renew)
    run_cmd_with_diag certbot renew --quiet
    status_all
    ;;
  issue)
    [[ -n "${DOMAIN}" ]] || { echo "DIAG_CERTBOT_DOMAIN_REQUIRED" >&2; echo "DOMAIN is required for issue" >&2; exit 2; }
    [[ -n "${EMAIL}" ]] || { echo "DIAG_CERTBOT_EMAIL_REQUIRED" >&2; echo "EMAIL is required for issue" >&2; exit 2; }
    if [[ "${CERT_METHOD}" == "cloudflare" ]]; then
      [[ -n "${CLOUDFLARE_API_TOKEN}" ]] || { echo "DIAG_CERTBOT_CF_TOKEN_REQUIRED" >&2; echo "CLOUDFLARE_API_TOKEN is required for cloudflare method" >&2; exit 2; }
      mkdir -p /root/.secrets/certbot
      cat > /root/.secrets/certbot/cloudflare.ini <<EOF
dns_cloudflare_api_token = ${CLOUDFLARE_API_TOKEN}
EOF
      chmod 600 /root/.secrets/certbot/cloudflare.ini
      run_cmd_with_diag certbot certonly --non-interactive --agree-tos --email "${EMAIL}" \
        --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/certbot/cloudflare.ini \
        --dns-cloudflare-propagation-seconds 60 -d "${DOMAIN}"
    else
      run_cmd_with_diag certbot certonly --non-interactive --agree-tos --email "${EMAIL}" --standalone -d "${DOMAIN}"
    fi
    status_all
    ;;
  *)
    echo "DIAG_CERTBOT_ACTION_UNSUPPORTED action=${CERT_ACTION}" >&2
    echo "unsupported CERT_ACTION=${CERT_ACTION}" >&2
    exit 2
    ;;
esac
