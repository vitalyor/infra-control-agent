# Infra Control Agent

HTTP-agent для сервера. Агент запускается в Docker, получает токен из панели/бота и дает API для диагностики хоста и управления Docker.

## Installation Flow

Токен не генерируется на сервере. Его генерирует панель/бот вместе с готовым `docker-compose.yml`.

### 1. Create Agent In Panel

В панели/боте создай agent/node и выбери порт, например `8091`.

Панель должна выдать:

- `AGENT_API_TOKEN`
- выбранный порт
- готовый `docker-compose.yml`

### 2. Prepare Server

```bash
mkdir -p /opt/infragent
cd /opt/infragent
```

### 3. Paste Generated Compose

```bash
nano docker-compose.yml
```

Пример compose, который должна генерировать панель:

```yaml
name: infra-control-agent

services:
  agent:
    build:
      context: https://github.com/vitalyor/infra-control-agent.git#main
      dockerfile: Dockerfile
    container_name: infra-control-agent
    restart: unless-stopped
    environment:
      AGENT_ID: infra-control-agent
      AGENT_API_TOKEN: paste-token-from-panel
      AGENT_HTTP_HOST: 0.0.0.0
      AGENT_HTTP_PORT: 8091
    ports:
      - "8091:8091"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - infra-control-agent-data:/agent/data

volumes:
  infra-control-agent-data:
```

Если репозиторий или ветка другие, панель должна подставить правильный `build.context`.

### 4. Open Port In UFW

Если UFW включен:

```bash
sudo ufw status | grep -qw active && sudo ufw allow 8091/tcp || true
```

Если выбран другой порт, замени `8091`.

### 5. Start Agent

```bash
docker compose up -d --build && docker compose logs -f -t
```

Healthcheck:

```bash
curl -sS http://127.0.0.1:8091/health
```

Protected endpoint:

```bash
curl -sS -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  http://127.0.0.1:8091/v1/docker/ps
```

## One Command Bootstrap

Можно также подготовить директорию и пример compose одной командой:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/vitalyor/infra-control-agent/refs/heads/main/install.sh)
```

Скрипт не генерирует токен. Он только:

- проверяет Docker и Docker Compose
- создает `/opt/infragent`
- кладет пример `docker-compose.yml`, если файла еще нет
- показывает команды для UFW и запуска

После этого вставь compose, который сгенерировала панель/бот.

## Endpoints

- `GET /health`
- `GET /v1/diagnostics/host`
- `GET /v1/docker/ps`
- `POST /v1/docker/logs/tail`
- `POST /v1/docker/restart`

Docker-функции требуют проброшенный `/var/run/docker.sock`.
