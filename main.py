from __future__ import annotations

<<<<<<< HEAD
=======
import hmac
>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)
import json
import logging
import os
import platform
import shutil
import subprocess
<<<<<<< HEAD
import time
import socket
import threading
import uuid
import hmac
import ipaddress
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
from typing import Any
from urllib.parse import parse_qs, quote, urlparse


class RequestBodyTooLarge(ValueError):
    pass


class JobRejected(RuntimeError):
    pass


def _env_int(name: str, default: int, *, min_value: int | None = None) -> int:
    try:
        value = int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default
    if min_value is not None:
        value = max(min_value, value)
    return value


def _has_unsafe_token(value: str) -> bool:
    return any(char.isspace() or char in ";|&`$<>" for char in value)


def _validate_simple_name(value: Any, *, field: str, max_len: int = 128, allow_dot: bool = True) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    allowed_extra = "_.-" if allow_dot else "_-"
    if len(text) > max_len or text.startswith("-") or any(not (char.isalnum() or char in allowed_extra) for char in text):
        raise ValueError(f"{field} contains unsupported characters")
    return text


def _validate_docker_container_ref(value: Any) -> str:
    text = str(value or "").strip().lstrip("/")
    if not text:
        raise ValueError("container is required")
    if len(text) > 128 or text.startswith("-") or _has_unsafe_token(text):
        raise ValueError("container contains unsupported characters")
    if any(not (char.isalnum() or char in "_.:-") for char in text):
        raise ValueError("container contains unsupported characters")
    return text


def _validate_fail2ban_jail(value: Any, *, default: str | None = None) -> str:
    raw = default if value in (None, "") and default is not None else value
    return _validate_simple_name(raw, field="jail", max_len=64)


def _validate_ip_or_cidr(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        if "/" in text:
            ipaddress.ip_network(text, strict=False)
        else:
            ipaddress.ip_address(text)
    except ValueError:
        raise ValueError(f"{field} must be an IP address or CIDR") from None
    return text


def _validate_tcp_udp_proto(value: Any, *, default: str = "tcp") -> str:
    proto = str(value or default).strip().lower()
    if proto not in ("tcp", "udp"):
        raise ValueError("proto must be tcp or udp")
    return proto


def _validate_port(value: Any, *, field: str = "port") -> str:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an integer") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"{field} must be from 1 to 65535")
    return str(port)


AGENT_VERSION = "0.3.3"
AGENT_ID = str(os.getenv("AGENT_ID") or platform.node() or "infra-control-agent").strip()
AGENT_API_TOKEN = str(os.getenv("AGENT_API_TOKEN") or "").strip()
AGENT_ALLOW_EMPTY_TOKEN = str(os.getenv("AGENT_ALLOW_EMPTY_TOKEN") or "false").strip().lower() in ("1", "true", "yes", "on")
AGENT_HTTP_HOST = str(os.getenv("AGENT_HTTP_HOST") or "0.0.0.0").strip()
AGENT_HTTP_PORT = int(os.getenv("AGENT_HTTP_PORT") or "8091")
AGENT_LOG_LEVEL = str(os.getenv("AGENT_LOG_LEVEL") or "info").strip().lower()
AGENT_ACCESS_LOG = str(os.getenv("AGENT_ACCESS_LOG") or "true").strip().lower() not in ("0", "false", "no", "off")
AGENT_HOST_ROOT = str(os.getenv("AGENT_HOST_ROOT") or "/host").rstrip("/")
AGENT_HOST_DISK_PATH = str(os.getenv("AGENT_HOST_DISK_PATH") or f"{AGENT_HOST_ROOT}/opt").strip()
AGENT_HOST_SYSCTL_DIR = str(os.getenv("AGENT_HOST_SYSCTL_DIR") or f"{AGENT_HOST_ROOT}/etc/sysctl.d").rstrip("/")
AGENT_HOST_PROC = str(os.getenv("AGENT_HOST_PROC") or f"{AGENT_HOST_ROOT}/proc").rstrip("/")
AGENT_ALLOWED_UPGRADES = {
    item.strip()
    for item in str(os.getenv("AGENT_ALLOWED_UPGRADES") or "panel,node,subscription").split(",")
    if item.strip()
}
DOCKER_BIN = str(
    os.getenv("AGENT_DOCKER_BIN")
    or shutil.which("docker")
    or ("/usr/bin/docker" if os.path.exists("/usr/bin/docker") else "")
).strip()
DOCKER_SOCKET = str(os.getenv("AGENT_DOCKER_SOCKET") or "/var/run/docker.sock").strip()
JOB_LOG_LIMIT = _env_int("AGENT_JOB_LOG_LIMIT", 30000, min_value=1000)
AGENT_JOB_MAX_COUNT = _env_int("AGENT_JOB_MAX_COUNT", 100, min_value=0)
AGENT_JOB_MAX_AGE_S = _env_int("AGENT_JOB_MAX_AGE_S", 86400, min_value=0)
AGENT_MAX_BODY_BYTES = _env_int("AGENT_MAX_BODY_BYTES", 65536, min_value=1024)
AGENT_MAX_ACTIVE_JOBS = _env_int("AGENT_MAX_ACTIVE_JOBS", 2, min_value=1)
AGENT_AUTH_FAIL_LIMIT = _env_int("AGENT_AUTH_FAIL_LIMIT", 10, min_value=1)
AGENT_AUTH_FAIL_WINDOW_S = _env_int("AGENT_AUTH_FAIL_WINDOW_S", 300, min_value=1)
AGENT_AUTH_FAIL_BLOCK_S = _env_int("AGENT_AUTH_FAIL_BLOCK_S", 300, min_value=1)
AGENT_STARTED_AT = time.time()
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
AUTH_FAILURES: dict[str, dict[str, Any]] = {}
AUTH_FAILURES_LOCK = threading.Lock()
UPGRADE_PROFILES = {
    "panel": "/opt/remnawave",
    "node": "/opt/remnanode",
    "subscription": "/opt/remnawave/subscription",
}
TUNING_PROFILES = {
    "bbr_fq": {
        "name": "BBR + fq",
        "description": "Enable fq queue discipline and BBR TCP congestion control.",
        "settings": {
            "net.core.default_qdisc": "fq",
            "net.ipv4.tcp_congestion_control": "bbr",
        },
        "disable_settings": {
            "net.core.default_qdisc": "fq_codel",
            "net.ipv4.tcp_congestion_control": "cubic",
        },
    }
}
TUNING_CONFIG_NAME = "99-infra-control-agent-tuning.conf"
FAIL2BAN_CONFIG_PATH = "/etc/fail2ban/jail.local"
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "off": logging.CRITICAL + 10,
    "none": logging.CRITICAL + 10,
}
LOGGER = logging.getLogger("infra-control-agent")


def _setup_logging() -> None:
    level = LOG_LEVELS.get(AGENT_LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    logging.Formatter.converter = time.gmtime
    LOGGER.setLevel(level)


def _log(level: int, event: str, **fields: Any) -> None:
    if not LOGGER.isEnabledFor(level):
        return
    parts = [f"event={event}"]
    for key, value in fields.items():
        if value is None:
            continue
        safe_value = str(value).replace("\n", "\\n")
        parts.append(f"{key}={safe_value}")
    LOGGER.log(level, " ".join(parts))


def _log_debug(event: str, **fields: Any) -> None:
    _log(logging.DEBUG, event, **fields)


def _log_info(event: str, **fields: Any) -> None:
    _log(logging.INFO, event, **fields)


def _log_warning(event: str, **fields: Any) -> None:
    _log(logging.WARNING, event, **fields)


def _log_error(event: str, **fields: Any) -> None:
    _log(logging.ERROR, event, **fields)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_to_ts(value: Any) -> float:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return 0.0


def _run_cmd(cmd: list[str], *, timeout_s: int = 120) -> dict[str, Any]:
    started = time.time()
    _log_debug("command_start", command=" ".join(cmd), timeout_s=timeout_s)
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        result = {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "duration_ms": int((time.time() - started) * 1000),
        }
        _log_debug(
            "command_finish",
            command=" ".join(cmd),
            ok=result["ok"],
            exit_code=result["exit_code"],
            duration_ms=result["duration_ms"],
        )
        return result
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.time() - started) * 1000)
        _log_warning("command_timeout", command=" ".join(cmd), timeout_s=timeout_s, duration_ms=duration_ms)
=======
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def _setup_logging() -> None:
    level = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
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
    "network.bbr_cake": Operation("network.bbr_cake", "network/01_bbr_cake.sh", timeout_s=120, confirm="network_tuning"),
    "services.update": Operation("services.update", "services/01_update_services.sh", timeout_s=7200, confirm="services_update"),
    "remnawave.node_install": Operation("remnawave.node_install", "remnawave/01_install_node.sh", timeout_s=1800, confirm="install_node"),
}


def _run_cmd(cmd: list[str], env: dict[str, str], timeout_s: int) -> dict[str, Any]:
    started = time.time()
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=timeout_s, check=False)
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": (p.stdout or "")[-12000:],
            "stderr": (p.stderr or "")[-12000:],
            "duration_ms": int((time.time() - started) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)
        return {
            "ok": False,
            "exit_code": None,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
<<<<<<< HEAD
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "command timed out",
            "duration_ms": duration_ms,
        }


def _run_cmd_in_dir(cmd: list[str], *, cwd: str | None = None, timeout_s: int = 120) -> dict[str, Any]:
    started = time.time()
    _log_debug("command_start", command=" ".join(cmd), cwd=cwd, timeout_s=timeout_s)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        result = {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "duration_ms": int((time.time() - started) * 1000),
        }
        _log_debug(
            "command_finish",
            command=" ".join(cmd),
            cwd=cwd,
            ok=result["ok"],
            exit_code=result["exit_code"],
            duration_ms=result["duration_ms"],
        )
        return result
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.time() - started) * 1000)
        _log_warning("command_timeout", command=" ".join(cmd), cwd=cwd, timeout_s=timeout_s, duration_ms=duration_ms)
        return {
            "ok": False,
            "exit_code": None,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "command timed out",
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        _log_error("command_error", command=" ".join(cmd), cwd=cwd, error=exc, duration_ms=duration_ms)
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": duration_ms,
        }


def _host_nsenter_prefix() -> list[str]:
    nsenter = shutil.which("nsenter")
    if not nsenter:
        return []
    proc = AGENT_HOST_PROC
    namespaces = [
        ("--mount", os.path.join(proc, "1/ns/mnt")),
        ("--uts", os.path.join(proc, "1/ns/uts")),
        ("--ipc", os.path.join(proc, "1/ns/ipc")),
        ("--net", os.path.join(proc, "1/ns/net")),
    ]
    args = [nsenter]
    used = False
    for flag, path in namespaces:
        if os.path.exists(path):
            args.append(f"{flag}={path}")
            used = True
    if not used:
        return []
    args.append("--")
    return args


def _host_cmd(cmd: list[str], *, timeout_s: int = 120) -> dict[str, Any]:
    prefix = _host_nsenter_prefix()
    return _run_cmd([*prefix, *cmd], timeout_s=timeout_s)


def _host_job_step(title: str, cmd: list[str], *, timeout_s: int = 120) -> dict[str, Any]:
    prefix = _host_nsenter_prefix()
    return {"title": title, "cmd": [*prefix, *cmd], "timeout_s": timeout_s}


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
    except OSError:
        return ""


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


def _remove_file(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


def _host_metrics() -> dict[str, Any]:
    uptime_raw = _read_text("/proc/uptime").split()
    uptime_s = int(float(uptime_raw[0])) if uptime_raw else None
    load = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
    disk_path = AGENT_HOST_DISK_PATH if os.path.exists(AGENT_HOST_DISK_PATH) else "/"
    disk = shutil.disk_usage(disk_path)

    mem_total_kb = 0
    mem_available_kb = 0
    for line in _read_text("/proc/meminfo").splitlines():
        key, _, value = line.partition(":")
        if key == "MemTotal":
            mem_total_kb = int(value.strip().split()[0])
        elif key == "MemAvailable":
            mem_available_kb = int(value.strip().split()[0])

    mem_used_kb = max(0, mem_total_kb - mem_available_kb)
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "uptime_s": uptime_s,
        "loadavg": {
            "1m": load[0],
            "5m": load[1],
            "15m": load[2],
        },
        "memory": {
            "total_mb": mem_total_kb // 1024 if mem_total_kb else None,
            "used_mb": mem_used_kb // 1024 if mem_total_kb else None,
            "available_mb": mem_available_kb // 1024 if mem_available_kb else None,
            "used_percent": round((mem_used_kb / mem_total_kb) * 100, 2) if mem_total_kb else None,
        },
        "disk": {
            "path": disk_path,
            "total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
            "used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
            "free_gb": round(disk.free / 1024 / 1024 / 1024, 2),
            "used_percent": round((disk.used / disk.total) * 100, 2) if disk.total else None,
        },
    }


def _host_diagnostics() -> dict[str, Any]:
    host = _host_metrics()
    return {
        "ok": True,
        "host": host,
        "checks": {
            "load": host["loadavg"],
            "memory": host["memory"],
            "disk": host["disk"],
            "docker_available": _docker_available(),
            "host_mounts": {
                "host_root": os.path.exists(AGENT_HOST_ROOT),
                "host_opt": os.path.exists(AGENT_HOST_DISK_PATH),
                "host_proc": os.path.exists(AGENT_HOST_PROC),
                "host_sysctl_dir": os.path.exists(AGENT_HOST_SYSCTL_DIR),
            },
        },
    }


def _parse_json_lines(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def _parse_percent(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().rstrip("%")
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def _split_pair(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    parts = [part.strip() for part in str(value).split("/", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return str(value), None


def _normalize_docker_stats(stat: dict[str, Any]) -> dict[str, Any]:
    memory_used, memory_limit = _split_pair(stat.get("MemUsage"))
    network_rx, network_tx = _split_pair(stat.get("NetIO"))
    block_read, block_write = _split_pair(stat.get("BlockIO"))
    return {
        "cpu_percent": _parse_percent(stat.get("CPUPerc")),
        "cpu_percent_text": stat.get("CPUPerc"),
        "memory": {
            "usage": memory_used,
            "limit": memory_limit,
            "percent": _parse_percent(stat.get("MemPerc")),
            "percent_text": stat.get("MemPerc"),
        },
        "network": {
            "rx": network_rx,
            "tx": network_tx,
            "raw": stat.get("NetIO"),
        },
        "block_io": {
            "read": block_read,
            "write": block_write,
            "raw": stat.get("BlockIO"),
        },
        "pids": int(stat["PIDs"]) if str(stat.get("PIDs") or "").isdigit() else stat.get("PIDs"),
    }


def _network_totals(networks: dict[str, Any]) -> tuple[int, int]:
    rx = 0
    tx = 0
    for item in networks.values():
        if isinstance(item, dict):
            rx += int(item.get("rx_bytes") or 0)
            tx += int(item.get("tx_bytes") or 0)
    return rx, tx


def _block_totals(items: list[dict[str, Any]]) -> tuple[int, int]:
    read = 0
    write = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op") or "").lower()
        value = int(item.get("value") or 0)
        if op == "read":
            read += value
        elif op == "write":
            write += value
    return read, write


def _normalize_docker_api_stats(stats: dict[str, Any]) -> dict[str, Any]:
    cpu_stats = stats.get("cpu_stats") or {}
    precpu_stats = stats.get("precpu_stats") or {}
    cpu_delta = int((cpu_stats.get("cpu_usage") or {}).get("total_usage") or 0) - int(
        (precpu_stats.get("cpu_usage") or {}).get("total_usage") or 0
    )
    system_delta = int(cpu_stats.get("system_cpu_usage") or 0) - int(precpu_stats.get("system_cpu_usage") or 0)
    online_cpus = int(cpu_stats.get("online_cpus") or len((cpu_stats.get("cpu_usage") or {}).get("percpu_usage") or []) or 1)
    cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100, 2) if system_delta > 0 and cpu_delta >= 0 else None

    memory_stats = stats.get("memory_stats") or {}
    memory_usage = int(memory_stats.get("usage") or 0)
    memory_limit = int(memory_stats.get("limit") or 0)
    memory_percent = round((memory_usage / memory_limit) * 100, 2) if memory_limit else None
    network_rx, network_tx = _network_totals(stats.get("networks") or {})
    block_read, block_write = _block_totals(((stats.get("blkio_stats") or {}).get("io_service_bytes_recursive") or []))
    pids = (stats.get("pids_stats") or {}).get("current")
    return {
        "cpu_percent": cpu_percent,
        "memory": {
            "usage_bytes": memory_usage,
            "limit_bytes": memory_limit,
            "percent": memory_percent,
        },
        "network": {
            "rx_bytes": network_rx,
            "tx_bytes": network_tx,
        },
        "block_io": {
            "read_bytes": block_read,
            "write_bytes": block_write,
        },
        "pids": pids,
    }


def _with_optional_raw(resources: dict[str, Any], raw: dict[str, Any], include_raw: bool) -> dict[str, Any]:
    if include_raw:
        resources["raw"] = raw
    return resources


def _parse_size_bytes(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    number = ""
    unit = ""
    for char in text:
        if char.isdigit() or char == ".":
            number += char
        elif not char.isspace():
            unit += char
    try:
        amount = float(number)
    except ValueError:
        return None

    unit = unit.lower()
    multipliers = {
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }
    return int(amount * multipliers.get(unit, 1))


def _resource_cpu_percent(container: dict[str, Any]) -> float | None:
    value = (container.get("resources") or {}).get("cpu_percent")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _resource_memory_bytes(container: dict[str, Any]) -> int | None:
    memory = (container.get("resources") or {}).get("memory") or {}
    if memory.get("usage_bytes") is not None:
        return int(memory["usage_bytes"])
    return _parse_size_bytes(memory.get("usage"))


def _status_health(status: Any) -> str | None:
    text = str(status or "").lower()
    if "(unhealthy)" in text:
        return "unhealthy"
    if "(healthy)" in text:
        return "healthy"
    if "(health: starting)" in text:
        return "starting"
    return None


def _container_hints(name: str, state: str, status: Any) -> dict[str, Any]:
    state_l = state.lower()
    health = _status_health(status)
    recommended_actions = []
    attention = "ok"

    if state_l == "restarting":
        attention = "critical"
        recommended_actions.append({"action": "view_logs", "container": name, "reason": "container is restarting"})
    elif state_l not in ("running", "created"):
        attention = "warning"
        recommended_actions.append({"action": "restart_container", "container": name, "reason": f"container state is {state_l or 'unknown'}"})

    if health == "unhealthy":
        attention = "critical"
        recommended_actions.append({"action": "view_logs", "container": name, "reason": "container healthcheck is unhealthy"})
        recommended_actions.append({"action": "restart_container", "container": name, "reason": "container healthcheck is unhealthy"})
    elif health == "starting" and attention == "ok":
        attention = "warning"

    return {
        "health": health,
        "attention": attention,
        "actions": {
            "can_view_logs": True,
            "can_restart": True,
        },
        "recommended_actions": recommended_actions,
    }


def _compose_command() -> list[str] | None:
    if DOCKER_BIN and _run_cmd([DOCKER_BIN, "compose", "version"], timeout_s=15)["ok"]:
        return [DOCKER_BIN, "compose"]
    docker_compose = shutil.which("docker-compose")
    if docker_compose and _run_cmd([docker_compose, "version"], timeout_s=15)["ok"]:
        return [docker_compose]
    return None


class UnixHTTPConnection(HTTPConnection):
    def __init__(self, socket_path: str, *, timeout: int = 120) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _docker_available() -> bool:
    return os.path.exists(DOCKER_SOCKET) or (bool(DOCKER_BIN) and bool(os.getenv("DOCKER_HOST")))


def _docker_api_request(
    method: str,
    path: str,
    *,
    timeout_s: int = 120,
    body: bytes | None = None,
    docker_log_stream: bool = False,
) -> dict[str, Any]:
    started = time.time()
    _log_debug("docker_api_request_start", method=method, path=path, timeout_s=timeout_s)
    if not os.path.exists(DOCKER_SOCKET):
        _log_warning("docker_socket_missing", socket=DOCKER_SOCKET)
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": f"docker socket is not available: {DOCKER_SOCKET}",
            "duration_ms": 0,
        }

    conn = UnixHTTPConnection(DOCKER_SOCKET, timeout=timeout_s)
    try:
        conn.request(method, path, body=body)
        response = conn.getresponse()
        raw = response.read()
        if docker_log_stream:
            raw = _decode_docker_log_stream(raw)
        text = raw.decode("utf-8", errors="replace")
        ok = 200 <= response.status < 300
        result = {
            "ok": ok,
            "exit_code": 0 if ok else response.status,
            "stdout": text[-12000:] if ok else "",
            "stderr": "" if ok else text[-12000:],
            "duration_ms": int((time.time() - started) * 1000),
        }
        _log_debug(
            "docker_api_request_finish",
            method=method,
            path=path,
            ok=ok,
            status=response.status,
            duration_ms=result["duration_ms"],
        )
        return result
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        _log_error("docker_api_request_error", method=method, path=path, error=exc, duration_ms=duration_ms)
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": duration_ms,
        }
    finally:
        conn.close()


def _docker_system_df() -> dict[str, Any]:
    if DOCKER_BIN:
        return _run_cmd([DOCKER_BIN, "system", "df"], timeout_s=30)
    result = _docker_api_request("GET", "/system/df", timeout_s=30)
    if not result["ok"]:
        return result
    try:
        data = json.loads(result["stdout"] or "{}")
    except json.JSONDecodeError:
        return result
    return {
        "ok": True,
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "duration_ms": result["duration_ms"],
        "summary": _docker_system_df_summary(data),
    }


def _docker_usage() -> dict[str, Any]:
    if DOCKER_BIN:
        result = _run_cmd([DOCKER_BIN, "system", "df", "--format", "{{json .}}"], timeout_s=30)
        if result["ok"]:
            rows = _parse_json_lines(result["stdout"])
            summary = _docker_system_df_cli_summary(rows)
            return {"ok": True, "source": "docker_cli", "summary": summary}

    if os.path.exists(DOCKER_SOCKET):
        result = _docker_api_request("GET", "/system/df", timeout_s=30)
        if result["ok"]:
            try:
                data = json.loads(result["stdout"] or "{}")
                return {"ok": True, "source": "docker_api", "summary": _docker_system_df_summary(data)}
            except json.JSONDecodeError:
                pass
        elif not DOCKER_BIN:
            return result
    result = _docker_system_df()
    if result.get("summary"):
        return {"ok": True, "summary": result["summary"]}
    return result


def _sum_usage(items: Any) -> tuple[int, int]:
    total = 0
    reclaimable = 0
    for item in items or []:
        if not isinstance(item, dict):
            continue
        total += int((item.get("UsageData") or {}).get("Size") or item.get("Size") or 0)
        if not item.get("InUse"):
            reclaimable += int((item.get("UsageData") or {}).get("Size") or item.get("Size") or 0)
    return total, reclaimable


def _docker_system_df_summary(data: dict[str, Any]) -> dict[str, Any]:
    images = data.get("Images") or []
    containers = data.get("Containers") or []
    volumes = (data.get("Volumes") or data.get("VolumeUsage") or {}).get("Items") or []
    build_cache = (data.get("BuildCache") or data.get("BuildCacheUsage") or {}).get("Items") or []
    image_total, image_reclaimable = _sum_usage(images)
    container_total, container_reclaimable = _sum_usage(containers)
    volume_total, volume_reclaimable = _sum_usage(volumes)
    build_total, build_reclaimable = _sum_usage(build_cache)
    return {
        "images": {"count": len(images), "size_bytes": image_total, "reclaimable_bytes": image_reclaimable},
        "containers": {"count": len(containers), "size_bytes": container_total, "reclaimable_bytes": container_reclaimable},
        "volumes": {"count": len(volumes), "size_bytes": volume_total, "reclaimable_bytes": volume_reclaimable},
        "build_cache": {"count": len(build_cache), "size_bytes": build_total, "reclaimable_bytes": build_reclaimable},
        "total_reclaimable_bytes": image_reclaimable + container_reclaimable + volume_reclaimable + build_reclaimable,
    }


def _reclaimable_size(value: Any) -> int:
    text = str(value or "").split("(", 1)[0].strip()
    return _parse_size_bytes(text) or 0


def _docker_system_df_cli_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mapping = {
        "Images": "images",
        "Containers": "containers",
        "Local Volumes": "volumes",
        "Build Cache": "build_cache",
    }
    summary = {
        "images": {"count": 0, "size_bytes": 0, "reclaimable_bytes": 0},
        "containers": {"count": 0, "size_bytes": 0, "reclaimable_bytes": 0},
        "volumes": {"count": 0, "size_bytes": 0, "reclaimable_bytes": 0},
        "build_cache": {"count": 0, "size_bytes": 0, "reclaimable_bytes": 0},
        "total_reclaimable_bytes": 0,
    }
    for row in rows:
        key = mapping.get(str(row.get("Type") or ""))
        if not key:
            continue
        summary[key] = {
            "count": int(row.get("TotalCount") or 0),
            "active": int(row.get("Active") or 0),
            "size_bytes": _parse_size_bytes(row.get("Size")) or 0,
            "reclaimable_bytes": _reclaimable_size(row.get("Reclaimable")),
            "size": row.get("Size"),
            "reclaimable": row.get("Reclaimable"),
        }
    summary["total_reclaimable_bytes"] = sum(
        int(summary[key]["reclaimable_bytes"])
        for key in ("images", "containers", "volumes", "build_cache")
    )
    return summary


def _decode_docker_log_stream(raw: bytes) -> bytes:
    frames: list[bytes] = []
    pos = 0
    while pos + 8 <= len(raw):
        stream_type = raw[pos]
        size = int.from_bytes(raw[pos + 4 : pos + 8], "big")
        next_pos = pos + 8 + size
        if stream_type not in (1, 2) or next_pos > len(raw):
            return raw
        frames.append(raw[pos + 8 : next_pos])
        pos = next_pos
    if pos != len(raw):
        return raw
    return b"".join(frames)


def _docker_ps() -> dict[str, Any]:
    if DOCKER_BIN:
        return _run_cmd([DOCKER_BIN, "ps", "--format", "{{.ID}} {{.Names}} {{.Status}}"], timeout_s=30)

    result = _docker_api_request("GET", "/containers/json", timeout_s=30)
    if not result["ok"]:
        return result

    containers = json.loads(result["stdout"] or "[]")
    lines = []
    for container in containers:
        container_id = str(container.get("Id") or "")[:12]
        names = container.get("Names") or []
        name = str(names[0]).lstrip("/") if names else ""
        status = str(container.get("Status") or "")
        lines.append(f"{container_id} {name} {status}".strip())
    result["stdout"] = "\n".join(lines)
    return result


def _docker_logs_tail(container: str, tail: int) -> dict[str, Any]:
    container = _validate_docker_container_ref(container)
    if DOCKER_BIN:
        return _run_cmd([DOCKER_BIN, "logs", "--tail", str(tail), container], timeout_s=60)

    path = f"/containers/{quote(container, safe='')}/logs?stdout=1&stderr=1&tail={tail}"
    return _docker_api_request("GET", path, timeout_s=60, docker_log_stream=True)


def _docker_restart(container: str) -> dict[str, Any]:
    container = _validate_docker_container_ref(container)
    if DOCKER_BIN:
        return _run_cmd([DOCKER_BIN, "restart", container], timeout_s=60)

    result = _docker_api_request("POST", f"/containers/{quote(container, safe='')}/restart", timeout_s=60)
    if result["ok"]:
        result["stdout"] = container
    return result


def _docker_container_action(container: str, action: str) -> dict[str, Any]:
    container = _validate_docker_container_ref(container)
    if action not in ("start", "stop", "restart"):
        raise ValueError("action must be one of: start, stop, restart")
    if action == "restart":
        return _docker_restart(container)
    if DOCKER_BIN:
        return _run_cmd([DOCKER_BIN, action, container], timeout_s=60)
    result = _docker_api_request("POST", f"/containers/{quote(container, safe='')}/{action}", timeout_s=60)
    if result["ok"]:
        result["stdout"] = container
    return result


def _docker_containers() -> dict[str, Any]:
    if DOCKER_BIN:
        ps_result = _run_cmd(
            [DOCKER_BIN, "ps", "-a", "--no-trunc", "--format", "{{json .}}"],
            timeout_s=30,
        )
        if not ps_result["ok"]:
            return ps_result

        stats_result = _run_cmd(
            [DOCKER_BIN, "stats", "--no-stream", "--format", "{{json .}}"],
            timeout_s=45,
        )
        stats_by_name: dict[str, dict[str, Any]] = {}
        stats_by_id: dict[str, dict[str, Any]] = {}
        if stats_result["ok"]:
            for stat in _parse_json_lines(stats_result["stdout"]):
                if stat.get("Name"):
                    stats_by_name[str(stat["Name"])] = stat
                if stat.get("Container"):
                    stats_by_id[str(stat["Container"])] = stat

        containers = []
        for row in _parse_json_lines(ps_result["stdout"]):
            container_id = str(row.get("ID") or "")
            name = str(row.get("Names") or "")
            state = str(row.get("State") or "")
            stat = stats_by_name.get(name) or stats_by_id.get(container_id[:12]) or {}
            hints = _container_hints(name, state, row.get("Status"))
            containers.append(
                {
                    "id": container_id[:12],
                    "name": name,
                    "image": row.get("Image"),
                    "state": state,
                    "status": row.get("Status"),
                    "running": state.lower() == "running",
                    "ports": row.get("Ports"),
                    "networks": row.get("Networks"),
                    "resources": _normalize_docker_stats(stat) if stat else {},
                    "health": hints["health"],
                    "attention": hints["attention"],
                    "actions": hints["actions"],
                    "recommended_actions": hints["recommended_actions"],
                }
            )

        return {"ok": True, "containers": containers, "count": len(containers)}

    result = _docker_api_request("GET", "/containers/json?all=1", timeout_s=30)
    if not result["ok"]:
        return result

    containers = []
    for container in json.loads(result["stdout"] or "[]"):
        names = container.get("Names") or []
        state = str(container.get("State") or "")
        name = str(names[0]).lstrip("/") if names else ""
        hints = _container_hints(name, state, container.get("Status"))
        containers.append(
            {
                "id": str(container.get("Id") or "")[:12],
                "name": name,
                "image": container.get("Image"),
                "state": state,
                "status": container.get("Status"),
                "running": state.lower() == "running",
                "ports": container.get("Ports"),
                "networks": container.get("NetworkSettings", {}).get("Networks"),
                "resources": {},
                "health": hints["health"],
                "attention": hints["attention"],
                "actions": hints["actions"],
                "recommended_actions": hints["recommended_actions"],
            }
        )
    return {"ok": True, "containers": containers, "count": len(containers)}


def _docker_container_detail(container: str, *, include_raw: bool = False) -> dict[str, Any]:
    container = _validate_docker_container_ref(container)
    if DOCKER_BIN:
        inspect_result = _run_cmd([DOCKER_BIN, "inspect", container], timeout_s=30)
        if not inspect_result["ok"]:
            return inspect_result
        inspect_data = json.loads(inspect_result["stdout"] or "[]")
        if not inspect_data:
            return {"ok": False, "error": "container not found"}

        stats_result = _run_cmd([DOCKER_BIN, "stats", "--no-stream", "--format", "{{json .}}", container], timeout_s=45)
        stat = _parse_json_lines(stats_result["stdout"])[0] if stats_result["ok"] and stats_result["stdout"].strip() else {}
        resources = _normalize_docker_stats(stat) if stat else {}
        data = inspect_data[0]
        state = data.get("State") or {}
        config = data.get("Config") or {}
        network_settings = data.get("NetworkSettings") or {}
        name = str(data.get("Name") or "").lstrip("/")
        health = ((state.get("Health") or {}).get("Status")) or _status_health(state.get("Status"))
        hints = _container_hints(name, str(state.get("Status") or ""), f"({health})" if health else "")
        return {
            "ok": True,
            "container": {
                "id": str(data.get("Id") or "")[:12],
                "full_id": data.get("Id"),
                "name": name,
                "image": config.get("Image"),
                "created": data.get("Created"),
                "state": {
                    "status": state.get("Status"),
                    "running": state.get("Running"),
                    "started_at": state.get("StartedAt"),
                    "finished_at": state.get("FinishedAt"),
                    "exit_code": state.get("ExitCode"),
                    "error": state.get("Error"),
                },
                "restart_count": data.get("RestartCount"),
                "ports": network_settings.get("Ports"),
                "networks": network_settings.get("Networks"),
                "resources": _with_optional_raw(resources, stat, include_raw) if stat else {},
                "health": health,
                "attention": hints["attention"],
                "actions": hints["actions"],
                "recommended_actions": hints["recommended_actions"],
            },
        }

    quoted = quote(container, safe="")
    inspect_result = _docker_api_request("GET", f"/containers/{quoted}/json", timeout_s=30)
    if not inspect_result["ok"]:
        return inspect_result
    stats_result = _docker_api_request("GET", f"/containers/{quoted}/stats?stream=0", timeout_s=45)
    data = json.loads(inspect_result["stdout"] or "{}")
    state = data.get("State") or {}
    config = data.get("Config") or {}
    network_settings = data.get("NetworkSettings") or {}
    raw_stats = json.loads(stats_result["stdout"] or "{}") if stats_result["ok"] else {}
    resources = _normalize_docker_api_stats(raw_stats) if stats_result["ok"] else {}
    name = str(data.get("Name") or "").lstrip("/")
    health = ((state.get("Health") or {}).get("Status")) or _status_health(state.get("Status"))
    hints = _container_hints(name, str(state.get("Status") or ""), f"({health})" if health else "")
    return {
        "ok": True,
        "container": {
            "id": str(data.get("Id") or "")[:12],
            "full_id": data.get("Id"),
            "name": name,
            "image": config.get("Image"),
            "created": data.get("Created"),
            "state": {
                "status": state.get("Status"),
                "running": state.get("Running"),
                "started_at": state.get("StartedAt"),
                "finished_at": state.get("FinishedAt"),
                "exit_code": state.get("ExitCode"),
                "error": state.get("Error"),
            },
            "restart_count": data.get("RestartCount"),
            "ports": network_settings.get("Ports"),
            "networks": network_settings.get("Networks"),
            "resources": _with_optional_raw(resources, raw_stats, include_raw) if stats_result["ok"] else {},
            "health": health,
            "attention": hints["attention"],
            "actions": hints["actions"],
            "recommended_actions": hints["recommended_actions"],
        },
    }


def _node_summary() -> dict[str, Any]:
    host = _host_metrics()
    docker_ok = _docker_available()
    containers_result = _docker_containers() if docker_ok else {"ok": False, "containers": []}
    containers = containers_result.get("containers") if containers_result.get("ok") else []
    running = [item for item in containers if item.get("running")]
    stopped = [item for item in containers if not item.get("running")]
    problems = []
    if not docker_ok:
        problems.append("docker is not available")
    if containers_result.get("ok") is False:
        problems.append(str(containers_result.get("stderr") or containers_result.get("error") or "cannot read containers"))
    if stopped:
        names = ", ".join(str(item.get("name") or item.get("id")) for item in stopped[:5])
        suffix = f" and {len(stopped) - 5} more" if len(stopped) > 5 else ""
        problems.append(f"stopped containers: {names}{suffix}")

    status = "ok" if docker_ok and containers_result.get("ok") and not stopped else "degraded"
    severity = "ok"
    if not docker_ok or containers_result.get("ok") is False:
        severity = "critical"
    elif any(item.get("attention") == "critical" for item in containers):
        severity = "critical"
    elif stopped or any(item.get("attention") == "warning" for item in containers):
        severity = "warning"

    recommended_actions = []
    for item in containers:
        recommended_actions.extend(item.get("recommended_actions") or [])

    mem = host.get("memory") or {}
    disk = host.get("disk") or {}
    resource_alerts = []
    if (mem.get("used_percent") or 0) >= 90:
        resource_alerts.append({"resource": "memory", "severity": "critical", "value": mem.get("used_percent")})
    elif (mem.get("used_percent") or 0) >= 80:
        resource_alerts.append({"resource": "memory", "severity": "warning", "value": mem.get("used_percent")})
    if (disk.get("used_percent") or 0) >= 90:
        resource_alerts.append({"resource": "disk", "severity": "critical", "value": disk.get("used_percent"), "path": disk.get("path")})
    elif (disk.get("used_percent") or 0) >= 80:
        resource_alerts.append({"resource": "disk", "severity": "warning", "value": disk.get("used_percent"), "path": disk.get("path")})

    containers_by_cpu = sorted(
        (item for item in containers if _resource_cpu_percent(item) is not None),
        key=lambda item: _resource_cpu_percent(item) or 0,
        reverse=True,
    )
    containers_by_memory = sorted(
        (item for item in containers if _resource_memory_bytes(item) is not None),
        key=lambda item: _resource_memory_bytes(item) or 0,
        reverse=True,
    )
    insights = {
        "severity": severity,
        "recommended_actions": recommended_actions[:10],
        "resource_alerts": resource_alerts,
        "top_containers_by_cpu": containers_by_cpu[:5],
        "top_containers_by_memory": containers_by_memory[:5],
    }
    return {
        "ok": status == "ok",
        "status": status,
        "severity": severity,
        "agent": {
            "id": AGENT_ID,
            "version": AGENT_VERSION,
        },
        "host": host,
        "docker": {
            "available": docker_ok,
            "containers_total": len(containers),
            "containers_running": len(running),
            "containers_stopped": len(stopped),
        },
        "containers": containers,
        "problems": problems,
        "recommended_actions": insights["recommended_actions"],
        "resource_alerts": resource_alerts,
        "insights": insights,
    }


def _append_job_log(job: dict[str, Any], text: str) -> None:
    job["log"] = str(job.get("log") or "") + text
    if len(job["log"]) > JOB_LOG_LIMIT:
        job["log"] = job["log"][-JOB_LOG_LIMIT:]
=======
            "stderr": ((exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "command timed out"),
            "duration_ms": int((time.time() - started) * 1000),
        }


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
    return {"ok": True, "removed": removed, "remaining": len(JOBS)}
>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)


def _job_public(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
<<<<<<< HEAD
        "action": job["action"],
        "category": job.get("category"),
        "target": job.get("target"),
=======
        "operation_id": job["operation_id"],
>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)
        "status": job["status"],
        "created_at": job["created_at"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
<<<<<<< HEAD
        "ok": job.get("ok"),
        "steps": job.get("steps", []),
        "log": job.get("log", ""),
        "error": job.get("error"),
    }


def _job_category(action: str) -> str:
    if action in ("ufw_action", "ufw_rule"):
        return "firewall"
    if action in ("fail2ban_action", "fail2ban_config", "fail2ban_jail_action"):
        return "fail2ban"
    if action in ("server_tuning_enable", "server_tuning_disable"):
        return "server_tuning"
    return action


def _active_jobs_locked() -> list[dict[str, Any]]:
    return [
        job
        for job in JOBS.values()
        if job.get("status") in ("queued", "running")
    ]


def _prune_jobs(*, max_age_s: int | None = None, max_count: int | None = None) -> dict[str, Any]:
    max_age_s = AGENT_JOB_MAX_AGE_S if max_age_s is None else max_age_s
    max_count = AGENT_JOB_MAX_COUNT if max_count is None else max_count
    now = time.time()
    removed: list[str] = []
    with JOBS_LOCK:
        for job_id, job in list(JOBS.items()):
            age_s = now - _iso_to_ts(job.get("created_at"))
            if max_age_s >= 0 and age_s > max_age_s and job.get("status") not in ("queued", "running"):
                removed.append(job_id)
                JOBS.pop(job_id, None)
        if max_count >= 0 and len(JOBS) > max_count:
            removable = [
                job for job in JOBS.values()
                if job.get("status") not in ("queued", "running")
            ]
            removable.sort(key=lambda item: item.get("created_at") or "")
            for job in removable[: max(0, len(JOBS) - max_count)]:
                removed.append(str(job["id"]))
                JOBS.pop(str(job["id"]), None)
    if removed:
        _log_info("jobs_pruned", removed=len(removed), max_age_s=max_age_s, max_count=max_count)
    return {"ok": True, "removed": removed, "removed_count": len(removed), "max_age_s": max_age_s, "max_count": max_count}


def _run_job(job_id: str, commands: list[dict[str, Any]]) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["started_at"] = _now_iso()
        action = job["action"]
        target = job.get("target")
    _log_info("job_started", job_id=job_id, action=action, target=target, steps=len(commands))

    ok = True
    for command in commands:
        cmd = command.get("cmd", [])
        cwd = command.get("cwd")
        title = command.get("title") or " ".join(cmd)
        with JOBS_LOCK:
            job = JOBS[job_id]
            job["steps"].append({"title": title, "status": "running", "started_at": _now_iso()})
            step_index = len(job["steps"]) - 1
            _append_job_log(job, f"\n$ {title}\n")
        _log_info("job_step_started", job_id=job_id, step=step_index + 1, title=title)

        if command.get("type") == "docker_api":
            result = _docker_api_request(
                str(command.get("method") or "POST"),
                str(command["path"]),
                timeout_s=int(command.get("timeout_s") or 600),
            )
        else:
            result = _run_cmd_in_dir(cmd, cwd=cwd, timeout_s=int(command.get("timeout_s") or 600))

        fail_marker = command.get("fail_on_output_contains")
        if fail_marker and fail_marker in f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}":
            result["ok"] = False
            result["exit_code"] = result.get("exit_code") or 1
            result["stderr"] = (result.get("stderr") or "") + f"\nmatched failure marker: {fail_marker}\n"

        with JOBS_LOCK:
            job = JOBS[job_id]
            job["steps"][step_index].update(
                {
                    "status": "succeeded" if result["ok"] else "failed",
                    "finished_at": _now_iso(),
                    "exit_code": result["exit_code"],
                    "duration_ms": result["duration_ms"],
                }
            )
            if result.get("stdout"):
                _append_job_log(job, result["stdout"])
            if result.get("stderr"):
                _append_job_log(job, result["stderr"])
        if result["ok"]:
            _log_info("job_step_succeeded", job_id=job_id, step=step_index + 1, title=title, duration_ms=result["duration_ms"])
        else:
            _log_error(
                "job_step_failed",
                job_id=job_id,
                step=step_index + 1,
                title=title,
                exit_code=result["exit_code"],
                duration_ms=result["duration_ms"],
                stderr=result.get("stderr", "")[-500:],
            )

        if not result["ok"]:
            ok = False
            break

    with JOBS_LOCK:
        job = JOBS[job_id]
        job["ok"] = ok
        job["status"] = "succeeded" if ok else "failed"
        job["finished_at"] = _now_iso()
        if not ok:
            job["error"] = "one or more steps failed"
    _log_info("job_finished", job_id=job_id, action=action, target=target, ok=ok)
    _prune_jobs()


def _create_job(action: str, target: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    category = _job_category(action)
    job = {
        "id": job_id,
        "action": action,
        "category": category,
        "target": target,
        "status": "queued",
        "created_at": _now_iso(),
        "steps": [],
        "log": "",
        "ok": None,
    }
    with JOBS_LOCK:
        active_jobs = _active_jobs_locked()
        if len(active_jobs) >= AGENT_MAX_ACTIVE_JOBS:
            raise JobRejected(f"too many active jobs: {len(active_jobs)} of {AGENT_MAX_ACTIVE_JOBS}")
        if any(job.get("category") == category for job in active_jobs):
            raise JobRejected(f"job category is already active: {category}")
        JOBS[job_id] = job
    _prune_jobs()
    _log_info("job_queued", job_id=job_id, action=action, target=target, steps=len(commands))
    thread = threading.Thread(target=_run_job, args=(job_id, commands), daemon=True)
    thread.start()
    return _job_public(job)


def _docker_prune_plan(target: str, include_volumes: bool) -> list[dict[str, Any]]:
    if target == "images":
        if DOCKER_BIN:
            return [{"title": "docker image prune", "cmd": [DOCKER_BIN, "image", "prune", "-f"], "timeout_s": 300}]
        return [{"type": "docker_api", "title": "docker image prune", "method": "POST", "path": "/images/prune", "timeout_s": 300}]
    if target == "containers":
        if DOCKER_BIN:
            return [{"title": "docker container prune", "cmd": [DOCKER_BIN, "container", "prune", "-f"], "timeout_s": 300}]
        return [
            {
                "type": "docker_api",
                "title": "docker container prune",
                "method": "POST",
                "path": "/containers/prune",
                "timeout_s": 300,
            }
        ]
    if target == "builder":
        if DOCKER_BIN:
            return [{"title": "docker builder prune", "cmd": [DOCKER_BIN, "builder", "prune", "-f"], "timeout_s": 300}]
        return [{"type": "docker_api", "title": "docker builder prune", "method": "POST", "path": "/build/prune", "timeout_s": 300}]
    if target == "system":
        if DOCKER_BIN:
            cmd = [DOCKER_BIN, "system", "prune", "-f"]
            if include_volumes:
                cmd.append("--volumes")
            return [{"title": "docker system prune", "cmd": cmd, "timeout_s": 600}]
        commands = [
            {"type": "docker_api", "title": "docker container prune", "method": "POST", "path": "/containers/prune", "timeout_s": 300},
            {"type": "docker_api", "title": "docker network prune", "method": "POST", "path": "/networks/prune", "timeout_s": 300},
            {"type": "docker_api", "title": "docker image prune", "method": "POST", "path": "/images/prune", "timeout_s": 300},
            {"type": "docker_api", "title": "docker builder prune", "method": "POST", "path": "/build/prune", "timeout_s": 300},
        ]
        if include_volumes:
            commands.append(
                {"type": "docker_api", "title": "docker volume prune", "method": "POST", "path": "/volumes/prune", "timeout_s": 300}
            )
        return commands
    raise ValueError("target must be one of: images, containers, builder, system")


def _upgrade_plan(profile: str) -> tuple[str, list[dict[str, Any]]]:
    if profile not in UPGRADE_PROFILES:
        raise ValueError("profile must be one of: panel, node, subscription")
    if profile not in AGENT_ALLOWED_UPGRADES:
        raise PermissionError(f"upgrade profile is not allowed: {profile}")

    compose = _compose_command()
    if not compose:
        raise RuntimeError("docker compose or docker-compose is required for upgrade")

    host_path = UPGRADE_PROFILES[profile]
    workdir = f"{AGENT_HOST_ROOT}{host_path}" if AGENT_HOST_ROOT else host_path
    if not os.path.isdir(workdir):
        raise FileNotFoundError(f"upgrade directory is not mounted or does not exist: {workdir}")

    return workdir, [
        {"title": f"{profile}: docker compose pull", "cmd": [*compose, "pull"], "cwd": workdir, "timeout_s": 900},
        {"title": f"{profile}: docker compose down", "cmd": [*compose, "down"], "cwd": workdir, "timeout_s": 300},
        {"title": f"{profile}: docker compose up -d", "cmd": [*compose, "up", "-d"], "cwd": workdir, "timeout_s": 600},
        {
            "title": f"{profile}: docker compose logs --tail 200",
            "cmd": [*compose, "logs", "--tail", "200"],
            "cwd": workdir,
            "timeout_s": 120,
        },
    ]


def _remnawave_profiles() -> dict[str, Any]:
    compose_available = _compose_command() is not None
    profiles = []
    for profile, host_path in UPGRADE_PROFILES.items():
        workdir = f"{AGENT_HOST_ROOT}{host_path}" if AGENT_HOST_ROOT else host_path
        compose_files = [
            os.path.join(workdir, "docker-compose.yml"),
            os.path.join(workdir, "docker-compose.yaml"),
            os.path.join(workdir, "compose.yml"),
            os.path.join(workdir, "compose.yaml"),
        ]
        directory_exists = os.path.isdir(workdir)
        compose_file = next((path for path in compose_files if os.path.isfile(path)), None)
        allowed = profile in AGENT_ALLOWED_UPGRADES
        available = bool(allowed and directory_exists and compose_file and compose_available)
        reason = None
        if not allowed:
            reason = "profile is not allowed"
        elif not directory_exists:
            reason = "upgrade directory is not mounted or does not exist"
        elif not compose_file:
            reason = "compose file was not found"
        elif not compose_available:
            reason = "docker compose or docker-compose is not available"
        profiles.append(
            {
                "profile": profile,
                "host_path": host_path,
                "workdir": workdir,
                "allowed": allowed,
                "directory_exists": directory_exists,
                "compose_file": compose_file,
                "compose_available": compose_available,
                "available": available,
                "can_upgrade": available,
                "reason": reason,
            }
        )
    return {
        "ok": True,
        "profiles": profiles,
        "available_profiles": [item["profile"] for item in profiles if item["available"]],
    }


def _command_exists(name: str) -> bool:
    name = _validate_simple_name(name, field="command", max_len=64)
    return _host_cmd(["which", name], timeout_s=15)["ok"]


def _systemctl_available() -> bool:
    return _command_exists("systemctl")


def _service_control_available() -> dict[str, Any]:
    if not _systemctl_available():
        return {"available": False, "reason": "systemctl is not available"}
    result = _host_cmd(["systemctl", "is-system-running"], timeout_s=15)
    stderr = str(result.get("stderr") or "").strip()
    stdout = str(result.get("stdout") or "").strip()
    if "Failed to connect to bus" in stderr:
        return {
            "available": False,
            "reason": "systemd bus is not available; run agent with pid: host",
            "stdout": stdout,
            "stderr": stderr,
        }
    return {
        "available": True,
        "state": stdout or "unknown",
        "exit_code": result.get("exit_code"),
    }


def _service_status(service: str) -> dict[str, Any]:
    service = _validate_simple_name(service, field="service", max_len=64)
    installed = _command_exists(service) or _host_cmd(["systemctl", "status", service, "--no-pager"], timeout_s=20)["exit_code"] in (0, 3)
    active_result = _host_cmd(["systemctl", "is-active", service], timeout_s=15) if _systemctl_available() else {"ok": False, "stdout": ""}
    enabled_result = _host_cmd(["systemctl", "is-enabled", service], timeout_s=15) if _systemctl_available() else {"ok": False, "stdout": ""}
    return {
        "installed": installed,
        "active": active_result["ok"],
        "state": active_result.get("stdout", "").strip() or "unknown",
        "enabled": enabled_result["ok"],
        "enabled_state": enabled_result.get("stdout", "").strip() or "unknown",
    }


def _service_action_plan(service: str, action: str) -> list[dict[str, Any]]:
    service = _validate_simple_name(service, field="service", max_len=64)
    if action not in ("start", "stop", "restart", "enable", "disable"):
        raise ValueError("action must be one of: start, stop, restart, enable, disable")
    return [_host_job_step(f"systemctl {action} {service}", ["systemctl", action, service], timeout_s=120)]


def _apt_install_plan(package: str) -> list[dict[str, Any]]:
    package = _validate_simple_name(package, field="package", max_len=64)
    return [
        _host_job_step("apt-get update", ["apt-get", "update"], timeout_s=900),
        _host_job_step(f"apt-get install -y {package}", ["apt-get", "install", "-y", package], timeout_s=900),
    ]


def _agent_info() -> dict[str, Any]:
    mounts = {
        "host_root": {"path": AGENT_HOST_ROOT, "exists": os.path.exists(AGENT_HOST_ROOT)},
        "host_opt": {"path": AGENT_HOST_DISK_PATH, "exists": os.path.exists(AGENT_HOST_DISK_PATH)},
        "host_sysctl_dir": {"path": AGENT_HOST_SYSCTL_DIR, "exists": os.path.exists(AGENT_HOST_SYSCTL_DIR)},
        "host_proc": {"path": AGENT_HOST_PROC, "exists": os.path.exists(AGENT_HOST_PROC)},
        "docker_socket": {"path": DOCKER_SOCKET, "exists": os.path.exists(DOCKER_SOCKET)},
    }
    return {
        "ok": True,
        "agent": {
            "id": AGENT_ID,
            "version": AGENT_VERSION,
            "uptime_s": int(time.time() - AGENT_STARTED_AT),
        },
        "config": {
            "http_host": AGENT_HTTP_HOST,
            "http_port": AGENT_HTTP_PORT,
            "token_configured": bool(AGENT_API_TOKEN),
            "allow_empty_token": AGENT_ALLOW_EMPTY_TOKEN,
            "log_level": AGENT_LOG_LEVEL,
            "access_log": AGENT_ACCESS_LOG,
            "allowed_upgrades": sorted(AGENT_ALLOWED_UPGRADES),
            "job_max_count": AGENT_JOB_MAX_COUNT,
            "job_max_age_s": AGENT_JOB_MAX_AGE_S,
            "job_log_limit": JOB_LOG_LIMIT,
            "max_active_jobs": AGENT_MAX_ACTIVE_JOBS,
            "max_body_bytes": AGENT_MAX_BODY_BYTES,
            "auth_fail_limit": AGENT_AUTH_FAIL_LIMIT,
            "auth_fail_window_s": AGENT_AUTH_FAIL_WINDOW_S,
            "auth_fail_block_s": AGENT_AUTH_FAIL_BLOCK_S,
        },
        "docker": {
            "available": _docker_available(),
            "mode": "cli" if DOCKER_BIN else "socket",
            "docker_bin": DOCKER_BIN or None,
            "socket": DOCKER_SOCKET,
        },
        "host_access": {
            "nsenter": bool(_host_nsenter_prefix()),
            "namespaces": _namespace_diagnostics(),
            "mounts": mounts,
            "service_control": _service_control_available(),
        },
    }


def _log_security_posture() -> None:
    public_bind = AGENT_HTTP_HOST in ("0.0.0.0", "::", "")
    if public_bind:
        _log_warning("security_public_bind", host=AGENT_HTTP_HOST, port=AGENT_HTTP_PORT)
    if AGENT_ALLOW_EMPTY_TOKEN:
        _log_error("security_empty_token_allowed", host=AGENT_HTTP_HOST)
    if AGENT_ALLOW_EMPTY_TOKEN and public_bind:
        _log_error("security_unsafe_empty_token_public_bind", message="empty token is not allowed with a public bind")
        raise SystemExit(2)
    _log_info(
        "security_posture",
        token_configured=bool(AGENT_API_TOKEN),
        allow_empty_token=AGENT_ALLOW_EMPTY_TOKEN,
        docker_socket=os.path.exists(DOCKER_SOCKET),
        host_root=os.path.exists(AGENT_HOST_ROOT),
        host_opt=os.path.exists(AGENT_HOST_DISK_PATH),
        host_proc=os.path.exists(AGENT_HOST_PROC),
        host_sysctl_dir=os.path.exists(AGENT_HOST_SYSCTL_DIR),
        max_active_jobs=AGENT_MAX_ACTIVE_JOBS,
        max_body_bytes=AGENT_MAX_BODY_BYTES,
    )


def _reboot_plan() -> list[dict[str, Any]]:
    return [
        _host_job_step(
            "reboot host",
            ["sh", "-lc", "systemctl reboot || reboot || shutdown -r now"],
            timeout_s=30,
        )
    ]


def _ufw_status() -> dict[str, Any]:
    installed = _command_exists("ufw")
    service = _service_status("ufw")
    result = _host_cmd(["ufw", "status", "verbose"], timeout_s=30) if installed else {"ok": False, "stdout": "", "stderr": "ufw is not installed"}
    numbered = _host_cmd(["ufw", "status", "numbered"], timeout_s=30) if installed else {"ok": False, "stdout": ""}
    status_text = result.get("stdout", "")
    numbered_text = numbered.get("stdout", "")
    return {
        "ok": True,
        "installed": installed,
        "service": service,
        "firewall": _parse_ufw_status(status_text),
        "rules": _parse_ufw_numbered(numbered_text),
        "raw": {
            "status": status_text,
            "numbered": numbered_text,
        },
    }


def _parse_ufw_status(text: str) -> dict[str, Any]:
    firewall = {"status": "unknown", "logging": None, "default": None}
    for line in text.splitlines():
        clean = line.strip()
        if clean.lower().startswith("status:"):
            firewall["status"] = clean.split(":", 1)[1].strip().lower()
        elif clean.lower().startswith("logging:"):
            firewall["logging"] = clean.split(":", 1)[1].strip()
        elif clean.lower().startswith("default:"):
            firewall["default"] = clean.split(":", 1)[1].strip()
    firewall["active"] = firewall["status"] == "active"
    return firewall


def _parse_ufw_numbered(text: str) -> list[dict[str, Any]]:
    rules = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean.startswith("["):
            continue
        number_text, _, rest = clean[1:].partition("]")
        try:
            number = int(number_text.strip())
        except ValueError:
            continue
        rules.append({"number": number, "rule": rest.strip()})
    return rules


def _ufw_action_plan(action: str) -> list[dict[str, Any]]:
    if action == "install":
        return [*_apt_install_plan("ufw"), *_service_action_plan("ufw", "enable"), *_service_action_plan("ufw", "start")]
    if action == "enable":
        return [_host_job_step("ufw --force enable", ["ufw", "--force", "enable"], timeout_s=120)]
    if action == "disable":
        return [_host_job_step("ufw disable", ["ufw", "disable"], timeout_s=120)]
    if action in ("start", "stop", "restart"):
        return _service_action_plan("ufw", action)
    raise ValueError("action must be one of: install, enable, disable, start, stop, restart")


def _ufw_rule_plan(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    action = str(payload.get("action") or "").strip().lower()
    if action not in ("allow", "deny", "reject", "delete"):
        raise ValueError("action must be one of: allow, deny, reject, delete")
    rule = str(payload.get("rule") or "").strip()
    number = payload.get("number")
    if action == "delete" and number is not None:
        try:
            number_text = str(int(number))
        except (TypeError, ValueError):
            raise ValueError("number must be an integer") from None
        command = _host_job_step(f"ufw --force delete {number_text}", ["ufw", "--force", "delete", number_text], timeout_s=120)
        command["fail_on_output_contains"] = "Could not delete non-existent rule"
        return f"delete {number_text}", [command]
    if not rule and payload.get("port") is not None:
        proto = _validate_tcp_udp_proto(payload.get("proto"))
        port = _validate_port(payload.get("port"))
        cmd = ["ufw", action]
        from_ip = str(payload.get("from") or payload.get("from_ip") or "").strip()
        to_ip = str(payload.get("to") or payload.get("to_ip") or "").strip()
        if from_ip:
            cmd.extend(["from", _validate_ip_or_cidr(from_ip, field="from")])
        if to_ip:
            cmd.extend(["to", _validate_ip_or_cidr(to_ip, field="to")])
        cmd.extend(["port", port, "proto", proto])
        command = _host_job_step(" ".join(cmd), cmd, timeout_s=120)
        return f"{action} port {port}/{proto}", [command]
    if not rule:
        raise ValueError("rule is required")
    parts = rule.split()
    if any(part.startswith("-") or ";" in part or "|" in part or "&" in part for part in parts):
        raise ValueError("rule contains unsupported tokens")
    cmd = ["ufw", action, *parts]
    if action == "delete":
        cmd = ["ufw", "--force", "delete", *parts]
    command = _host_job_step(" ".join(cmd), cmd, timeout_s=120)
    if action == "delete":
        command["fail_on_output_contains"] = "Could not delete non-existent rule"
    return f"{action} {rule}", [command]


def _fail2ban_status(jail: str | None = None) -> dict[str, Any]:
    if jail:
        jail = _validate_fail2ban_jail(jail)
    installed = _command_exists("fail2ban-client")
    service = _service_status("fail2ban")
    status = _host_cmd(["fail2ban-client", "status"], timeout_s=30) if installed else {"ok": False, "stdout": "", "stderr": "fail2ban is not installed"}
    payload = {
        "ok": True,
        "installed": installed,
        "service": service,
        "summary": _parse_fail2ban_status(status.get("stdout", "")),
        "raw": {
            "status": status,
        },
    }
    if jail:
        payload["jail"] = jail
        jail_status = _host_cmd(["fail2ban-client", "status", jail], timeout_s=30) if installed else {"ok": False, "stderr": "fail2ban is not installed"}
        payload["jail_status"] = _parse_fail2ban_jail_status(jail_status.get("stdout", ""))
        payload["raw"]["jail_status"] = jail_status
    return payload


def _fail2ban_default_config() -> dict[str, Any]:
    return {
        "bantime": "30m",
        "findtime": "10m",
        "maxretry": 10,
        "backend": "systemd",
        "sshd_enabled": True,
        "sshd_port": "22",
        "sshd_filter": "sshd",
    }


def _fail2ban_config_text(config: dict[str, Any]) -> str:
    sshd_enabled = "true" if bool(config["sshd_enabled"]) else "false"
    return "\n".join(
        [
            "[DEFAULT]",
            f"bantime = {config['bantime']}",
            f"findtime = {config['findtime']}",
            f"maxretry = {config['maxretry']}",
            f"backend = {config['backend']}",
            "",
            "[sshd]",
            f"enabled = {sshd_enabled}",
            f"port = {config['sshd_port']}",
            f"filter = {config['sshd_filter']}",
            "",
        ]
    )


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on", "enabled"):
        return True
    if text in ("0", "false", "no", "off", "disabled"):
        return False
    raise ValueError("boolean value must be true or false")


def _validate_fail2ban_duration(name: str, value: Any) -> str:
    text = str(value).strip().lower()
    if not text:
        raise ValueError(f"{name} is required")
    if text.isdigit():
        number = int(text)
        if 1 <= number <= 31536000:
            return text
    elif len(text) > 1 and text[:-1].isdigit() and text[-1] in ("s", "m", "h", "d", "w"):
        number = int(text[:-1])
        if 1 <= number <= 525600:
            return text
    raise ValueError(f"{name} must be seconds or a duration like 30m, 1h, 1d")


def _validate_fail2ban_port(value: Any) -> str:
    text = str(value).strip()
    if text == "ssh":
        return text
    if text.isdigit() and 1 <= int(text) <= 65535:
        return text
    raise ValueError("sshd_port must be ssh or a TCP port from 1 to 65535")


def _validate_fail2ban_config(payload: dict[str, Any], *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    allowed = {"bantime", "findtime", "maxretry", "backend", "sshd_enabled", "sshd_port"}
    unknown = sorted(set(payload) - allowed - {"dry_run", "confirm"})
    if unknown:
        raise ValueError(f"unsupported fail2ban config fields: {', '.join(unknown)}")

    config = dict(base or _fail2ban_default_config())
    if "bantime" in payload:
        config["bantime"] = _validate_fail2ban_duration("bantime", payload["bantime"])
    if "findtime" in payload:
        config["findtime"] = _validate_fail2ban_duration("findtime", payload["findtime"])
    if "maxretry" in payload:
        try:
            maxretry = int(payload["maxretry"])
        except (TypeError, ValueError):
            raise ValueError("maxretry must be an integer") from None
        if not 1 <= maxretry <= 100:
            raise ValueError("maxretry must be between 1 and 100")
        config["maxretry"] = maxretry
    if "backend" in payload:
        backend = str(payload["backend"]).strip().lower()
        if backend not in ("systemd", "auto", "polling", "pyinotify"):
            raise ValueError("backend must be one of: systemd, auto, polling, pyinotify")
        config["backend"] = backend
    if "sshd_enabled" in payload:
        config["sshd_enabled"] = _parse_bool(payload["sshd_enabled"])
    if "sshd_port" in payload:
        config["sshd_port"] = _validate_fail2ban_port(payload["sshd_port"])
    config["sshd_filter"] = "sshd"
    return config


def _fail2ban_config_from_text(text: str) -> dict[str, Any]:
    config = _fail2ban_default_config()
    section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        key_l = key.lower()
        if section == "default" and key_l in ("bantime", "findtime", "backend"):
            config[key_l] = value
        elif section == "default" and key_l == "maxretry":
            try:
                config["maxretry"] = int(value)
            except ValueError:
                config["maxretry"] = value
        elif section == "sshd" and key_l == "enabled":
            config["sshd_enabled"] = value.lower() in ("1", "true", "yes", "on")
        elif section == "sshd" and key_l == "port":
            config["sshd_port"] = value
        elif section == "sshd" and key_l == "filter":
            config["sshd_filter"] = value
    return config


def _fail2ban_config() -> dict[str, Any]:
    exists_result = _host_cmd(["test", "-f", FAIL2BAN_CONFIG_PATH], timeout_s=15)
    exists = exists_result["ok"]
    result = _host_cmd(["cat", FAIL2BAN_CONFIG_PATH], timeout_s=15) if exists else {"ok": False, "stdout": ""}
    raw = result.get("stdout", "") if result.get("ok") else ""
    config = _fail2ban_config_from_text(raw) if raw else _fail2ban_default_config()
    return {
        "ok": True,
        "path": FAIL2BAN_CONFIG_PATH,
        "exists": exists,
        "config": config,
        "raw": raw,
        "defaults": _fail2ban_default_config(),
    }


def _fail2ban_config_plan(config: dict[str, Any], *, restart: bool = True) -> list[dict[str, Any]]:
    text = _fail2ban_config_text(config)
    commands = [
        _host_job_step(
            "write /etc/fail2ban/jail.local",
            ["sh", "-lc", f"mkdir -p /etc/fail2ban && cat > {FAIL2BAN_CONFIG_PATH} <<'EOF'\n{text}EOF\n"],
            timeout_s=30,
        ),
    ]
    if restart:
        commands.extend(_service_action_plan("fail2ban", "restart"))
    return commands


def _parse_fail2ban_status(text: str) -> dict[str, Any]:
    jails: list[str] = []
    jail_count = 0
    for line in text.splitlines():
        clean = line.strip()
        if "Number of jail:" in clean:
            try:
                jail_count = int(clean.rsplit(":", 1)[1].strip())
            except ValueError:
                jail_count = 0
        elif "Jail list:" in clean:
            jails = [item.strip() for item in clean.rsplit(":", 1)[1].split(",") if item.strip()]
    return {"jail_count": jail_count, "jails": jails}


def _parse_fail2ban_jail_status(text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {"filter": {}, "actions": {}}
    for line in text.splitlines():
        clean = line.strip().lstrip("|-`")
        if ":" not in clean:
            continue
        key, value = [part.strip() for part in clean.split(":", 1)]
        key_l = key.lower().replace(" ", "_")
        if key_l in ("currently_failed", "total_failed", "file_list"):
            parsed["filter"][key_l] = value
        elif key_l in ("currently_banned", "total_banned", "banned_ip_list"):
            parsed["actions"][key_l] = value
        elif key_l == "status_for_the_jail":
            parsed["jail"] = value
    return parsed


def _fail2ban_action_plan(action: str) -> list[dict[str, Any]]:
    if action == "install":
        return [
            *_apt_install_plan("fail2ban"),
            *_fail2ban_config_plan(_fail2ban_default_config(), restart=False),
            *_service_action_plan("fail2ban", "enable"),
            *_service_action_plan("fail2ban", "restart"),
        ]
    if action in ("start", "stop", "restart", "enable", "disable"):
        return _service_action_plan("fail2ban", action)
    raise ValueError("action must be one of: install, start, stop, restart, enable, disable")


def _fail2ban_jail_action(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    action = str(payload.get("action") or "").strip().lower()
    jail = _validate_fail2ban_jail(payload.get("jail"), default="sshd")
    if action not in ("banip", "unbanip"):
        raise ValueError("action must be banip or unbanip")
    ip = _validate_ip_or_cidr(payload.get("ip"), field="ip")
    title = f"fail2ban-client set {jail} {action} {ip}"
    return title, [_host_job_step(title, ["fail2ban-client", "set", jail, action, ip], timeout_s=60)]


def _tuning_config_path() -> str:
    return os.path.join(AGENT_HOST_SYSCTL_DIR, TUNING_CONFIG_NAME)


def _host_netns_path() -> str:
    return os.path.join(AGENT_HOST_PROC, "1/ns/net")


def _readlink(path: str) -> str:
    try:
        return os.readlink(path)
    except OSError:
        return ""


def _namespace_diagnostics() -> dict[str, Any]:
    container_netns = _readlink("/proc/self/ns/net")
    host_netns_path = _host_netns_path()
    host_netns = _readlink(host_netns_path)
    return {
        "container_netns": container_netns,
        "host_netns_path": host_netns_path,
        "host_netns": host_netns,
        "same_netns": bool(container_netns and host_netns and container_netns == host_netns),
    }


def _nsenter_sysctl_cmd(key: str, value: str | None = None) -> list[str] | None:
    nsenter = shutil.which("nsenter")
    sysctl = shutil.which("sysctl")
    netns = _host_netns_path()
    if not nsenter or not sysctl or not os.path.exists(netns):
        return None
    if value is None:
        return [nsenter, f"--net={netns}", sysctl, "-n", key]
    return [nsenter, f"--net={netns}", sysctl, "-w", f"{key}={value}"]


def _sysctl_get(key: str) -> dict[str, Any]:
    namespaces = _namespace_diagnostics()
    if namespaces["same_netns"] and shutil.which("sysctl"):
        result = _run_cmd(["sysctl", "-n", key], timeout_s=15)
        if result["ok"]:
            return {"ok": True, "key": key, "value": result["stdout"].strip(), "source": "host_network"}

    nsenter_cmd = _nsenter_sysctl_cmd(key)
    if nsenter_cmd:
        result = _run_cmd(nsenter_cmd, timeout_s=15)
        if result["ok"]:
            return {"ok": True, "key": key, "value": result["stdout"].strip(), "source": "host_netns", "namespaces": namespaces}

    proc_path = os.path.join(AGENT_HOST_PROC, "sys", *key.split("."))
    if os.path.exists(proc_path):
        return {"ok": True, "key": key, "value": _read_text(proc_path).strip(), "source": proc_path, "namespaces": namespaces}
    if not shutil.which("sysctl"):
        return {"ok": False, "key": key, "value": None, "error": "sysctl command is not available"}
    result = _run_cmd(["sysctl", "-n", key], timeout_s=15)
    return {
        "ok": result["ok"],
        "key": key,
        "value": result["stdout"].strip() if result["ok"] else None,
        "error": result["stderr"].strip() if not result["ok"] else None,
        "source": "sysctl",
        "namespaces": namespaces,
    }


def _tuning_status(profile: str = "bbr_fq") -> dict[str, Any]:
    if profile not in TUNING_PROFILES:
        raise ValueError("profile must be one of: bbr_fq")

    profile_data = TUNING_PROFILES[profile]
    settings = profile_data["settings"]
    disable_settings = profile_data["disable_settings"]
    current = {key: _sysctl_get(key) for key in settings}
    runtime_applied = all(current[key].get("value") == value for key, value in settings.items())
    runtime_disabled = all(current[key].get("value") == value for key, value in disable_settings.items())

    config_path = _tuning_config_path()
    config_text = _read_text(config_path)
    configured_enabled = all(
        f"{key} = {value}" in config_text or f"{key}={value}" in config_text for key, value in settings.items()
    )
    configured_disabled = all(
        f"{key} = {value}" in config_text or f"{key}={value}" in config_text
        for key, value in disable_settings.items()
    )

    if runtime_applied and configured_enabled:
        state = "enabled"
        recommended_action = "disable"
    elif runtime_applied:
        state = "enabled_external"
        recommended_action = "enable"
    elif configured_enabled:
        state = "configured_pending_apply"
        recommended_action = "enable"
    elif runtime_disabled and configured_disabled:
        state = "disabled"
        recommended_action = "enable"
    elif configured_disabled:
        state = "disabled_configured_pending_apply"
        recommended_action = "disable"
    else:
        state = "disabled"
        recommended_action = "enable"
    _log_debug(
        "server_tuning_status_checked",
        profile=profile,
        state=state,
        runtime_applied=runtime_applied,
        runtime_disabled=runtime_disabled,
        configured_enabled=configured_enabled,
        configured_disabled=configured_disabled,
    )

    return {
        "ok": True,
        "profile": profile,
        "name": profile_data["name"],
        "description": profile_data["description"],
        "state": state,
        "enabled": runtime_applied,
        "runtime_applied": runtime_applied,
        "runtime_disabled": runtime_disabled,
        "configured": configured_enabled,
        "configured_enabled": configured_enabled,
        "configured_disabled": configured_disabled,
        "recommended_action": recommended_action,
        "config_path": config_path,
        "namespaces": _namespace_diagnostics(),
        "settings": settings,
        "disable_settings": disable_settings,
        "current": current,
    }


def _sysctl_set_commands(settings: dict[str, str]) -> list[dict[str, Any]]:
    commands = []
    sysctl = shutil.which("sysctl")
    if not sysctl:
        return commands

    for key, value in settings.items():
        nsenter_cmd = _nsenter_sysctl_cmd(key, value)
        if nsenter_cmd:
            commands.append(
                {
                    "title": f"apply host sysctl {key}={value}",
                    "cmd": nsenter_cmd,
                    "timeout_s": 30,
                }
            )
        else:
            commands.append(
                {
                    "title": f"apply sysctl {key}={value}",
                    "cmd": [sysctl, "-w", f"{key}={value}"],
                    "timeout_s": 30,
                }
            )
    return commands


def _tuning_config_text(profile: str, settings_key: str = "settings") -> str:
    profile_data = TUNING_PROFILES[profile]
    lines = [
        "# Managed by infra-control-agent.",
        "# Change via POST /v1/server/tuning.",
    ]
    for key, value in profile_data[settings_key].items():
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def _tuning_apply(profile: str, action: str, *, dry_run: bool = False) -> dict[str, Any]:
    if profile not in TUNING_PROFILES:
        raise ValueError("profile must be one of: bbr_fq")
    if action not in ("enable", "disable"):
        raise ValueError("action must be enable or disable")

    status_before = _tuning_status(profile)
    config_path = _tuning_config_path()
    settings = TUNING_PROFILES[profile]["settings"]
    disable_settings = TUNING_PROFILES[profile]["disable_settings"]

    if dry_run:
        _log_info("server_tuning_dry_run", profile=profile, action=action, state_before=status_before["state"])
        return {
            "ok": True,
            "dry_run": True,
            "action": action,
            "profile": profile,
            "config_path": config_path,
            "status": status_before,
            "would_write": True,
            "would_apply_runtime": True,
            "settings": settings if action == "enable" else disable_settings,
        }

    os.makedirs(AGENT_HOST_SYSCTL_DIR, exist_ok=True)

    if action == "enable":
        _write_text(config_path, _tuning_config_text(profile))
        _log_warning("server_tuning_config_written", profile=profile, action=action, config_path=config_path)
        commands = _sysctl_set_commands(settings)
        if commands:
            job = _create_job("server_tuning_enable", profile, commands)
            return {"ok": True, "status_before": status_before, "job": job}
        return {
            "ok": True,
            "status_before": status_before,
            "warning": "config written, but sysctl command is not available for runtime apply",
        }

    _write_text(config_path, _tuning_config_text(profile, "disable_settings"))
    _log_warning("server_tuning_config_written", profile=profile, action=action, config_path=config_path)
    commands = _sysctl_set_commands(disable_settings)
    if commands:
        job = _create_job("server_tuning_disable", profile, commands)
        return {"ok": True, "status_before": status_before, "job": job}
    return {
        "ok": True,
        "status_before": status_before,
        "warning": "disable config written, but sysctl command is not available for runtime apply",
    }


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status.value)
    request_id = getattr(handler, "request_id", None)
    if request_id:
        handler.send_header("X-Request-Id", str(request_id))
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _docker_http_status(result: dict[str, Any]) -> HTTPStatus:
    if result.get("ok"):
        return HTTPStatus.OK

    exit_code = result.get("exit_code")
    if exit_code == 404:
        return HTTPStatus.NOT_FOUND
    if exit_code == 400:
        return HTTPStatus.BAD_REQUEST
    if exit_code == 409:
        return HTTPStatus.CONFLICT

    text = " ".join(
        str(result.get(key) or "")
        for key in ("error", "stderr", "stdout")
    ).lower()
    if "no such container" in text or "container not found" in text or "not found" in text:
        return HTTPStatus.NOT_FOUND
    if "docker socket is not available" in text or "cannot connect to the docker daemon" in text:
        return HTTPStatus.SERVICE_UNAVAILABLE
    if "bad parameter" in text or "invalid" in text:
        return HTTPStatus.BAD_REQUEST
    return HTTPStatus.INTERNAL_SERVER_ERROR


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except (TypeError, ValueError):
        raise ValueError("Content-Length must be an integer") from None
    if length <= 0:
        return {}
    if length > AGENT_MAX_BODY_BYTES:
        raise RequestBodyTooLarge(f"request body too large: max {AGENT_MAX_BODY_BYTES} bytes")
    raw = handler.rfile.read(length)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object")
    return data


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    return str((handler.client_address or ("unknown",))[0] or "unknown")


def _auth_blocked_until(client_ip: str) -> float:
    now = time.time()
    with AUTH_FAILURES_LOCK:
        state = AUTH_FAILURES.get(client_ip)
        if not state:
            return 0.0
        blocked_until = float(state.get("blocked_until") or 0)
        if blocked_until <= now:
            return 0.0
        return blocked_until


def _record_auth_failure(client_ip: str) -> None:
    now = time.time()
    with AUTH_FAILURES_LOCK:
        state = AUTH_FAILURES.get(client_ip) or {"count": 0, "first_ts": now, "blocked_until": 0.0}
        if now - float(state.get("first_ts") or now) > AGENT_AUTH_FAIL_WINDOW_S:
            state = {"count": 0, "first_ts": now, "blocked_until": 0.0}
        state["count"] = int(state.get("count") or 0) + 1
        if state["count"] >= AGENT_AUTH_FAIL_LIMIT:
            state["blocked_until"] = now + AGENT_AUTH_FAIL_BLOCK_S
            _log_warning("auth_client_blocked", client=client_ip, blocked_s=AGENT_AUTH_FAIL_BLOCK_S)
        AUTH_FAILURES[client_ip] = state


def _record_auth_success(client_ip: str) -> None:
    with AUTH_FAILURES_LOCK:
        AUTH_FAILURES.pop(client_ip, None)


def _is_authorized(handler: BaseHTTPRequestHandler) -> bool:
    client_ip = _client_ip(handler)
    blocked_until = _auth_blocked_until(client_ip)
    if blocked_until:
        setattr(handler, "auth_blocked_until", blocked_until)
        return False
    if not AGENT_API_TOKEN:
        _log_warning("auth_token_empty", path=urlparse(handler.path).path)
        return AGENT_ALLOW_EMPTY_TOKEN
    auth = str(handler.headers.get("Authorization") or "").strip()
    x_token = str(handler.headers.get("X-Agent-Token") or "").strip()
    ok = hmac.compare_digest(auth, f"Bearer {AGENT_API_TOKEN}") or hmac.compare_digest(x_token, AGENT_API_TOKEN)
    if ok:
        _record_auth_success(client_ip)
    else:
        _record_auth_failure(client_ip)
    return ok


class AgentHandler(BaseHTTPRequestHandler):
=======
        "dry_run": bool(job.get("dry_run")),
        "params": job.get("params", {}),
        "result": job.get("result"),
        "log": (job.get("log") or "")[-AGENT_JOB_LOG_LIMIT:],
    }


def _run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    op = OPERATIONS[job["operation_id"]]
    env = os.environ.copy()
    env["DRY_RUN"] = "true" if job.get("dry_run") else "false"
    for key, value in (job.get("params") or {}).items():
        env[str(key).upper()] = str(value)
    result = _run_cmd(["/bin/bash", str(op.script_path)], env=env, timeout_s=op.timeout_s)
    with JOBS_LOCK:
        job2 = JOBS.get(job_id)
        if not job2:
            return
        job2["status"] = "completed" if result["ok"] else "failed"
        job2["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        job2["result"] = result
        job2["log"] = ((result.get("stdout") or "") + ("\n" + result.get("stderr") if result.get("stderr") else ""))[-AGENT_JOB_LOG_LIMIT:]


def _create_job(operation_id: str, params: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    if operation_id not in OPERATIONS:
        raise ValueError("unknown operation_id")
    if _active_jobs_count() >= AGENT_MAX_ACTIVE_JOBS:
        raise RuntimeError(f"too many active jobs: max {AGENT_MAX_ACTIVE_JOBS}")
    op = OPERATIONS[operation_id]
    if not op.script_path.exists():
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
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return _job_public(job)


def _json_response(h: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    h.send_response(status.value)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _read_json_body(h: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(h.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    if length > AGENT_MAX_BODY_BYTES:
        raise ValueError(f"request body too large: max {AGENT_MAX_BODY_BYTES} bytes")
    data = json.loads(h.rfile.read(length).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("request body must be object")
    return data


def _authorized(h: BaseHTTPRequestHandler) -> bool:
    if not AGENT_API_TOKEN:
        return AGENT_ALLOW_EMPTY_TOKEN
    auth = str(h.headers.get("Authorization") or "").strip()
    x_token = str(h.headers.get("X-Agent-Token") or "").strip()
    return hmac.compare_digest(auth, f"Bearer {AGENT_API_TOKEN}") or hmac.compare_digest(x_token, AGENT_API_TOKEN)


def _require_auth(h: BaseHTTPRequestHandler) -> bool:
    if _authorized(h):
        return True
    _json_response(h, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
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
    if path == "/v1/security/harden-ssh":
        return {"DISABLE_PASSWORD_AUTH": str(bool(payload.get("disable_password_auth") if "disable_password_auth" in payload else True)).lower()}
    if path == "/v1/security/ssh-port":
        return {
            "ACTION": str(payload.get("action") or "set"),
            "PORT": str(payload.get("port") or ""),
        }
    if path == "/v1/network/tuning":
        params: dict[str, Any] = {}
        if "bbr" in payload:
            params["ENABLE_BBR"] = str(bool(payload["bbr"])).lower()
        if "cake" in payload:
            params["ENABLE_CAKE"] = str(bool(payload["cake"])).lower()
        return params
    if path == "/v1/services/update":
        params = {"MODE": str(payload.get("mode") or "pull")}
        dirs = payload.get("dirs")
        if isinstance(dirs, list):
            params["DIRS"] = ",".join(str(x).strip() for x in dirs if str(x).strip())
        return params
    if path == "/v1/remnawave/node/install":
        return {
            "DOMAIN": str(payload.get("domain") or ""),
            "NODE_PORT": str(payload.get("node_port") or 2222),
            "NODE_SECRET_KEY": str(payload.get("node_secret_key") or "replace_with_node_secret_key"),
        }
    if path == "/v1/ufw/action":
        params = {"UFW_ACTION": str(payload.get("action") or "enable")}
        if payload.get("rule_action") is not None:
            params["UFW_RULE_ACTION"] = str(payload.get("rule_action") or "")
        if payload.get("rule") is not None:
            params["UFW_RULE"] = str(payload.get("rule") or "")
        return params
    if path in {"/v1/fail2ban/action", "/v1/fail2ban/config"}:
        params = {
            "F2B_ACTION": str(payload.get("action") or ("config" if path.endswith("/config") else "restart"))
        }
        if payload.get("bantime") is not None:
            params["F2B_BANTIME"] = str(payload["bantime"])
        if payload.get("findtime") is not None:
            params["F2B_FINDTIME"] = str(payload["findtime"])
        if payload.get("maxretry") is not None:
            params["F2B_MAXRETRY"] = str(payload["maxretry"])
        return params
    return _to_params(payload, {"dry_run", "confirm"})


class Handler(BaseHTTPRequestHandler):
>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)
    server_version = f"InfraControlAgent/{AGENT_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        if AGENT_ACCESS_LOG:
<<<<<<< HEAD
            _log_info("http_server", client=self.client_address[0], message=fmt % args)

    def _request_id(self) -> str:
        request_id = getattr(self, "request_id", "")
        if request_id:
            return str(request_id)
        request_id = uuid.uuid4().hex[:12]
        self.request_id = request_id
        return request_id

    def _require_auth(self) -> bool:
        if _is_authorized(self):
            return True
        blocked_until = float(getattr(self, "auth_blocked_until", 0.0) or 0.0)
        if blocked_until > time.time():
            retry_after = max(1, int(blocked_until - time.time()))
            _log_warning(
                "auth_rate_limited",
                request_id=self._request_id(),
                client=self.client_address[0],
                path=urlparse(self.path).path,
                retry_after_s=retry_after,
            )
            _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"ok": False, "error": "too many auth failures", "retry_after_s": retry_after})
            return False
        _log_warning("auth_failed", request_id=self._request_id(), client=self.client_address[0], path=urlparse(self.path).path)
        _json_response(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
        return False

    def do_GET(self) -> None:
        started = time.time()
        request_id = self._request_id()
        path = urlparse(self.path).path.rstrip("/") or "/"
        _log_debug("request_started", request_id=request_id, method="GET", path=path, client=self.client_address[0])
        try:
            self._handle_get(path)
        finally:
            if AGENT_ACCESS_LOG:
                _log_info(
                    "request_finished",
                    request_id=request_id,
                    method="GET",
                    path=path,
                    client=self.client_address[0],
                    duration_ms=int((time.time() - started) * 1000),
                )

    def _handle_get(self, path: str) -> None:
        if path == "/health":
            docker_ok = _docker_available()
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "ok": docker_ok,
                    "status": "ok" if docker_ok else "degraded",
                    "agent_id": AGENT_ID,
                    "version": AGENT_VERSION,
                    "hostname": platform.node(),
                    "uptime_s": _host_metrics()["uptime_s"],
                    "docker_available": docker_ok,
                },
            )
            return

        if not self._require_auth():
            return

        if path == "/v1/node/summary":
            summary = _node_summary()
            _json_response(self, HTTPStatus.OK if summary["ok"] else HTTPStatus.OK, summary)
            return

        if path == "/v1/agent/info":
            _json_response(self, HTTPStatus.OK, _agent_info())
            return

        if path == "/v1/diagnostics/host":
            _json_response(self, HTTPStatus.OK, _host_diagnostics())
            return

        if path == "/v1/docker/containers":
            if not _docker_available():
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            result = _docker_containers()
            if result.get("ok") and not DOCKER_BIN:
                result["resources_note"] = "Use GET /v1/docker/containers/{container} for live resource stats."
            _json_response(self, _docker_http_status(result), result)
            return

        if path.startswith("/v1/docker/containers/"):
            if not _docker_available():
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            container = path.rsplit("/", 1)[-1]
            if not container:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "container is required"})
                return
            query = parse_qs(urlparse(self.path).query)
            include_raw = str((query.get("raw") or ["false"])[0]).strip().lower() in ("1", "true", "yes", "on")
            _log_info("docker_container_detail_requested", request_id=self._request_id(), container=container, raw=include_raw)
            result = _docker_container_detail(container, include_raw=include_raw)
            _json_response(self, _docker_http_status(result), result)
            return

        if path == "/v1/docker/ps":
            if not _docker_available():
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            result = _docker_ps()
            _json_response(self, _docker_http_status(result), result)
            return

        if path == "/v1/docker/usage":
            if not _docker_available():
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            result = _docker_usage()
            _json_response(self, _docker_http_status(result), result)
            return

        if path == "/v1/remnawave/profiles":
            _log_info("remnawave_profiles_requested", request_id=self._request_id())
            _json_response(self, HTTPStatus.OK, _remnawave_profiles())
            return

        if path == "/v1/ufw/status":
            _json_response(self, HTTPStatus.OK, _ufw_status())
            return

        if path == "/v1/fail2ban/status":
            query = parse_qs(urlparse(self.path).query)
            jail = str((query.get("jail") or [""])[0]).strip() or None
            _json_response(self, HTTPStatus.OK, _fail2ban_status(jail))
            return

        if path == "/v1/fail2ban/config":
            _json_response(self, HTTPStatus.OK, _fail2ban_config())
            return

        if path == "/v1/server/tuning":
            query = parse_qs(urlparse(self.path).query)
            profile = str((query.get("profile") or ["bbr_fq"])[0]).strip() or "bbr_fq"
            try:
                status = _tuning_status(profile)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            _json_response(self, HTTPStatus.OK, status)
            return

        if path == "/v1/actions":
            _prune_jobs()
            with JOBS_LOCK:
                jobs = [_job_public(job) for job in JOBS.values()]
            jobs.sort(key=lambda item: item["created_at"], reverse=True)
            _json_response(self, HTTPStatus.OK, {"ok": True, "jobs": jobs[:50]})
            return

        if path.startswith("/v1/actions/"):
            job_id = path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                payload = _job_public(job) if job else None
            if not payload:
                _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "job not found"})
                return
            _json_response(self, HTTPStatus.OK, {"ok": True, "job": payload})
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_DELETE(self) -> None:
        started = time.time()
        request_id = self._request_id()
        path = urlparse(self.path).path.rstrip("/") or "/"
        _log_debug("request_started", request_id=request_id, method="DELETE", path=path, client=self.client_address[0])
        try:
            if not self._require_auth():
                return
            if path.startswith("/v1/actions/"):
                job_id = path.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    if job and job.get("status") in ("queued", "running"):
                        _json_response(self, HTTPStatus.CONFLICT, {"ok": False, "error": "cannot delete a running job"})
                        return
                    removed = JOBS.pop(job_id, None)
                if not removed:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "job not found"})
                    return
                _json_response(self, HTTPStatus.OK, {"ok": True, "removed": job_id})
                return
            _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
        finally:
            if AGENT_ACCESS_LOG:
                _log_info(
                    "request_finished",
                    request_id=request_id,
                    method="DELETE",
                    path=path,
                    client=self.client_address[0],
                    duration_ms=int((time.time() - started) * 1000),
                )

    def do_POST(self) -> None:
        started = time.time()
        request_id = self._request_id()
        path = urlparse(self.path).path.rstrip("/") or "/"
        _log_debug("request_started", request_id=request_id, method="POST", path=path, client=self.client_address[0])
        try:
            self._handle_post(path)
        finally:
            if AGENT_ACCESS_LOG:
                _log_info(
                    "request_finished",
                    request_id=request_id,
                    method="POST",
                    path=path,
                    client=self.client_address[0],
                    duration_ms=int((time.time() - started) * 1000),
                )

    def _create_job_or_respond(self, action: str, target: str, commands: list[dict[str, Any]]) -> dict[str, Any] | None:
        try:
            return _create_job(action, target, commands)
        except JobRejected as exc:
            _log_warning("job_rejected", request_id=self._request_id(), action=action, target=target, error=exc)
            _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"ok": False, "error": str(exc)})
            return None

    def _handle_post(self, path: str) -> None:
        if not self._require_auth():
            return

        try:
            payload = _read_json_body(self)
        except RequestBodyTooLarge as exc:
            _log_warning("request_body_too_large", request_id=self._request_id(), path=path, error=exc)
            _json_response(self, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            _log_warning("request_bad_json", request_id=self._request_id(), path=path, error=exc)
            _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        if path == "/v1/docker/logs/tail":
            if not _docker_available():
                _log_warning("docker_unavailable", request_id=self._request_id(), action="logs_tail")
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            try:
                container = _validate_docker_container_ref(payload.get("container"))
            except Exception as exc:
                _log_warning("docker_logs_invalid_container", request_id=self._request_id(), error=exc)
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            try:
                tail = max(10, min(5000, int(payload.get("tail") or 200)))
            except (TypeError, ValueError):
                _log_warning("docker_logs_invalid_tail", request_id=self._request_id(), tail=payload.get("tail"))
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "tail must be a number"})
                return
            _log_info("docker_logs_tail_requested", request_id=self._request_id(), container=container, tail=tail)
            result = _docker_logs_tail(container, tail)
            _json_response(self, _docker_http_status(result), result)
            return

        if path == "/v1/docker/container/action":
            if not _docker_available():
                _log_warning("docker_unavailable", request_id=self._request_id(), action="container_action")
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            try:
                container = _validate_docker_container_ref(payload.get("container"))
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            action = str(payload.get("action") or "").strip().lower()
            _log_warning("docker_container_action_requested", request_id=self._request_id(), container=container, action=action)
            try:
                result = _docker_container_action(container, action)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            _json_response(self, _docker_http_status(result), result)
            return

        if path == "/v1/docker/prune":
            target = str(payload.get("target") or "images").strip()
            include_volumes = bool(payload.get("volumes") or False)
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            confirm = str(payload.get("confirm") or "").strip().lower()
            _log_warning("docker_prune_requested", request_id=self._request_id(), target=target, volumes=include_volumes, dry_run=dry_run)
            try:
                commands = _docker_prune_plan(target, include_volumes)
            except Exception as exc:
                _log_warning("docker_prune_rejected", request_id=self._request_id(), target=target, error=exc)
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            if dry_run:
                df = _docker_system_df()
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "dry_run": True,
                        "target": target,
                        "volumes": include_volumes,
                        "commands": [command["title"] for command in commands],
                        "docker_system_df": df,
                    },
                )
                return
            expected_confirm = "docker_prune_volumes" if include_volumes else "docker_prune"
            if confirm != expected_confirm:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"confirm must be {expected_confirm}"})
                return
            job = self._create_job_or_respond("docker_prune", target, commands)
            if not job:
                return
            _log_warning("docker_prune_job_created", request_id=self._request_id(), target=target, job_id=job["id"])
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        if path == "/v1/server/reboot":
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            confirm = str(payload.get("confirm") or "").strip().lower()
            _log_warning("server_reboot_requested", request_id=self._request_id(), dry_run=dry_run)
            commands = _reboot_plan()
            if dry_run:
                _json_response(self, HTTPStatus.OK, {"ok": True, "dry_run": True, "commands": [command["title"] for command in commands]})
                return
            if confirm != "reboot":
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "confirm must be reboot"})
                return
            job = self._create_job_or_respond("server_reboot", "host", commands)
            if not job:
                return
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        if path == "/v1/ufw/action":
            action = str(payload.get("action") or "").strip().lower()
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            confirm = str(payload.get("confirm") or "").strip().lower()
            _log_warning("ufw_action_requested", request_id=self._request_id(), action=action, dry_run=dry_run)
            try:
                commands = _ufw_action_plan(action)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            if dry_run:
                _json_response(self, HTTPStatus.OK, {"ok": True, "dry_run": True, "action": action, "commands": [command["title"] for command in commands]})
                return
            if action in ("disable", "stop") and confirm != f"ufw_{action}":
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"confirm must be ufw_{action}"})
                return
            job = self._create_job_or_respond("ufw_action", action, commands)
            if not job:
                return
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        if path == "/v1/ufw/rule":
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            try:
                target, commands = _ufw_rule_plan(payload)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            _log_warning("ufw_rule_requested", request_id=self._request_id(), target=target, dry_run=dry_run)
            if dry_run:
                _json_response(self, HTTPStatus.OK, {"ok": True, "dry_run": True, "target": target, "commands": [command["title"] for command in commands]})
                return
            job = self._create_job_or_respond("ufw_rule", target, commands)
            if not job:
                return
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        if path == "/v1/fail2ban/action":
            action = str(payload.get("action") or "").strip().lower()
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            confirm = str(payload.get("confirm") or "").strip().lower()
            _log_warning("fail2ban_action_requested", request_id=self._request_id(), action=action, dry_run=dry_run)
            try:
                commands = _fail2ban_action_plan(action)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            if dry_run:
                _json_response(self, HTTPStatus.OK, {"ok": True, "dry_run": True, "action": action, "commands": [command["title"] for command in commands]})
                return
            if action in ("stop", "disable") and confirm != f"fail2ban_{action}":
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"confirm must be fail2ban_{action}"})
                return
            job = self._create_job_or_respond("fail2ban_action", action, commands)
            if not job:
                return
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        if path == "/v1/fail2ban/config":
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            confirm = str(payload.get("confirm") or "").strip().lower()
            current = _fail2ban_config()["config"]
            try:
                config = _validate_fail2ban_config(payload, base=current)
                commands = _fail2ban_config_plan(config)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            _log_warning("fail2ban_config_requested", request_id=self._request_id(), dry_run=dry_run)
            if dry_run:
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "dry_run": True,
                        "path": FAIL2BAN_CONFIG_PATH,
                        "config": config,
                        "content": _fail2ban_config_text(config),
                        "commands": [command["title"] for command in commands],
                    },
                )
                return
            if confirm != "fail2ban_config":
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "confirm must be fail2ban_config"})
                return
            job = self._create_job_or_respond("fail2ban_config", FAIL2BAN_CONFIG_PATH, commands)
            if not job:
                return
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job, "config": config})
            return

        if path == "/v1/fail2ban/jail":
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            try:
                target, commands = _fail2ban_jail_action(payload)
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            _log_warning("fail2ban_jail_action_requested", request_id=self._request_id(), target=target, dry_run=dry_run)
            if dry_run:
                _json_response(self, HTTPStatus.OK, {"ok": True, "dry_run": True, "target": target, "commands": [command["title"] for command in commands]})
                return
            job = self._create_job_or_respond("fail2ban_jail_action", target, commands)
            if not job:
                return
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        if path == "/v1/actions/prune":
            max_age_s = int(payload.get("max_age_s")) if payload.get("max_age_s") is not None else None
            max_count = int(payload.get("max_count")) if payload.get("max_count") is not None else None
            _json_response(self, HTTPStatus.OK, _prune_jobs(max_age_s=max_age_s, max_count=max_count))
            return

        if path == "/v1/remnawave/upgrade":
            profile = str(payload.get("profile") or "").strip()
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            confirm = str(payload.get("confirm") or "").strip().lower()
            _log_warning("remnawave_upgrade_requested", request_id=self._request_id(), profile=profile, dry_run=dry_run)
            try:
                workdir, commands = _upgrade_plan(profile)
            except PermissionError as exc:
                _log_warning("remnawave_upgrade_forbidden", request_id=self._request_id(), profile=profile, error=exc)
                _json_response(self, HTTPStatus.FORBIDDEN, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                _log_warning("remnawave_upgrade_rejected", request_id=self._request_id(), profile=profile, error=exc)
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            if dry_run:
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "dry_run": True,
                        "profile": profile,
                        "workdir": workdir,
                        "commands": [command["title"] for command in commands],
                    },
                )
                return
            if confirm != "remnawave_upgrade":
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "confirm must be remnawave_upgrade"})
                return
            job = self._create_job_or_respond("remnawave_upgrade", profile, commands)
            if not job:
                return
            _log_warning("remnawave_upgrade_job_created", request_id=self._request_id(), profile=profile, job_id=job["id"])
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        if path == "/v1/server/tuning":
            profile = str(payload.get("profile") or "bbr_fq").strip()
            action = str(payload.get("action") or "").strip()
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            confirm = str(payload.get("confirm") or "").strip().lower()
            _log_warning("server_tuning_requested", request_id=self._request_id(), profile=profile, action=action, dry_run=dry_run)
            if not dry_run and confirm != "server_tuning":
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "confirm must be server_tuning"})
                return
            try:
                result = _tuning_apply(profile, action, dry_run=dry_run)
            except JobRejected as exc:
                _log_warning("server_tuning_job_rejected", request_id=self._request_id(), profile=profile, action=action, error=exc)
                _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                _log_warning("server_tuning_rejected", request_id=self._request_id(), profile=profile, action=action, error=exc)
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            status = HTTPStatus.ACCEPTED if result.get("job") else HTTPStatus.OK
            if result.get("job"):
                _log_warning("server_tuning_job_created", request_id=self._request_id(), profile=profile, action=action, job_id=result["job"]["id"])
            _json_response(self, status, result)
=======
            _log(logging.INFO, "http", client=self.client_address[0], msg=(fmt % args))

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
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
                _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "job not found"})
                return
            _json_response(self, HTTPStatus.OK, {"ok": True, "job": _job_public(j)})
            return
        if path == "/v1/security/status":
            op = OPERATIONS["security.status"]
            env = os.environ.copy()
            env["DRY_RUN"] = "false"
            result = _run_cmd(["/bin/bash", str(op.script_path)], env=env, timeout_s=op.timeout_s)
            _json_response(self, HTTPStatus.OK if result["ok"] else HTTPStatus.SERVICE_UNAVAILABLE, {"ok": result["ok"], "result": result})
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if not _require_auth(self):
            return
        if path.startswith("/v1/actions/"):
            job_id = path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                j = JOBS.get(job_id)
                if j and j.get("status") in {"queued", "running"}:
                    _json_response(self, HTTPStatus.CONFLICT, {"ok": False, "error": "cannot delete active job"})
                    return
                removed = JOBS.pop(job_id, None)
            if not removed:
                _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "job not found"})
                return
            _json_response(self, HTTPStatus.OK, {"ok": True, "removed": job_id})
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if not _require_auth(self):
            return
        try:
            payload = _read_json_body(self)
        except Exception as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        if path == "/v1/actions/prune":
            _json_response(self, HTTPStatus.OK, _prune_jobs(payload.get("max_age_s"), payload.get("max_count")))
            return

        if path == "/v1/actions/run":
            operation_id = str(payload.get("operation_id") or "").strip()
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            op = OPERATIONS.get(operation_id)
            if not op:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "unknown operation_id"})
                return
            if not dry_run and op.confirm:
                confirm = str(payload.get("confirm") or "").strip().lower()
                if confirm != op.confirm:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"confirm must be {op.confirm}"})
                    return
            try:
                job = _create_job(operation_id, params, dry_run=dry_run)
            except RuntimeError as exc:
                _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
            return

        alias: dict[str, str] = {
            "/v1/system/update": "system.update",
            "/v1/security/harden-ssh": "security.harden_ssh",
            "/v1/security/ssh-port": "security.ssh_port",
            "/v1/security/rollback": "security.rollback",
            "/v1/network/tuning": "network.bbr_cake",
            "/v1/services/update": "services.update",
            "/v1/remnawave/node/install": "remnawave.node_install",
            "/v1/ufw/action": "security.ufw",
            "/v1/fail2ban/action": "security.fail2ban",
            "/v1/fail2ban/config": "security.fail2ban",
        }
        if path in alias:
            op_id = alias[path]
            op = OPERATIONS[op_id]
            dry_run = bool(payload.get("dry_run") if "dry_run" in payload else False)
            if not dry_run and op.confirm:
                confirm = str(payload.get("confirm") or "").strip().lower()
                if confirm != op.confirm:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"confirm must be {op.confirm}"})
                    return
            params = _alias_params(path, payload)
            try:
                job = _create_job(op_id, params, dry_run=dry_run)
            except RuntimeError as exc:
                _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            _json_response(self, HTTPStatus.ACCEPTED, {"ok": True, "job": job})
>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})


def main() -> None:
    _setup_logging()
    if not AGENT_API_TOKEN and not AGENT_ALLOW_EMPTY_TOKEN:
<<<<<<< HEAD
        _log_error(
            "agent_token_required",
            message="AGENT_API_TOKEN is required; set AGENT_ALLOW_EMPTY_TOKEN=true only for local development",
        )
        raise SystemExit(2)
    _log_security_posture()
    server = ThreadingHTTPServer((AGENT_HTTP_HOST, AGENT_HTTP_PORT), AgentHandler)
    _log_info(
        "agent_started",
        host=AGENT_HTTP_HOST,
        port=AGENT_HTTP_PORT,
        agent_id=AGENT_ID,
        version=AGENT_VERSION,
        log_level=AGENT_LOG_LEVEL,
        access_log=AGENT_ACCESS_LOG,
    )
    if not AGENT_API_TOKEN:
        _log_warning("agent_token_empty", message="protected endpoints are open because AGENT_ALLOW_EMPTY_TOKEN=true")
    server.serve_forever()
=======
        raise SystemExit("AGENT_API_TOKEN is required")
    for op in OPERATIONS.values():
        if not op.script_path.exists():
            raise SystemExit(f"missing operation script: {op.script_relpath}")
    _log(logging.INFO, "agent_started", id=AGENT_ID, version=AGENT_VERSION, host=AGENT_HTTP_HOST, port=AGENT_HTTP_PORT)
    ThreadingHTTPServer((AGENT_HTTP_HOST, AGENT_HTTP_PORT), Handler).serve_forever()
>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)


if __name__ == "__main__":
    main()
