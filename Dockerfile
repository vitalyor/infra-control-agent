FROM python:3.12-slim

WORKDIR /agent

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io docker-compose procps util-linux iproute2 curl certbot python3-certbot-dns-cloudflare \
    && if [ ! -x /usr/bin/docker ]; then \
         printf '%s\n' '#!/usr/bin/env sh' \
           'set -eu' \
           'if [ "${1:-}" = "compose" ]; then' \
           '  shift' \
           '  exec docker-compose "$@"' \
           'fi' \
           'echo "docker shim: only '\''docker compose ...'\'' is supported in this image" >&2' \
           'exit 127' > /usr/local/bin/docker; \
         chmod +x /usr/local/bin/docker; \
       fi \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY ops ./ops
RUN find /agent/ops -type f -name "*.sh" -exec chmod +x {} \;

CMD ["python", "main.py"]
