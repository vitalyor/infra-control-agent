#!/usr/bin/env bash
set -euo pipefail
DOMAIN="${DOMAIN:-}"
NODE_PORT="${NODE_PORT:-2222}"
NODE_SECRET_KEY="${NODE_SECRET_KEY:-replace_with_node_secret_key}"

if [[ -z "${DOMAIN}" ]]; then
  echo "DOMAIN is required" >&2
  exit 2
fi

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  echo "DRY_RUN: install remnawave node domain=${DOMAIN} port=${NODE_PORT}"
  exit 0
fi

mkdir -p /opt/remnanode /var/www/html
cat > /opt/remnanode/docker-compose.yml <<EOF
services:
  remnanode:
    image: remnawave/node:latest
    container_name: remnanode
    restart: unless-stopped
    network_mode: host
    environment:
      - NODE_PORT=${NODE_PORT}
      - SECRET_KEY=${NODE_SECRET_KEY}
  remnanode-nginx:
    image: nginx:1.28
    container_name: remnanode-nginx
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /var/www/html:/var/www/html:ro
EOF

cat > /opt/remnanode/nginx.conf <<EOF
server {
  listen 80;
  server_name ${DOMAIN};
  root /var/www/html;
  index index.html;
}
EOF

cat > /var/www/html/index.html <<'EOF'
<!doctype html><html><head><meta charset="utf-8"><title>Service is running</title></head><body><h1>Service is running</h1></body></html>
EOF

cd /opt/remnanode
docker compose up -d
echo "Remnawave node installed for domain=${DOMAIN}"

