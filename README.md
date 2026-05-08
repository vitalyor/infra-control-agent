<<<<<<< HEAD
# Infra Control Agent

HTTP-agent для сервера. Агент запускается в Docker, получает токен из панели/бота и дает API для диагностики хоста и управления Docker.

Полный справочник по возможностям, security model, endpoint'ам и bot-flow лежит в `AGENT_REFERENCE.md`.

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
    privileged: true
    network_mode: host
    pid: host
    environment:
      AGENT_ID: infra-control-agent
      AGENT_API_TOKEN: paste-token-from-panel
      AGENT_HTTP_PORT: 8091
      AGENT_LOG_LEVEL: warning
      AGENT_ACCESS_LOG: "false"
      AGENT_ALLOWED_UPGRADES: panel,node,subscription
      AGENT_JOB_MAX_COUNT: 20
      AGENT_JOB_MAX_AGE_S: 3600
      AGENT_MAX_ACTIVE_JOBS: 2
      AGENT_MAX_BODY_BYTES: 65536
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /opt:/host/opt:rw
      - /etc/sysctl.d:/host/etc/sysctl.d:rw
      - /proc:/host/proc:ro
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

## Security Notes

Агент имеет сильные права на сервере:

- `/var/run/docker.sock` позволяет управлять Docker на хосте;
- `privileged: true` нужен для server tuning;
- `network_mode: host` нужен, чтобы tuning видел host network namespace;
- `/opt` монтируется для upgrade Remnawave compose-директорий;
- `/etc/sysctl.d` монтируется для managed tuning config.

Поэтому `AGENT_API_TOKEN` обязателен. По умолчанию агент откажется стартовать с пустым токеном.

Для локальной разработки можно явно разрешить пустой токен:

```yaml
environment:
  AGENT_ALLOW_EMPTY_TOKEN: "true"
```

В production так делать нельзя: защищенные endpoint'ы станут открытыми.

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

## Logging

Агент пишет структурированные читаемые логи в stdout контейнера.

Настройки:

- `AGENT_LOG_LEVEL=debug` - максимально подробно: команды, Docker API, диагностика.
- `AGENT_LOG_LEVEL=info` - обычный режим по умолчанию.
- `AGENT_LOG_LEVEL=warning` - только важные действия и проблемы.
- `AGENT_LOG_LEVEL=error` - только ошибки.
- `AGENT_LOG_LEVEL=off` - почти полностью выключить логи.
- `AGENT_ACCESS_LOG=true|false` - включить или выключить access-log HTTP-запросов.

Пример:

```yaml
environment:
  AGENT_LOG_LEVEL: debug
  AGENT_ACCESS_LOG: "true"
```

В логах есть `event=...`, `request_id=...`, action, target, job_id и причина ошибки. Новые функции агента должны логировать validation, action start, job creation и результат.

Background jobs хранятся в памяти агента. Настройки retention и защиты от случайной нагрузки:

- `AGENT_JOB_MAX_COUNT=20`
- `AGENT_JOB_MAX_AGE_S=3600`
- `AGENT_JOB_LOG_LIMIT=30000`
- `AGENT_MAX_ACTIVE_JOBS=2`
- `AGENT_MAX_BODY_BYTES=65536`
- `AGENT_AUTH_FAIL_LIMIT=10`
- `AGENT_AUTH_FAIL_WINDOW_S=300`
- `AGENT_AUTH_FAIL_BLOCK_S=300`

Опасные POST-действия требуют явный `confirm`, если это не `dry_run`: reboot, Docker prune, Remnawave upgrade, UFW stop/disable, fail2ban stop/disable/config и server tuning.

Для UFW можно использовать старое поле `rule` или структурированный формат:

```json
{
  "action": "allow",
  "port": 443,
  "proto": "tcp",
  "from": "10.0.0.0/8",
  "dry_run": true
}
```

## Endpoints

- `GET /health`
- `GET /v1/agent/info`
- `GET /v1/node/summary`
- `GET /v1/diagnostics/host`
- `GET /v1/docker/ps`
- `GET /v1/docker/usage`
- `GET /v1/docker/containers`
- `GET /v1/docker/containers/{container}`
- `POST /v1/docker/container/action`
- `POST /v1/docker/logs/tail`
- `POST /v1/docker/prune`
- `GET /v1/remnawave/profiles`
- `POST /v1/remnawave/upgrade`
- `GET /v1/ufw/status`
- `POST /v1/ufw/action`
- `POST /v1/ufw/rule`
- `GET /v1/fail2ban/status`
- `POST /v1/fail2ban/action`
- `GET /v1/fail2ban/config`
- `POST /v1/fail2ban/config`
- `POST /v1/fail2ban/jail`
- `POST /v1/server/reboot`
- `GET /v1/server/tuning`
- `POST /v1/server/tuning`
- `GET /v1/actions`
- `GET /v1/actions/{job_id}`
- `DELETE /v1/actions/{job_id}`
- `POST /v1/actions/prune`

Docker-функции требуют проброшенный `/var/run/docker.sock`.

Агент запускается с `network_mode: host`. Это нужно, чтобы endpoint server tuning видел те же `net.*` sysctl значения, что и сам сервер. Порт публикуется напрямую через `AGENT_HTTP_PORT`, поэтому отдельный `ports:` block в compose не нужен.

По умолчанию агент слушает `0.0.0.0`. В compose это не указывается, чтобы установка была проще. Для нестандартного локального режима можно задать `AGENT_HTTP_HOST=127.0.0.1`.

Upgrade Remnawave требует доступ к compose-директориям хоста. Для этого compose монтирует `/opt` хоста внутрь контейнера как `/host/opt`. Пользователю не нужно указывать эти пути: агент сам использует стандартные mount-пути внутри контейнера.

Server tuning требует доступ к `/etc/sysctl.d` хоста и host `/proc`, поэтому compose монтирует их как `/host/etc/sysctl.d` и `/host/proc`. Пользователю не нужно настраивать эти пути вручную. Агент пишет только свой файл `99-infra-control-agent-tuning.conf`.

Для чтения и применения `net.*` sysctl агент работает в host network namespace. В tuning status также возвращается диагностика namespace: `container_netns`, `host_netns`, `same_netns`.

## OpenAPI

OpenAPI-спеку храните отдельно для разработки бота/клиента. Агент её по HTTP не публикует.

## Health

`GET /health` - главный endpoint для бота. Он быстрый и не требует авторизации.

Пример ответа:

```json
{
  "ok": true,
  "status": "ok",
  "agent_id": "infra-control-agent",
  "version": "0.3.3",
  "hostname": "node-1",
  "uptime_s": 12345,
  "docker_available": true
}
```

## Agent Info

`GET /v1/agent/info` возвращает диагностическую информацию об агенте:

- версию;
- настроен ли токен, без значения токена;
- режим Docker: CLI или socket;
- наличие host mounts;
- namespace diagnostics;
- настройки job retention;
- версию OpenAPI.

## Node Summary

`GET /v1/node/summary` возвращает дружелюбную сводку для бота/панели:

- статус агента;
- uptime, load average, RAM и disk;
- доступность Docker;
- количество контейнеров всего/живых/остановленных;
- список контейнеров с ресурсами;
- список проблем;
- `severity`: `ok`, `warning` или `critical`;
- `recommended_actions` для бота, например посмотреть логи или перезапустить контейнер;
- `resource_alerts` по RAM/disk;
- `insights.top_containers_by_cpu`;
- `insights.top_containers_by_memory`.

## Docker Containers

`GET /v1/docker/usage` возвращает Docker disk usage через Docker Engine API:

- images size/reclaimable;
- containers size/reclaimable;
- volumes size/reclaimable;
- build cache;
- total reclaimable.

`GET /v1/docker/containers` возвращает контейнеры в JSON:

- `id`
- `name`
- `image`
- `state`
- `status`
- `running`
- `resources.cpu_percent`
- `resources.memory_usage`
- `resources.memory_percent`
- `resources.network_io`
- `resources.block_io`
- `resources.pids`
- `health`
- `attention`
- `actions.can_view_logs`
- `actions.can_restart`
- `recommended_actions`

Поля `attention` и `recommended_actions` нужны для бота/панели: агент не блокирует действия по неизвестным контейнерам, но подсказывает, где есть проблема и какие кнопки логично показать.

`GET /v1/docker/containers/{container}` возвращает подробную информацию и текущее потребление конкретного контейнера:

- inspect/status;
- restart count;
- ports/networks;
- CPU percent;
- RAM usage/limit/percent;
- network rx/tx;
- block read/write;
- PIDs.

Raw Docker stats по умолчанию скрыты. Для отладки можно добавить `?raw=true`.

Пример:

```bash
curl -sS -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  http://127.0.0.1:8091/v1/docker/containers/infra-control-agent
```

## Docker Restart

Новый универсальный endpoint:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"container":"container-name","action":"restart"}' \
  http://127.0.0.1:8091/v1/docker/container/action
```

Allowed actions:

- `start`
- `stop`
- `restart`

## Docker Prune

Dry run:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"target":"images","dry_run":true}' \
  http://127.0.0.1:8091/v1/docker/prune
```

Run cleanup:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"target":"images"}' \
  http://127.0.0.1:8091/v1/docker/prune
```

Allowed `target` values:

- `images`
- `containers`
- `builder`
- `system`

Volumes are not removed by default. For `target=system`, volumes are removed only with `"volumes": true`.

Prune runs as a background job and returns `job_id`.

Prune uses Docker CLI when it is available. If the container has no docker CLI, the agent falls back to Docker Engine API through `/var/run/docker.sock`.

Dry-run возвращает компактный `docker_system_df.summary`, если используется Docker API fallback.

## Remnawave Upgrade

Upgrade is restricted to allowlisted profiles. The agent does not accept arbitrary shell commands.

Profiles:

- `panel` -> `/opt/remnawave`
- `node` -> `/opt/remnanode`
- `subscription` -> `/opt/remnawave/subscription`

Inside the agent container these paths are resolved automatically through the default host mount `/host`, for example `/host/opt/remnawave`.

Проверить, какие upgrade-профили реально доступны на ноде:

```bash
curl -sS -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  http://127.0.0.1:8091/v1/remnawave/profiles
```

Endpoint возвращает `available_profiles` и подробности по каждому профилю: разрешен ли он, существует ли директория, найден ли compose-файл и доступен ли `docker compose`.

Dry run:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"profile":"panel","dry_run":true}' \
  http://127.0.0.1:8091/v1/remnawave/upgrade
```

Run upgrade:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"profile":"panel"}' \
  http://127.0.0.1:8091/v1/remnawave/upgrade
```

Upgrade runs as a background job:

```bash
curl -sS -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  http://127.0.0.1:8091/v1/actions/<JOB_ID>
```

## Server Reboot

Перезагрузка сервера запускается как background job и требует явного подтверждения:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"confirm":"reboot"}' \
  http://127.0.0.1:8091/v1/server/reboot
```

Dry run:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"dry_run":true}' \
  http://127.0.0.1:8091/v1/server/reboot
```

## UFW

`GET /v1/ufw/status` показывает, установлен ли UFW, состояние systemd-сервиса и вывод `ufw status verbose/numbered`.

Service actions:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"action":"install"}' \
  http://127.0.0.1:8091/v1/ufw/action
```

Allowed actions:

- `install`
- `enable`
- `disable`
- `start`
- `stop`
- `restart`

Rules:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"action":"allow","rule":"8091/tcp"}' \
  http://127.0.0.1:8091/v1/ufw/rule
```

Allowed rule actions:

- `allow`
- `deny`
- `reject`
- `delete`

Удаление по номеру:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"action":"delete","number":3}' \
  http://127.0.0.1:8091/v1/ufw/rule
```

## Fail2Ban

`GET /v1/fail2ban/status` показывает, установлен ли Fail2Ban, состояние сервиса и вывод `fail2ban-client status`.

Проверить конкретный jail:

```bash
curl -sS -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  'http://127.0.0.1:8091/v1/fail2ban/status?jail=sshd'
```

Service actions:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"action":"restart"}' \
  http://127.0.0.1:8091/v1/fail2ban/action
```

Allowed actions:

- `install`
- `start`
- `stop`
- `restart`
- `enable`
- `disable`

Managed config:

```bash
curl -sS -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  http://127.0.0.1:8091/v1/fail2ban/config
```

Update managed `/etc/fail2ban/jail.local` and restart Fail2Ban:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"bantime":"1h","findtime":"10m","maxretry":5,"backend":"systemd","sshd_enabled":true,"sshd_port":"22"}' \
  http://127.0.0.1:8091/v1/fail2ban/config
```

Allowed config fields:

- `bantime`
- `findtime`
- `maxretry`
- `backend`
- `sshd_enabled`
- `sshd_port`

Jail actions:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"action":"unbanip","jail":"sshd","ip":"1.2.3.4"}' \
  http://127.0.0.1:8091/v1/fail2ban/jail
```

Allowed jail actions:

- `banip`
- `unbanip`

Install action uses the package flow from `fail2ban.md`: `apt-get update`, `apt-get install -y fail2ban`, enable/start service. SSH hardening commands from that file are intentionally not exposed yet.

## Jobs

Long-running actions return a background job. Recent jobs:

```bash
curl -sS -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  http://127.0.0.1:8091/v1/actions
```

Prune completed jobs:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"max_age_s":3600,"max_count":50}' \
  http://127.0.0.1:8091/v1/actions/prune
```

Delete one completed job:

```bash
curl -sS -X DELETE \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  http://127.0.0.1:8091/v1/actions/<JOB_ID>
```

## Server Tuning

`GET /v1/server/tuning` показывает состояние tuning-профиля.

По умолчанию используется профиль `bbr_fq`:

```conf
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
```

Проверить статус:

```bash
curl -sS -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  http://127.0.0.1:8091/v1/server/tuning
```

Включить:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"profile":"bbr_fq","action":"enable"}' \
  http://127.0.0.1:8091/v1/server/tuning
```

Выключить:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer <TOKEN_FROM_PANEL>" \
  -H "Content-Type: application/json" \
  -d '{"profile":"bbr_fq","action":"disable"}' \
  http://127.0.0.1:8091/v1/server/tuning
```

Enable записывает конфиг в `/etc/sysctl.d/99-infra-control-agent-tuning.conf` на хосте и запускает runtime apply как background job.

Disable тоже записывает managed-конфиг, но уже с обычными значениями:

```conf
net.core.default_qdisc = fq_codel
net.ipv4.tcp_congestion_control = cubic
```

Это нужно для случаев, когда BBR/fq были включены на сервере еще до установки агента. Агент не редактирует чужие sysctl-файлы, а управляет только своим override-файлом.
=======
# Infra Control Agent (v2)

Агент для ноды: выполняет операции через локальные скрипты `ops/**/*.sh`, запускаемые по HTTP API.

## Архитектура

- `main.py` — HTTP API, авторизация, jobs, operation registry.
- `ops/` — неинтерактивные скрипты операций.
- `openapi.json` — актуальная схема API для интеграции бота.

## Основные endpoint'ы

- `GET /health` — без токена.
- `GET /v1/agent/info` — состояние агента и список операций.
- `GET /v1/actions` / `GET /v1/actions/{job_id}` / `DELETE /v1/actions/{job_id}`.
- `POST /v1/actions/run` — универсальный запуск операции:
  - `operation_id`
  - `params` (ключи попадут в ENV скрипта верхним регистром)
  - `dry_run`
  - `confirm` (для опасных операций)
- `POST /v1/actions/prune` — чистка истории jobs.

## Совместимые alias endpoint'ы

- `GET /v1/security/status`
- `POST /v1/system/update`
- `POST /v1/security/harden-ssh`
- `POST /v1/security/ssh-port`
- `POST /v1/security/rollback`
- `POST /v1/network/tuning`
- `POST /v1/services/update`
- `POST /v1/remnawave/node/install`
- `POST /v1/ufw/action`
- `POST /v1/fail2ban/action`
- `POST /v1/fail2ban/config`

## Confirm-токены

- `harden_ssh`
- `ssh_port`
- `rollback_security`
- `system_update`
- `network_tuning`
- `services_update`
- `install_node`

## Быстрый запуск

```bash
docker compose up -d --build
curl -sS http://127.0.0.1:8091/health
```

## Для бота

Рекомендуемый путь — использовать только `POST /v1/actions/run` и хранить mapping операций на стороне бота.

>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)
