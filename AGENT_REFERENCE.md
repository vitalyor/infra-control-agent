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
