# AGENT REFERENCE (v2)

## 1) Модель выполнения

Агент работает как operation-runner:

1. Бот отправляет HTTP-запрос.
2. Агент валидирует токен/confirm.
3. Агент создаёт job.
4. Job запускает локальный shell-скрипт из `ops/`.
5. Результат (`exit_code/stdout/stderr`) сохраняется в job.

## 2) Универсальный запуск операций

`POST /v1/actions/run`

Body:

```json
{
  "operation_id": "system.update",
  "params": { "full_update": true },
  "dry_run": false,
  "confirm": "system_update"
}
```

## 3) Операции

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
- `system.reboot`
- `system.agent_update`
- `network.bbr_cake`
- `network.ipv6`
- `services.update`
- `remnawave.node_install`
- `remnawave.stack`
- `security.certbot`

## 4) Confirm для опасных действий

- `security.harden_ssh` -> `harden_ssh`
- `security.ssh_port` -> `ssh_port`
- `security.rollback` -> `rollback_security`
- `system.update` -> `system_update`
- `system.reboot` -> `reboot_host`
- `system.agent_update` -> `agent_update`
- `network.bbr_cake` -> `network_tuning`
- `network.ipv6` -> `ipv6_change`
- `services.update` -> `services_update`
- `remnawave.node_install` -> `install_node`
- `security.certbot` -> `cert_manage`

## 5) Job API

- `GET /v1/actions`
- `GET /v1/actions/{job_id}`
- `DELETE /v1/actions/{job_id}` (только неактивные)
- `POST /v1/actions/prune`

## 6) Alias endpoint'ы

Добавлены для удобства интеграции:

- `GET /v1/security/status`
- `GET /v1/remnawave/config?name=docker-compose|nginx|caddy`
- `POST /v1/system/update`
- `POST /v1/system/reboot`
  - `mode`: `hard|soft`
  - `delay_sec`: задержка перед reboot (сек)
  - `wait_timeout_sec`: для `soft`, сколько максимум ждать завершения активных job
  - `poll_sec`: для `soft`, интервал проверки
- `POST /v1/agent/update`
  - `confirm`: `agent_update`
  - `stack_dir` (опц., по умолчанию `/opt/infragent`)
  - `delay_sec` (опц., по умолчанию `2`)
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

### UFW payload (alias `/v1/ufw/action`)
- `action`: `install|status|status_numbered|enable|disable|start|stop|restart|reset`
- `rule_action`: `allow|deny|reject|limit|delete`
- Raw rule mode: `rule` (example: `8091/tcp`, `allow 8091/tcp`)
- Structured mode: `port`, `proto`, `from`, `to`
- Delete by number: `rule_num` with `rule_action=delete`

### Node install payload additions (`/v1/remnawave/node/install`)
- `panel_ips`: array of panel IPs for restricting `node_port` (or `panel_ip` for single IP)
- `bot_ips`: array of bot IPs for restricting `agent_port` (or `bot_ip` for single IP)
- `ufw_auto=true` applies rules in safe order: allow SSH first, then enable UFW
- `ufw_strict=true` (по умолчанию): запрещает fallback в `allow any` для `node_port/agent_port`, требует `panel_ips` и `bot_ips`

## 7) Стандарт ошибок API и job

### Ошибка HTTP API
Формат:

```json
{
  "ok": false,
  "error": "confirm must be install_node",
  "error_code": "confirm_required"
}
```

Основные `error_code`:
- `unauthorized`
- `invalid_request`
- `unknown_operation`
- `confirm_required`
- `too_many_active_jobs`
- `job_not_found`
- `job_active`
- `compose_validation_failed`
- `restart_failed`
- `route_not_found`

### Ошибка внутри job (`job.result.error_code`)
- `timeout`
- `missing_dependency_docker`
- `missing_dependency_ufw`
- `missing_dependency_certbot`
- `cert_issue_http_challenge`
- `invalid_ufw_action`
- `operation_script_missing`
- `command_failed`

## 8) Готовые payload-шаблоны для бота

### Установка ноды (строгий UFW)

```json
{
  "dry_run": false,
  "confirm": "install_node",
  "domain": "node.example.com",
  "node_port": 2222,
  "node_secret_key": "SECRET_FROM_PANEL",
  "web_server": "nginx",
  "cert_method": "http",
  "cert_domain": "node.example.com",
  "cert_email": "ops@example.com",
  "ufw_auto": true,
  "ufw_strict": true,
  "ssh_port": 22,
  "agent_port": 8091,
  "panel_ips": ["1.2.3.4"],
  "bot_ips": ["5.6.7.8"]
}
```

### UFW статус с номерами + удаление по номеру

```json
{ "dry_run": false, "action": "status_numbered" }
```

```json
{
  "dry_run": false,
  "action": "enable",
  "rule_action": "delete",
  "rule_num": 3
}
```
