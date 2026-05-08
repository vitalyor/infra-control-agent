#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-}"
NODE_PORT="${NODE_PORT:-2222}"
NODE_SECRET_KEY="${NODE_SECRET_KEY:-}"
WEB_SERVER="${WEB_SERVER:-nginx}"                  # nginx|caddy
CERT_METHOD="${CERT_METHOD:-none}"                 # none|http|cloudflare
CERT_DOMAIN="${CERT_DOMAIN:-}"
CERT_EMAIL="${CERT_EMAIL:-}"
CERT_FORCE_RENEWAL="${CERT_FORCE_RENEWAL:-true}"   # true|false
CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
TEMPLATE_SOURCE="${TEMPLATE_SOURCE:-builtin}"      # builtin|url
COMPOSE_TEMPLATE_URL="${COMPOSE_TEMPLATE_URL:-}"
WEB_TEMPLATE_URL="${WEB_TEMPLATE_URL:-}"
UFW_AUTO="${UFW_AUTO:-true}"                  # true|false
UFW_STRICT="${UFW_STRICT:-true}"              # true|false
SSH_PORT="${SSH_PORT:-22}"
AGENT_PORT="${AGENT_PORT:-8091}"
PANEL_IPS="${PANEL_IPS:-}"                    # comma-separated
BOT_IPS="${BOT_IPS:-}"                        # comma-separated

BASE_DIR="/opt/remnanode"
WWW_DIR="/var/www/html"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TPL_DIR="${SCRIPT_DIR}/templates"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "required command not found: $1" >&2; exit 2; }; }
diagnose_certbot_failure() {
  local combined="${1:-}"
  echo "certbot failed, diagnostics:"
  if echo "${combined}" | grep -qi "too many certificates"; then
    echo "CERTBOT_DIAG=rate_limit_exact_set"
  elif echo "${combined}" | grep -qi "failed to authenticate"; then
    echo "CERTBOT_DIAG=auth_failed_http_or_dns"
  elif echo "${combined}" | grep -qi "connection refused"; then
    echo "CERTBOT_DIAG=port_80_unreachable_or_blocked"
  elif echo "${combined}" | grep -qi "no start line"; then
    echo "CERTBOT_DIAG=invalid_pem_content"
  elif echo "${combined}" | grep -qi "live directory exists"; then
    echo "CERTBOT_DIAG=existing_lineage_conflict"
  else
    echo "CERTBOT_DIAG=unknown"
  fi
  if [[ -f /var/log/letsencrypt/letsencrypt.log ]]; then
    echo "----- certbot log tail -----"
    tail -n 80 /var/log/letsencrypt/letsencrypt.log || true
    echo "----- end certbot log tail -----"
  fi
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

[[ -n "${DOMAIN}" ]] || { echo "DOMAIN is required" >&2; exit 2; }
[[ -n "${NODE_SECRET_KEY}" ]] || { echo "NODE_SECRET_KEY is required" >&2; exit 2; }
[[ "${WEB_SERVER}" == "nginx" || "${WEB_SERVER}" == "caddy" ]] || { echo "WEB_SERVER must be nginx or caddy" >&2; exit 2; }
[[ "${CERT_METHOD}" == "none" || "${CERT_METHOD}" == "http" || "${CERT_METHOD}" == "cloudflare" ]] || { echo "CERT_METHOD must be none|http|cloudflare" >&2; exit 2; }
[[ "${TEMPLATE_SOURCE}" == "builtin" || "${TEMPLATE_SOURCE}" == "url" ]] || { echo "TEMPLATE_SOURCE must be builtin|url" >&2; exit 2; }

if [[ -z "${CERT_DOMAIN}" ]]; then
  CERT_DOMAIN="${DOMAIN}"
fi
CERT_FULLCHAIN_PATH="/etc/letsencrypt/live/${CERT_DOMAIN}/fullchain.pem"
CERT_PRIVKEY_PATH="/etc/letsencrypt/live/${CERT_DOMAIN}/privkey.pem"
EFFECTIVE_CERT_NAME="${CERT_DOMAIN}"

if [[ "${CERT_METHOD}" != "none" ]]; then
  [[ -n "${CERT_EMAIL}" ]] || { echo "CERT_EMAIL is required when CERT_METHOD!=none" >&2; exit 2; }
  if [[ "${CERT_METHOD}" == "cloudflare" ]]; then
    [[ -n "${CLOUDFLARE_API_TOKEN}" ]] || { echo "CLOUDFLARE_API_TOKEN is required for cloudflare method" >&2; exit 2; }
  fi
fi
if [[ "${CERT_FORCE_RENEWAL}" != "true" && "${CERT_FORCE_RENEWAL}" != "false" ]]; then
  echo "CERT_FORCE_RENEWAL must be true or false" >&2
  exit 2
fi

if [[ "${UFW_AUTO}" != "true" && "${UFW_AUTO}" != "false" ]]; then
  echo "UFW_AUTO must be true or false" >&2
  exit 2
fi
if [[ "${UFW_STRICT}" != "true" && "${UFW_STRICT}" != "false" ]]; then
  echo "UFW_STRICT must be true or false" >&2
  exit 2
fi

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: install node domain=${DOMAIN} cert_domain=${CERT_DOMAIN} web=${WEB_SERVER} cert=${CERT_METHOD} force_renew=${CERT_FORCE_RENEWAL} tpl=${TEMPLATE_SOURCE} ufw_strict=${UFW_STRICT}"
  exit 0
fi

need_cmd docker
need_cmd bash
need_cmd sed

mkdir -p "${BASE_DIR}" "${WWW_DIR}"

# Cleanup conflicting path types from previous failed/manual installs.
for p in "${BASE_DIR}/docker-compose.yml" "${BASE_DIR}/nginx.conf" "${BASE_DIR}/Caddyfile"; do
  if [[ -e "${p}" && ! -f "${p}" ]]; then
    rm -rf "${p}"
  fi
done

# Cleanup conflicting certificate path types from previous failed starts.
for p in "${CERT_FULLCHAIN_PATH}" "${CERT_PRIVKEY_PATH}"; do
  if [[ -e "${p}" && ! -f "${p}" ]]; then
    rm -rf "${p}"
  fi
done

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
  cert_force_args=()
  if [[ "${CERT_FORCE_RENEWAL}" == "true" ]]; then
    cert_force_args+=(--force-renewal)
  fi
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
      --email "${CERT_EMAIL}" --cert-name "${CERT_DOMAIN}" -d "${CERT_DOMAIN}" \
      "${cert_force_args[@]}" > /tmp/infra-agent-certbot.out 2>&1 || true
    certbot_output="$(cat /tmp/infra-agent-certbot.out 2>/dev/null || true)"
    echo "${certbot_output}"
    if grep -qiE "error|failed|too many certificates|connection refused|live directory exists" /tmp/infra-agent-certbot.out; then
      diagnose_certbot_failure "${certbot_output}"
      rm -f "${tmp_compose}" /tmp/infra-agent-certbot.out
      exit 1
    fi
    rm -f /tmp/infra-agent-certbot.out
    rm -f "${tmp_compose}"
  else
    need_cmd certbot
    mkdir -p /root/.secrets/certbot
    cat > /root/.secrets/certbot/cloudflare.ini <<EOF
dns_cloudflare_api_token = ${CLOUDFLARE_API_TOKEN}
EOF
    chmod 600 /root/.secrets/certbot/cloudflare.ini
    run_cmd_with_diag certbot certonly --non-interactive --agree-tos --email "${CERT_EMAIL}" \
      --cert-name "${CERT_DOMAIN}" \
      --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/certbot/cloudflare.ini \
      --dns-cloudflare-propagation-seconds 60 -d "${CERT_DOMAIN}" \
      "${cert_force_args[@]}"
  fi
fi

# Resolve actual cert lineage name (can be domain-0001, etc.) and align compose mounts.
if [[ "${CERT_METHOD}" != "none" ]]; then
  certbot_cert_path="$(certbot certificates --cert-name "${CERT_DOMAIN}" 2>/dev/null | awk -F': ' '/Certificate Path:/ {print $2; exit}' || true)"
  if [[ -n "${certbot_cert_path}" ]]; then
    cert_lineage_dir="$(dirname "${certbot_cert_path}")"
    EFFECTIVE_CERT_NAME="$(basename "${cert_lineage_dir}")"
  elif [[ -f "/etc/letsencrypt/live/${CERT_DOMAIN}/fullchain.pem" ]]; then
    EFFECTIVE_CERT_NAME="${CERT_DOMAIN}"
  else
    candidate="$(ls -1d /etc/letsencrypt/live/${CERT_DOMAIN}-* 2>/dev/null | head -n1 || true)"
    if [[ -n "${candidate}" && -f "${candidate}/fullchain.pem" ]]; then
      EFFECTIVE_CERT_NAME="$(basename "${candidate}")"
    fi
  fi
  CERT_FULLCHAIN_PATH="/etc/letsencrypt/live/${EFFECTIVE_CERT_NAME}/fullchain.pem"
  CERT_PRIVKEY_PATH="/etc/letsencrypt/live/${EFFECTIVE_CERT_NAME}/privkey.pem"
  if [[ "${EFFECTIVE_CERT_NAME}" != "${CERT_DOMAIN}" ]]; then
    sed -i \
      -e "s|/etc/letsencrypt/live/${CERT_DOMAIN}/fullchain.pem|/etc/letsencrypt/live/${EFFECTIVE_CERT_NAME}/fullchain.pem|g" \
      -e "s|/etc/letsencrypt/live/${CERT_DOMAIN}/privkey.pem|/etc/letsencrypt/live/${EFFECTIVE_CERT_NAME}/privkey.pem|g" \
      "${BASE_DIR}/docker-compose.yml"
  fi
fi

# Guardrail: for nginx/caddy TLS templates we need real cert files on host.
if [[ "${CERT_METHOD}" != "none" ]]; then
  if [[ ! -f "${CERT_FULLCHAIN_PATH}" || ! -f "${CERT_PRIVKEY_PATH}" ]]; then
    echo "certificate files are missing or invalid: ${CERT_FULLCHAIN_PATH} ${CERT_PRIVKEY_PATH}" >&2
    exit 2
  fi
fi

if [[ "${UFW_AUTO}" == "true" ]]; then
  if ! command -v ufw >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get -y install ufw
  fi
  # Safety first: allow SSH before enabling firewall to avoid lockout.
  ufw allow "${SSH_PORT}/tcp" || true
  if [[ -n "${PANEL_IPS}" ]]; then
    IFS=',' read -r -a panel_arr <<< "${PANEL_IPS}"
    for ip in "${panel_arr[@]}"; do
      ip="$(echo "${ip}" | xargs)"
      [[ -z "${ip}" ]] && continue
      ufw allow from "${ip}" to any port "${NODE_PORT}" proto tcp || true
    done
  else
    if [[ "${UFW_STRICT}" == "true" ]]; then
      echo "PANEL_IPS is required when UFW_STRICT=true" >&2
      exit 2
    fi
    ufw allow "${NODE_PORT}/tcp" || true
  fi
  if [[ -n "${BOT_IPS}" ]]; then
    IFS=',' read -r -a bot_arr <<< "${BOT_IPS}"
    for ip in "${bot_arr[@]}"; do
      ip="$(echo "${ip}" | xargs)"
      [[ -z "${ip}" ]] && continue
      ufw allow from "${ip}" to any port "${AGENT_PORT}" proto tcp || true
    done
  else
    if [[ "${UFW_STRICT}" == "true" ]]; then
      echo "BOT_IPS is required when UFW_STRICT=true" >&2
      exit 2
    fi
    ufw allow "${AGENT_PORT}/tcp" || true
  fi
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
  ufw --force enable || true
fi

cd "${BASE_DIR}"
docker compose up -d
echo "Remnawave node installed: domain=${DOMAIN} web=${WEB_SERVER} cert=${CERT_METHOD} dir=${BASE_DIR}"
