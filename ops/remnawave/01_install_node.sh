#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-}"
NODE_PORT="${NODE_PORT:-2222}"
NODE_SECRET_KEY="${NODE_SECRET_KEY:-}"
WEB_SERVER="${WEB_SERVER:-nginx}"                  # nginx|caddy
CERT_METHOD="${CERT_METHOD:-none}"                 # none|http|cloudflare
CERT_DOMAIN="${CERT_DOMAIN:-}"
CERT_EMAIL="${CERT_EMAIL:-}"
CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
TEMPLATE_SOURCE="${TEMPLATE_SOURCE:-builtin}"      # builtin|url
COMPOSE_TEMPLATE_URL="${COMPOSE_TEMPLATE_URL:-}"
WEB_TEMPLATE_URL="${WEB_TEMPLATE_URL:-}"

BASE_DIR="/opt/remnanode"
WWW_DIR="/var/www/html"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TPL_DIR="${SCRIPT_DIR}/templates"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "required command not found: $1" >&2; exit 2; }; }

[[ -n "${DOMAIN}" ]] || { echo "DOMAIN is required" >&2; exit 2; }
[[ -n "${NODE_SECRET_KEY}" ]] || { echo "NODE_SECRET_KEY is required" >&2; exit 2; }
[[ "${WEB_SERVER}" == "nginx" || "${WEB_SERVER}" == "caddy" ]] || { echo "WEB_SERVER must be nginx or caddy" >&2; exit 2; }
[[ "${CERT_METHOD}" == "none" || "${CERT_METHOD}" == "http" || "${CERT_METHOD}" == "cloudflare" ]] || { echo "CERT_METHOD must be none|http|cloudflare" >&2; exit 2; }
[[ "${TEMPLATE_SOURCE}" == "builtin" || "${TEMPLATE_SOURCE}" == "url" ]] || { echo "TEMPLATE_SOURCE must be builtin|url" >&2; exit 2; }

if [[ -z "${CERT_DOMAIN}" ]]; then
  CERT_DOMAIN="${DOMAIN}"
fi

if [[ "${CERT_METHOD}" != "none" ]]; then
  [[ -n "${CERT_EMAIL}" ]] || { echo "CERT_EMAIL is required when CERT_METHOD!=none" >&2; exit 2; }
  if [[ "${CERT_METHOD}" == "cloudflare" ]]; then
    [[ -n "${CLOUDFLARE_API_TOKEN}" ]] || { echo "CLOUDFLARE_API_TOKEN is required for cloudflare method" >&2; exit 2; }
  fi
fi

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: install node domain=${DOMAIN} cert_domain=${CERT_DOMAIN} web=${WEB_SERVER} cert=${CERT_METHOD} tpl=${TEMPLATE_SOURCE}"
  exit 0
fi

need_cmd docker
need_cmd bash
need_cmd sed

mkdir -p "${BASE_DIR}" "${WWW_DIR}"

compose_tpl=""
web_tpl=""
if [[ "${WEB_SERVER}" == "nginx" ]]; then
  compose_tpl="${TPL_DIR}/docker-compose.nginx.yml.tpl"
  web_tpl="${TPL_DIR}/nginx.conf.tpl"
else
  compose_tpl="${TPL_DIR}/docker-compose.caddy.yml.tpl"
  web_tpl="${TPL_DIR}/Caddyfile.tpl"
fi

if [[ "${TEMPLATE_SOURCE}" == "url" ]]; then
  need_cmd curl
  [[ -n "${COMPOSE_TEMPLATE_URL}" ]] || { echo "COMPOSE_TEMPLATE_URL is required for TEMPLATE_SOURCE=url" >&2; exit 2; }
  [[ -n "${WEB_TEMPLATE_URL}" ]] || { echo "WEB_TEMPLATE_URL is required for TEMPLATE_SOURCE=url" >&2; exit 2; }
  curl -fsSL "${COMPOSE_TEMPLATE_URL}" -o "${BASE_DIR}/docker-compose.yml.tpl"
  if [[ "${WEB_SERVER}" == "nginx" ]]; then
    curl -fsSL "${WEB_TEMPLATE_URL}" -o "${BASE_DIR}/nginx.conf.tpl"
  else
    curl -fsSL "${WEB_TEMPLATE_URL}" -o "${BASE_DIR}/Caddyfile.tpl"
  fi
  compose_tpl="${BASE_DIR}/docker-compose.yml.tpl"
  web_tpl="${BASE_DIR}/$( [[ "${WEB_SERVER}" == "nginx" ]] && echo "nginx.conf.tpl" || echo "Caddyfile.tpl" )"
fi

cp "${compose_tpl}" "${BASE_DIR}/docker-compose.yml"
if [[ "${WEB_SERVER}" == "nginx" ]]; then
  cp "${web_tpl}" "${BASE_DIR}/nginx.conf"
else
  cp "${web_tpl}" "${BASE_DIR}/Caddyfile"
fi

# Render placeholders in templates.
sed -i \
  -e "s|__DOMAIN__|${DOMAIN}|g" \
  -e "s|__CERT_DOMAIN__|${CERT_DOMAIN}|g" \
  -e "s|__NODE_PORT__|${NODE_PORT}|g" \
  -e "s|__NODE_SECRET_KEY__|${NODE_SECRET_KEY}|g" \
  "${BASE_DIR}/docker-compose.yml"

if [[ "${WEB_SERVER}" == "nginx" ]]; then
  sed -i -e "s|__DOMAIN__|${DOMAIN}|g" "${BASE_DIR}/nginx.conf"
else
  sed -i -e "s|__DOMAIN__|${DOMAIN}|g" "${BASE_DIR}/Caddyfile"
fi

cat > "${WWW_DIR}/index.html" <<'EOF'
<!doctype html><html><head><meta charset="utf-8"><title>Service is running</title></head><body><h1>Service is running</h1></body></html>
EOF

if [[ "${CERT_METHOD}" != "none" ]]; then
  if [[ "${CERT_METHOD}" == "http" ]]; then
    tmp_compose="/tmp/infra-agent-certbot-http.yml"
    cat > "${tmp_compose}" <<EOF
services:
  certbot:
    image: certbot/certbot:latest
    network_mode: host
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt
      - /var/lib/letsencrypt:/var/lib/letsencrypt
    entrypoint: ["certbot"]
EOF
    docker compose -f "${tmp_compose}" run --rm certbot \
      certonly --non-interactive --agree-tos --standalone \
      --email "${CERT_EMAIL}" -d "${CERT_DOMAIN}"
    rm -f "${tmp_compose}"
  else
    need_cmd certbot
    mkdir -p /root/.secrets/certbot
    cat > /root/.secrets/certbot/cloudflare.ini <<EOF
dns_cloudflare_api_token = ${CLOUDFLARE_API_TOKEN}
EOF
    chmod 600 /root/.secrets/certbot/cloudflare.ini
    certbot certonly --non-interactive --agree-tos --email "${CERT_EMAIL}" \
      --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/certbot/cloudflare.ini \
      --dns-cloudflare-propagation-seconds 60 -d "${CERT_DOMAIN}"
  fi
fi

cd "${BASE_DIR}"
docker compose up -d
echo "Remnawave node installed: domain=${DOMAIN} web=${WEB_SERVER} cert=${CERT_METHOD} dir=${BASE_DIR}"
