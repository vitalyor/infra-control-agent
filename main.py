from __future__ import annotations

import hmac
import json
import logging
import os
import platform
import shutil
import subprocess
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


AGENT_VERSION = "0.4.0"
AGENT_ID = str(os.getenv("AGENT_ID") or platform.node() or "infra-control-agent").strip()
AGENT_API_TOKEN = str(os.getenv("AGENT_API_TOKEN") or "").strip()
AGENT_ALLOW_EMPTY_TOKEN = str(os.getenv("AGENT_ALLOW_EMPTY_TOKEN") or "false").strip().lower() in {"1", "true", "yes", "on"}
AGENT_HTTP_HOST = str(os.getenv("AGENT_HTTP_HOST") or "0.0.0.0").strip()
AGENT_HTTP_PORT = int(os.getenv("AGENT_HTTP_PORT") or "8091")
AGENT_MAX_BODY_BYTES = int(os.getenv("AGENT_MAX_BODY_BYTES") or "65536")
AGENT_MAX_ACTIVE_JOBS = max(1, int(os.getenv("AGENT_MAX_ACTIVE_JOBS") or "2"))
AGENT_JOB_MAX_COUNT = max(0, int(os.getenv("AGENT_JOB_MAX_COUNT") or "100"))
AGENT_JOB_MAX_AGE_S = max(0, int(os.getenv("AGENT_JOB_MAX_AGE_S") or "86400"))
AGENT_JOB_LOG_LIMIT = max(1000, int(os.getenv("AGENT_JOB_LOG_LIMIT") or "30000"))
AGENT_LOG_LEVEL = str(os.getenv("AGENT_LOG_LEVEL") or "info").strip().lower()
AGENT_ACCESS_LOG = str(os.getenv("AGENT_ACCESS_LOG") or "true").strip().lower() not in {"0", "false", "no", "off"}
AGENT_STARTED_AT = time.time()
SCRIPT_DIR = Path(__file__).resolve().parent
OPS_DIR = SCRIPT_DIR / "ops"
HOST_OPS_DIR = Path("/opt/infra-control-agent/ops-runtime")
REMNANODE_DIR = Path("/opt/remnanode")

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def _setup_logging() -> None:
    level = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "none": logging.CRITICAL + 10,
        "off": logging.CRITICAL + 10,
    }.get(AGENT_LOG_LEVEL, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    logging.Formatter.converter = time.gmtime


def _log(level: int, event: str, **fields: Any) -> None:
    parts = [f"event={event}"]
    for k, v in fields.items():
        if v is None:
            continue
        parts.append(f"{k}={str(v).replace(chr(10), ' ')}")
    logging.log(level, " ".join(parts))


def _log_debug(event: str, **fields: Any) -> None:
    _log(logging.DEBUG, event, **fields)


def _log_info(event: str, **fields: Any) -> None:
    _log(logging.INFO, event, **fields)


def _log_warning(event: str, **fields: Any) -> None:
    _log(logging.WARNING, event, **fields)


class Operation:
    def __init__(self, operation_id: str, script_relpath: str, timeout_s: int = 900, confirm: str | None = None) -> None:
        self.operation_id = operation_id
        self.script_relpath = script_relpath
        self.timeout_s = timeout_s
        self.confirm = confirm

    @property
    def script_path(self) -> Path:
        return OPS_DIR / self.script_relpath


OPERATIONS: dict[str, Operation] = {
    "diagnostics.uptime": Operation("diagnostics.uptime", "diagnostics/01_get_uptime.sh", timeout_s=30),
    "diagnostics.disk": Operation("diagnostics.disk", "diagnostics/02_check_disk_usage.sh", timeout_s=120),
    "diagnostics.load_net": Operation("diagnostics.load_net", "diagnostics/03_check_load_and_net.sh", timeout_s=60),
    "security.status": Operation("security.status", "security/00_get_security_status.sh", timeout_s=30),
    "security.harden_ssh": Operation("security.harden_ssh", "security/01_harden_ssh.sh", timeout_s=180, confirm="harden_ssh"),
    "security.ssh_port": Operation("security.ssh_port", "security/02_ssh_port.sh", timeout_s=180, confirm="ssh_port"),
    "security.ufw": Operation("security.ufw", "security/03_setup_ufw.sh", timeout_s=300),
    "security.fail2ban": Operation("security.fail2ban", "security/04_setup_fail2ban.sh", timeout_s=300),
    "security.kernel": Operation("security.kernel", "security/05_apply_kernel.sh", timeout_s=120),
    "security.ssh_notify": Operation("security.ssh_notify", "security/06_setup_ssh_login_notify.sh", timeout_s=90),
    "security.rollback": Operation("security.rollback", "security/99_rollback_security.sh", timeout_s=180, confirm="rollback_security"),
    "system.update": Operation("system.update", "system/01_update_system.sh", timeout_s=3600, confirm="system_update"),
    "system.reboot": Operation("system.reboot", "system/02_reboot.sh", timeout_s=30, confirm="reboot_host"),
    "network.bbr_cake": Operation("network.bbr_cake", "network/01_bbr_cake.sh", timeout_s=120, confirm="network_tuning"),
    "network.ipv6": Operation("network.ipv6", "network/02_ipv6.sh", timeout_s=120, confirm="ipv6_change"),
    "services.update": Operation("services.update", "services/01_update_services.sh", timeout_s=7200, confirm="services_update"),
    "remnawave.node_install": Operation("remnawave.node_install", "remnawave/01_install_node.sh", timeout_s=1800, confirm="install_node"),
    "remnawave.stack": Operation("remnawave.stack", "remnawave/02_manage_stack.sh", timeout_s=3600),
    "security.certbot": Operation("security.certbot", "security/07_certbot.sh", timeout_s=3600, confirm="cert_manage"),
}


def _run_cmd(cmd: list[str], env: dict[str, str], timeout_s: int) -> dict[str, Any]:
    started = time.time()
    _log_debug("cmd_start", cmd=" ".join(cmd), timeout_s=timeout_s)
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=timeout_s, check=False)
        _log_debug("cmd_finish", cmd=" ".join(cmd), exit_code=p.returncode, duration_ms=int((time.time() - started) * 1000))
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": (p.stdout or "")[-12000:],
            "stderr": (p.stderr or "")[-12000:],
            "duration_ms": int((time.time() - started) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        _log_warning("cmd_timeout", cmd=" ".join(cmd), timeout_s=timeout_s)
        return {
            "ok": False,
            "exit_code": None,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": ((exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "command timed out"),
            "duration_ms": int((time.time() - started) * 1000),
        }


def _sync_ops_to_host() -> None:
    HOST_OPS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(OPS_DIR, HOST_OPS_DIR, dirs_exist_ok=True)


def _op_exec_cmd(op: "Operation") -> list[str]:
    # Run all operations in host namespaces to manage the server itself, not the agent container.
    if shutil.which("nsenter"):
        _sync_ops_to_host()
        host_script = HOST_OPS_DIR / op.script_relpath
        return ["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "/bin/bash", str(host_script)]
    return ["/bin/bash", str(op.script_path)]


def _active_jobs_count() -> int:
    with JOBS_LOCK:
        return sum(1 for j in JOBS.values() if j.get("status") in {"queued", "running"})


def _prune_jobs(max_age_s: int | None = None, max_count: int | None = None) -> dict[str, Any]:
    age = AGENT_JOB_MAX_AGE_S if max_age_s is None else max(0, int(max_age_s))
    count = AGENT_JOB_MAX_COUNT if max_count is None else max(0, int(max_count))
    now = time.time()
    removed: list[str] = []
    with JOBS_LOCK:
        ids = sorted(JOBS.keys(), key=lambda i: JOBS[i]["created_ts"], reverse=True)
        for job_id in list(ids):
            job = JOBS.get(job_id)
            if not job:
                continue
            if job["status"] in {"queued", "running"}:
                continue
            if age and now - float(job["created_ts"]) > age:
                JOBS.pop(job_id, None)
                removed.append(job_id)
        if count and len(JOBS) > count:
            ids2 = sorted(JOBS.keys(), key=lambda i: JOBS[i]["created_ts"], reverse=True)
            for job_id in ids2[count:]:
                job = JOBS.get(job_id)
                if job and job["status"] not in {"queued", "running"}:
                    JOBS.pop(job_id, None)
                    removed.append(job_id)
    result = {"ok": True, "removed": removed, "remaining": len(JOBS)}
    _log_debug("jobs_pruned", removed=len(removed), remaining=result["remaining"], max_age_s=age, max_count=count)
    return result


def _job_public(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
        "operation_id": job["operation_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "dry_run": bool(job.get("dry_run")),
        "params": job.get("params", {}),
        "result": job.get("result"),
        "log": (job.get("log") or "")[-AGENT_JOB_LOG_LIMIT:],
    }


def _run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            _log_warning("job_missing_on_start", job_id=job_id)
            return
        job["status"] = "running"
        job["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _log_info("job_started", job_id=job_id, operation_id=job["operation_id"], dry_run=job.get("dry_run"))
    op = OPERATIONS[job["operation_id"]]
    env = os.environ.copy()
    env["DRY_RUN"] = "true" if job.get("dry_run") else "false"
    for key, value in (job.get("params") or {}).items():
        env[str(key).upper()] = str(value)
    result = _run_cmd(_op_exec_cmd(op), env=env, timeout_s=op.timeout_s)
    if not result.get("ok"):
        result["error_code"] = _job_error_code(result)
    with JOBS_LOCK:
        job2 = JOBS.get(job_id)
        if not job2:
            _log_warning("job_missing_on_finish", job_id=job_id)
            return
        job2["status"] = "completed" if result["ok"] else "failed"
        job2["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        job2["result"] = result
        job2["log"] = ((result.get("stdout") or "") + ("\n" + result.get("stderr") if result.get("stderr") else ""))[-AGENT_JOB_LOG_LIMIT:]
    _log_info(
        "job_finished",
        job_id=job_id,
        operation_id=job["operation_id"],
        status=job2["status"],
        ok=result.get("ok"),
        exit_code=result.get("exit_code"),
        duration_ms=result.get("duration_ms"),
    )


def _create_job(operation_id: str, params: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    if operation_id not in OPERATIONS:
        _log_warning("job_rejected_unknown_operation", operation_id=operation_id)
        raise ValueError("unknown operation_id")
    if _active_jobs_count() >= AGENT_MAX_ACTIVE_JOBS:
        _log_warning("job_rejected_limit", operation_id=operation_id, max_active_jobs=AGENT_MAX_ACTIVE_JOBS)
        raise RuntimeError(f"too many active jobs: max {AGENT_MAX_ACTIVE_JOBS}")
    op = OPERATIONS[operation_id]
    if not op.script_path.exists():
        _log_warning("job_rejected_missing_script", operation_id=operation_id, script=op.script_relpath)
        raise FileNotFoundError(f"operation script not found: {op.script_relpath}")
    job_id = uuid.uuid4().hex[:12]
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job = {
        "id": job_id,
        "operation_id": operation_id,
        "status": "queued",
        "created_at": created_at,
        "created_ts": time.time(),
        "params": params,
        "dry_run": dry_run,
        "result": None,
        "log": "",
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    _log_info("job_created", job_id=job_id, operation_id=operation_id, dry_run=dry_run, params_count=len(params))
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return _job_public(job)


def _json_response(h: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    h.send_response(status.value)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _error_payload(error: str, error_code: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": error, "error_code": error_code}
    payload.update(extra)
    return payload


def _job_error_code(result: dict[str, Any]) -> str:
    if result.get("exit_code") is None:
        return "timeout"
    stderr = str(result.get("stderr") or "").lower()
    if "required command not found: docker" in stderr:
        return "missing_dependency_docker"
    if "required command not found: ufw" in stderr:
        return "missing_dependency_ufw"
    if "required command not found: certbot" in stderr:
        return "missing_dependency_certbot"
    if "certbot failed to authenticate" in stderr or "some challenges have failed" in stderr:
        return "cert_issue_http_challenge"
    if "invalid ufw_action" in stderr:
        return "invalid_ufw_action"
    if "operation script not found" in stderr:
        return "operation_script_missing"
    return "command_failed"


def _read_json_body(h: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(h.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    if length > AGENT_MAX_BODY_BYTES:
        _log_warning("request_rejected_body_too_large", path=urlparse(h.path).path, content_length=length, max=AGENT_MAX_BODY_BYTES)
        raise ValueError(f"request body too large: max {AGENT_MAX_BODY_BYTES} bytes")
    data = json.loads(h.rfile.read(length).decode("utf-8"))
    if not isinstance(data, dict):
        _log_warning("request_rejected_body_not_object", path=urlparse(h.path).path)
        raise ValueError("request body must be object")
    _log_debug("request_body_parsed", path=urlparse(h.path).path, keys=list(data.keys()))
    return data


def _authorized(h: BaseHTTPRequestHandler) -> bool:
    if not AGENT_API_TOKEN:
        return AGENT_ALLOW_EMPTY_TOKEN
    auth = str(h.headers.get("Authorization") or "").strip()
    x_token = str(h.headers.get("X-Agent-Token") or "").strip()
    return hmac.compare_digest(auth, f"Bearer {AGENT_API_TOKEN}") or hmac.compare_digest(x_token, AGENT_API_TOKEN)


def _require_auth(h: BaseHTTPRequestHandler) -> bool:
    if _authorized(h):
        _log_debug("auth_ok", path=urlparse(h.path).path, client=h.client_address[0])
        return True
    _log_warning("auth_failed", path=urlparse(h.path).path, client=h.client_address[0])
    _json_response(h, HTTPStatus.UNAUTHORIZED, _error_payload("unauthorized", "unauthorized"))
    return False


def _to_params(payload: dict[str, Any], exclude: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k in exclude:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
    return out


def _alias_params(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if path == "/v1/system/update":
        return {"FULL_UPDATE": str(bool(payload.get("full") if "full" in payload else False)).lower()}
    if path == "/v1/system/reboot":
        params: dict[str, Any] = {}
        if payload.get("delay_sec") is not None:
            params["REBOOT_DELAY_SEC"] = str(payload.get("delay_sec"))
        if payload.get("mode") is not None:
            params["REBOOT_MODE"] = str(payload.get("mode"))
        if payload.get("wait_timeout_sec") is not None:
            params["REBOOT_WAIT_TIMEOUT_SEC"] = str(payload.get("wait_timeout_sec"))
        if payload.get("poll_sec") is not None:
            params["REBOOT_POLL_SEC"] = str(payload.get("poll_sec"))
        return params
    if path == "/v1/security/harden-ssh":
        return {"DISABLE_PASSWORD_AUTH": str(bool(payload.get("disable_password_auth") if "disable_password_auth" in payload else True)).lower()}
    if path == "/v1/security/ssh-port":
        return {"ACTION": str(payload.get("action") or "set"), "PORT": str(payload.get("port") or "")}
    if path == "/v1/network/tuning":
        params: dict[str, Any] = {}
        if "bbr" in payload:
            params["ENABLE_BBR"] = str(bool(payload["bbr"])).lower()
        if "cake" in payload:
            params["ENABLE_CAKE"] = str(bool(payload["cake"])).lower()
        return params
    if path == "/v1/network/ipv6":
        return {"IPV6_ACTION": str(payload.get("action") or "status")}
    if path == "/v1/services/update":
        params = {"MODE": str(payload.get("mode") or "pull")}
        dirs = payload.get("dirs")
        if isinstance(dirs, list):
            params["DIRS"] = ",".join(str(x).strip() for x in dirs if str(x).strip())
        return params
    if path == "/v1/remnawave/node/install":
        params = {
            "DOMAIN": str(payload.get("domain") or ""),
            "NODE_PORT": str(payload.get("node_port") or 2222),
            "NODE_SECRET_KEY": str(payload.get("node_secret_key") or ""),
            "WEB_SERVER": str(payload.get("web_server") or "nginx"),
            "CERT_METHOD": str(payload.get("cert_method") or "none"),
            "UFW_AUTO": str(bool(payload.get("ufw_auto") if "ufw_auto" in payload else True)).lower(),
            "UFW_STRICT": str(bool(payload.get("ufw_strict") if "ufw_strict" in payload else True)).lower(),
            "SSH_PORT": str(payload.get("ssh_port") or 22),
            "AGENT_PORT": str(payload.get("agent_port") or 8091),
        }
        panel_ips = payload.get("panel_ips")
        if isinstance(panel_ips, list):
            params["PANEL_IPS"] = ",".join(str(x).strip() for x in panel_ips if str(x).strip())
        elif payload.get("panel_ip") is not None:
            params["PANEL_IPS"] = str(payload.get("panel_ip") or "")
        bot_ips = payload.get("bot_ips")
        if isinstance(bot_ips, list):
            params["BOT_IPS"] = ",".join(str(x).strip() for x in bot_ips if str(x).strip())
        elif payload.get("bot_ip") is not None:
            params["BOT_IPS"] = str(payload.get("bot_ip") or "")
        if payload.get("cert_domain") is not None:
            params["CERT_DOMAIN"] = str(payload.get("cert_domain") or "")
        if payload.get("cert_email") is not None:
            params["CERT_EMAIL"] = str(payload.get("cert_email") or "")
        if payload.get("cloudflare_api_token") is not None:
            params["CLOUDFLARE_API_TOKEN"] = str(payload.get("cloudflare_api_token") or "")
        if payload.get("template_source") is not None:
            params["TEMPLATE_SOURCE"] = str(payload.get("template_source") or "builtin")
        if payload.get("compose_template_url") is not None:
            params["COMPOSE_TEMPLATE_URL"] = str(payload.get("compose_template_url") or "")
        if payload.get("web_template_url") is not None:
            params["WEB_TEMPLATE_URL"] = str(payload.get("web_template_url") or "")
        return params
    if path == "/v1/remnawave/stack":
        params = {
            "ACTION": str(payload.get("action") or "status"),
            "STACK": str(payload.get("stack") or "auto"),
        }
        if payload.get("service") is not None:
            params["SERVICE"] = str(payload.get("service") or "")
        if payload.get("lines") is not None:
            params["LOG_LINES"] = str(payload.get("lines"))
        return params
    if path == "/v1/ufw/action":
        params = {"UFW_ACTION": str(payload.get("action") or "enable")}
        if payload.get("rule_action") is not None:
            params["UFW_RULE_ACTION"] = str(payload.get("rule_action") or "")
        if payload.get("rule") is not None:
            params["UFW_RULE"] = str(payload.get("rule") or "")
        if payload.get("rule_num") is not None:
            params["UFW_RULE_NUM"] = str(payload.get("rule_num") or "")
        if payload.get("port") is not None:
            params["UFW_PORT"] = str(payload.get("port") or "")
        if payload.get("proto") is not None:
            params["UFW_PROTO"] = str(payload.get("proto") or "")
        if payload.get("from") is not None:
            params["UFW_FROM"] = str(payload.get("from") or "")
        if payload.get("to") is not None:
            params["UFW_TO"] = str(payload.get("to") or "")
        return params
    if path in {"/v1/fail2ban/action", "/v1/fail2ban/config"}:
        params = {"F2B_ACTION": str(payload.get("action") or ("config" if path.endswith("/config") else "restart"))}
        if payload.get("bantime") is not None:
            params["F2B_BANTIME"] = str(payload["bantime"])
        if payload.get("findtime") is not None:
            params["F2B_FINDTIME"] = str(payload["findtime"])
        if payload.get("maxretry") is not None:
            params["F2B_MAXRETRY"] = str(payload["maxretry"])
        return params
    if path == "/v1/security/certbot":
        params = {
            "CERT_ACTION": str(payload.get("action") or "status"),
            "CERT_METHOD": str(payload.get("method") or "http"),
        }
        if payload.get("domain") is not None:
            params["DOMAIN"] = str(payload.get("domain") or "")
        if payload.get("email") is not None:
            params["EMAIL"] = str(payload.get("email") or "")
        if payload.get("cloudflare_api_token") is not None:
            params["CLOUDFLARE_API_TOKEN"] = str(payload.get("cloudflare_api_token") or "")
        return params
    return _to_params(payload, {"dry_run", "confirm"})


def _config_path(name: str) -> Path:
    mapping = {
        "docker-compose": REMNANODE_DIR / "docker-compose.yml",
        "nginx": REMNANODE_DIR / "nginx.conf",
        "caddy": REMNANODE_DIR / "Caddyfile",
    }
    if name not in mapping:
        raise ValueError("name must be docker-compose|nginx|caddy")
    return mapping[name]


class Handler(BaseHTTPRequestHandler):
    server_version = f"InfraControlAgent/{AGENT_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        if AGENT_ACCESS_LOG:
            _log(logging.INFO, "http", client=self.client_address[0], msg=(fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        _log_debug("http_get", path=path, client=self.client_address[0])
        if path == "/health":
            _json_response(self, HTTPStatus.OK, {
                "ok": True,
                "status": "ok",
                "agent_id": AGENT_ID,
                "version": AGENT_VERSION,
                "hostname": platform.node(),
                "uptime_s": int(time.time() - AGENT_STARTED_AT),
                "docker_available": bool(shutil.which("docker")),
            })
            return
        if not _require_auth(self):
            return
        if path == "/v1/agent/info":
            _json_response(self, HTTPStatus.OK, {
                "ok": True,
                "agent": {"id": AGENT_ID, "version": AGENT_VERSION, "uptime_s": int(time.time() - AGENT_STARTED_AT)},
                "config": {
                    "http_host": AGENT_HTTP_HOST,
                    "http_port": AGENT_HTTP_PORT,
                    "token_configured": bool(AGENT_API_TOKEN),
                    "allow_empty_token": AGENT_ALLOW_EMPTY_TOKEN,
                    "max_active_jobs": AGENT_MAX_ACTIVE_JOBS,
                    "max_body_bytes": AGENT_MAX_BODY_BYTES,
                },
                "operations": sorted(OPERATIONS.keys()),
            })
            return
        if path == "/v1/actions":
            _prune_jobs()
            with JOBS_LOCK:
                jobs = [_job_public(j) for j in JOBS.values()]
            jobs.sort(key=lambda x: x["created_at"], reverse=True)
            _json_response(self, HTTPStatus.OK, {"ok": True, "jobs": jobs[:100]})
            return
        if path.startswith("/v1/actions/"):
            job_id = path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                j = JOBS.get(job_id)
            if not j:
                _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("job not found", "job_not_found"))
                return
            _json_response(self, HTTPStatus.OK, {"ok": True, "job": _job_public(j)})
            return
        if path == "/v1/security/status":
            op = OPERATIONS["security.status"]
            env = os.environ.copy()
            env["DRY_RUN"] = "false"
            result = _run_cmd(_op_exec_cmd(op), env=env, timeout_s=op.timeout_s)
            _json_response(self, HTTPStatus.OK if result["ok"] else HTTPStatus.SERVICE_UNAVAILABLE, {"ok": result["ok"], "result": result})
            return
        if path == "/v1/remnawave/config":
            query = parse_qs(parsed.query)
            name = str((query.get("name") or [""])[0]).strip()
            try:
                target = _config_path(name)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload(str(exc), "invalid_request"))
                return
            if not target.exists():
                _json_response(self, HTTPStatus.NOT_FOUND, _error_payload(f"config not found: {target}", "config_not_found"))
                return
            text = target.read_text(encoding="utf-8", errors="ignore")
            _json_response(self, HTTPStatus.OK, {"ok": True, "name": name, "path": str(target), "content": text})
            return
        _log_warning("route_not_found", method="GET", path=path)
        _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not found", "route_not_found"))

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        _log_debug("http_delete", path=path, client=self.client_address[0])
        if not _require_auth(self):
            return
        if path.startswith("/v1/actions/"):
            job_id = path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                j = JOBS.get(job_id)
                if j and j.get("status") in {"queued", "running"}:
                    _log_warning("job_delete_rejected_active", job_id=job_id)
                    _json_response(self, HTTPStatus.CONFLICT, _error_payload("cannot delete active job", "job_active"))
                    return
                removed = JOBS.pop(job_id, None)
            if not removed:
                _log_warning("job_delete_not_found", job_id=job_id)
                _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("job not found", "job_not_found"))
                return
            _log_info("job_deleted", job_id=job_id)
            _json_response(self, HTTPStatus.OK, {"ok": True, "removed": job_id})
            return
        _log_warning("route_not_found", method="DELETE", path=path)
        _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not found", "route_not_found"))

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        _log_debug("http_post", path=path, client=self.client_address[0])
        if not _require_auth(self):
            return
        try:
            payload = _read_json_body(self)
        except Exception as exc:
            _log_warning("request_bad_json", path=path, error=str(exc))
            _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload(str(exc), "invalid_request"))
            return

        if path == "/v1/actions/prune":
            _log_info("jobs_prune_requested", max_age_s=payload.get("max_age_s"), max_count=payload.get("max_count"))
            _json_response(self, HTTPStatus.OK, _prune_jobs(payload.get("max_age_s"), payload.get("max_count")))
            return

        if path == "/v1/remnawave/config":
            name = str(payload.get("name") or "").strip()
            content = payload.get("content")
            if not isinstance(content, str):
                _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload("content must be string", "invalid_request"))
                return
            backup = bool(payload.get("backup") if "backup" in payload else True)
            validate = bool(payload.get("validate") if "validate" in payload else True)
            restart = bool(payload.get("restart") if "restart" in payload else False)
            try:
                target = _config_path(name)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload(str(exc), "invalid_request"))
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            if backup and target.exists():
                backup_path = target.with_suffix(target.suffix + f".bak.{int(time.time())}")
                backup_path.write_text(target.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            target.write_text(content, encoding="utf-8")
            checks: dict[str, Any] = {"written": str(target)}
            if validate and name == "docker-compose":
                result = _run_cmd(["docker", "compose", "-f", str(target), "config"], env=os.environ.copy(), timeout_s=60)
                checks["compose_config"] = result
                if not result.get("ok"):
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        _error_payload("docker compose config validation failed", "compose_validation_failed", checks=checks),
                    )
                    return
            if restart:
                stack_payload = {"ACTION": "restart", "STACK": "node"}
                try:
                    job = _create_job("remnawave.stack", stack_payload, dry_run=False)
                except Exception as exc:
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        _error_payload(f"config saved but restart failed: {exc}", "restart_failed", checks=checks),
                    )
                    return
                _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "checks": checks, "job": job})
                return
            _json_response(self, HTTPStatus.OK, {"ok": True, "checks": checks})
            return

        if path == "/v1/actions/run":
            operation_id = str(payload.get("operation_id") or "").strip()
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            op = OPERATIONS.get(operation_id)
            if not op:
                _log_warning("job_run_unknown_operation", operation_id=operation_id)
                _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload("unknown operation_id", "unknown_operation"))
                return
            if not dry_run and op.confirm:
                confirm = str(payload.get("confirm") or "").strip().lower()
                if confirm != op.confirm:
                    _log_warning("job_run_confirm_mismatch", operation_id=operation_id, expected=op.confirm, got=confirm or "-")
                    _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload(f"confirm must be {op.confirm}", "confirm_required"))
                    return
            try:
                job = _create_job(operation_id, params, dry_run=dry_run)
            except RuntimeError as exc:
                _log_warning("job_run_rate_limited", operation_id=operation_id, error=str(exc))
                _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, _error_payload(str(exc), "too_many_active_jobs"))
                return
            except Exception as exc:
                _log_warning("job_run_failed", operation_id=operation_id, error=str(exc))
                _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload(str(exc), "job_create_failed"))
                return
            _log_info("job_run_accepted", operation_id=operation_id, job_id=job["id"], dry_run=dry_run)
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        alias: dict[str, str] = {
            "/v1/system/update": "system.update",
            "/v1/system/reboot": "system.reboot",
            "/v1/security/harden-ssh": "security.harden_ssh",
            "/v1/security/ssh-port": "security.ssh_port",
            "/v1/security/rollback": "security.rollback",
            "/v1/network/tuning": "network.bbr_cake",
            "/v1/network/ipv6": "network.ipv6",
            "/v1/services/update": "services.update",
            "/v1/remnawave/node/install": "remnawave.node_install",
            "/v1/remnawave/stack": "remnawave.stack",
            "/v1/ufw/action": "security.ufw",
            "/v1/fail2ban/action": "security.fail2ban",
            "/v1/fail2ban/config": "security.fail2ban",
            "/v1/security/certbot": "security.certbot",
        }
        if path in alias:
            op_id = alias[path]
            op = OPERATIONS[op_id]
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            if not dry_run and op.confirm:
                confirm = str(payload.get("confirm") or "").strip().lower()
                if confirm != op.confirm:
                    _log_warning("alias_confirm_mismatch", path=path, operation_id=op_id, expected=op.confirm, got=confirm or "-")
                    _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload(f"confirm must be {op.confirm}", "confirm_required"))
                    return
            params = _alias_params(path, payload)
            try:
                job = _create_job(op_id, params, dry_run=dry_run)
            except RuntimeError as exc:
                _log_warning("alias_rate_limited", path=path, operation_id=op_id, error=str(exc))
                _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, _error_payload(str(exc), "too_many_active_jobs"))
                return
            except Exception as exc:
                _log_warning("alias_run_failed", path=path, operation_id=op_id, error=str(exc))
                _json_response(self, HTTPStatus.BAD_REQUEST, _error_payload(str(exc), "job_create_failed"))
                return
            _log_info("alias_run_accepted", path=path, operation_id=op_id, job_id=job["id"], dry_run=dry_run)
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        _log_warning("route_not_found", method="POST", path=path)
        _json_response(self, HTTPStatus.NOT_FOUND, _error_payload("not found", "route_not_found"))


def main() -> None:
    _setup_logging()
    if not AGENT_API_TOKEN and not AGENT_ALLOW_EMPTY_TOKEN:
        _log_warning("agent_start_blocked_empty_token")
        raise SystemExit("AGENT_API_TOKEN is required")
    for op in OPERATIONS.values():
        if not op.script_path.exists():
            _log_warning("agent_start_blocked_missing_script", operation_id=op.operation_id, script=op.script_relpath)
            raise SystemExit(f"missing operation script: {op.script_relpath}")
    _log_info("agent_started", id=AGENT_ID, version=AGENT_VERSION, host=AGENT_HTTP_HOST, port=AGENT_HTTP_PORT, log_level=AGENT_LOG_LEVEL)
    ThreadingHTTPServer((AGENT_HTTP_HOST, AGENT_HTTP_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
