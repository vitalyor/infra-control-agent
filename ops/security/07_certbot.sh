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

command -v certbot >/dev/null 2>&1 || { echo "certbot not installed" >&2; exit 2; }

case "${CERT_ACTION}" in
  renew)
    certbot renew --quiet
    status_all
    ;;
  issue)
    [[ -n "${DOMAIN}" ]] || { echo "DOMAIN is required for issue" >&2; exit 2; }
    [[ -n "${EMAIL}" ]] || { echo "EMAIL is required for issue" >&2; exit 2; }
    if [[ "${CERT_METHOD}" == "cloudflare" ]]; then
      [[ -n "${CLOUDFLARE_API_TOKEN}" ]] || { echo "CLOUDFLARE_API_TOKEN is required for cloudflare method" >&2; exit 2; }
      mkdir -p /root/.secrets/certbot
      cat > /root/.secrets/certbot/cloudflare.ini <<EOF
dns_cloudflare_api_token = ${CLOUDFLARE_API_TOKEN}
EOF
      chmod 600 /root/.secrets/certbot/cloudflare.ini
      certbot certonly --non-interactive --agree-tos --email "${EMAIL}" \
        --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/certbot/cloudflare.ini \
        --dns-cloudflare-propagation-seconds 60 -d "${DOMAIN}"
    else
      certbot certonly --non-interactive --agree-tos --email "${EMAIL}" --standalone -d "${DOMAIN}"
    fi
    status_all
    ;;
  *)
    echo "unsupported CERT_ACTION=${CERT_ACTION}" >&2
    exit 2
    ;;
esac
