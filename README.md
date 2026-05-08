# Infra Control Agent (v2)

Лёгкий HTTP-агент для управления нодой через локальные операции (`ops/*.sh`).

## Что делает агент

1. Принимает запросы от бота по HTTP API.
2. Проверяет токен (`Authorization: Bearer ...` или `X-Agent-Token`).
3. Создаёт job в памяти.
4. Запускает нужный скрипт из `ops/`.
5. Возвращает результат (`exit_code`, `stdout`, `stderr`, статус job).

## Быстрый запуск

Сначала установи Docker:

```bash
sudo curl -fsSL https://get.docker.com | sh
```

Дальше:

```bash
mkdir -p /opt/infragent
cd /opt/infragent
nano docker-compose.yml
```

Пример `docker-compose.yml`:

```yaml
name: infra-control-agent

services:
  agent:
    build:
      context: https://github.com/vitalyor/infra-control-agent.git#main
      dockerfile: Dockerfile
    container_name: infra-control-agent
    restart: unless-stopped
    privileged: true
    pid: host
    environment:
      AGENT_ID: infra-control-agent
      AGENT_API_TOKEN: paste-token-from-panel
      AGENT_HTTP_PORT: 8091
      AGENT_LOG_LEVEL: warning
      AGENT_ACCESS_LOG: "false"
      AGENT_JOB_MAX_COUNT: 20
      AGENT_JOB_MAX_AGE_S: 3600
      AGENT_MAX_ACTIVE_JOBS: 2
      AGENT_MAX_BODY_BYTES: 65536
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - infra-control-agent-data:/agent/data
    ports:
      - "8091:8091"

volumes:
  infra-control-agent-data:
```

Запуск:

```bash
docker compose up -d --build
docker compose logs -f -t
```

Проверка:

```bash
curl -sS http://127.0.0.1:8091/health
```

## Переменные окружения

- `AGENT_API_TOKEN` (обязательно в production)
- `AGENT_ALLOW_EMPTY_TOKEN` (`false` по умолчанию)
- `AGENT_HTTP_HOST` (`0.0.0.0`)
- `AGENT_HTTP_PORT` (`8091`)
- `AGENT_LOG_LEVEL` (`debug|info|warning|error|none|off`)
- `AGENT_ACCESS_LOG` (`true|false`)
- `AGENT_MAX_BODY_BYTES` (`65536`)
- `AGENT_MAX_ACTIVE_JOBS` (`2`)
- `AGENT_JOB_MAX_COUNT` (`100`)
- `AGENT_JOB_MAX_AGE_S` (`86400`)
- `AGENT_JOB_LOG_LIMIT` (`30000`)

## Эндпоинты

### Публичный
- `GET /health`

### Требуют токен
- `GET /v1/agent/info`
- `GET /v1/actions`
- `GET /v1/actions/{job_id}`
- `DELETE /v1/actions/{job_id}`
- `POST /v1/actions/prune`
- `POST /v1/actions/run`
- `GET /v1/security/status`
- `GET /v1/remnawave/config?name=docker-compose|nginx|caddy`
- `POST /v1/system/update`
- `POST /v1/security/harden-ssh`
- `POST /v1/security/ssh-port`
- `POST /v1/security/rollback`
- `POST /v1/network/tuning`
- `POST /v1/network/ipv6`
- `POST /v1/services/update`
- `POST /v1/remnawave/node/install`
- `POST /v1/remnawave/stack`
- `POST /v1/remnawave/config`
- `POST /v1/ufw/action`
- `POST /v1/fail2ban/action`
- `POST /v1/fail2ban/config`
- `POST /v1/security/certbot`

## Операции (`operation_id`)

- `diagnostics.uptime`
- `diagnostics.disk`
- `diagnostics.load_net`
- `security.status`
- `security.harden_ssh`
- `security.ssh_port`
- `security.ufw`
- `security.fail2ban`
- `security.kernel`
- `security.ssh_notify`
- `security.rollback`
- `system.update`
- `network.bbr_cake`
- `network.ipv6`
- `services.update`
- `remnawave.node_install`
- `remnawave.stack`
- `security.certbot`

Полная спецификация для интеграции: `AGENT_REFERENCE.md` и `openapi.json` (локально).
