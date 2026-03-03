# Infra Control Agent

Отдельный агент для выполнения задач, выданных `Control API`.

## Быстрая установка одной командой

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/your-org/infra-control-agent/main/install.sh)
```

Установщик:

1. клонирует код с GitHub;
2. запрашивает нужные параметры (`CONTROL_API_URL`, `AGENT_ENROLL_TOKEN`, `AGENT_NODE_UUID` и т.д.);
3. создаёт `.env`;
4. поднимает агент через `docker compose`.

## Что умеет сейчас

- регистрация через enrollment token;
- heartbeat в Control API;
- poll задач;
- выполнение базовых action:
  - `diagnostics.host`
  - `docker.ps`
  - `docker.logs.tail`
  - `docker.restart`

## Локальный ручной запуск (без install.sh)

```bash
cp .env.example .env
docker compose up -d --build
```

Логи:

```bash
docker compose logs -f agent
```

## Переменные окружения

- `CONTROL_API_URL` - URL Control API (`http://<bot-host>:8090`)
- `AGENT_ID` - уникальный идентификатор агента
- `AGENT_NODE_UUID` - UUID ноды для таргетирования jobs
- `AGENT_DISPLAY_NAME` - отображаемое имя
- `AGENT_ENROLL_TOKEN` - одноразовый токен регистрации
- `AGENT_ACCESS_TOKEN` - опционально, если токен уже выдан
- `AGENT_POLL_INTERVAL_S` - период poll
- `AGENT_HEARTBEAT_INTERVAL_S` - период heartbeat
- `AGENT_STATE_PATH` - путь для сохранения состояния/ключей
- `AGENT_VERIFY_TLS` - `true/false`

## Безопасность

- enrollment token одноразовый и с TTL;
- access token хранится локально в `AGENT_STATE_PATH`;
- рекомендуется ограничивать доступ к Control API по ACL/firewall.
