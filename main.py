from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
from typing import Any
from urllib.parse import urlparse


AGENT_ID = str(os.getenv("AGENT_ID") or platform.node() or "infra-control-agent").strip()
AGENT_API_TOKEN = str(os.getenv("AGENT_API_TOKEN") or "").strip()
AGENT_HTTP_HOST = str(os.getenv("AGENT_HTTP_HOST") or "0.0.0.0").strip()
AGENT_HTTP_PORT = int(os.getenv("AGENT_HTTP_PORT") or "8091")
DOCKER_BIN = str(
    os.getenv("AGENT_DOCKER_BIN")
    or shutil.which("docker")
    or ("/usr/bin/docker" if os.path.exists("/usr/bin/docker") else "")
).strip()
DOCKER_SOCKET = str(os.getenv("AGENT_DOCKER_SOCKET") or "/var/run/docker.sock").strip()


def _run_cmd(cmd: list[str], *, timeout_s: int = 120) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "duration_ms": int((time.time() - started) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "command timed out",
            "duration_ms": int((time.time() - started) * 1000),
        }


class UnixHTTPConnection(HTTPConnection):
    def __init__(self, socket_path: str, *, timeout: int = 120) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _docker_available() -> bool:
    return bool(DOCKER_BIN) or os.path.exists(DOCKER_SOCKET)


def _docker_api_request(
    method: str,
    path: str,
    *,
    timeout_s: int = 120,
    body: bytes | None = None,
    docker_log_stream: bool = False,
) -> dict[str, Any]:
    started = time.time()
    if not os.path.exists(DOCKER_SOCKET):
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
        return {
            "ok": ok,
            "exit_code": 0 if ok else response.status,
            "stdout": text[-12000:] if ok else "",
            "stderr": "" if ok else text[-12000:],
            "duration_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": int((time.time() - started) * 1000),
        }
    finally:
        conn.close()


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
    if DOCKER_BIN:
        return _run_cmd([DOCKER_BIN, "logs", "--tail", str(tail), container], timeout_s=60)

    path = f"/containers/{container}/logs?stdout=1&stderr=1&tail={tail}"
    return _docker_api_request("GET", path, timeout_s=60, docker_log_stream=True)


def _docker_restart(container: str) -> dict[str, Any]:
    if DOCKER_BIN:
        return _run_cmd([DOCKER_BIN, "restart", container], timeout_s=60)

    result = _docker_api_request("POST", f"/containers/{container}/restart", timeout_s=60)
    if result["ok"]:
        result["stdout"] = container
    return result


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status.value)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object")
    return data


def _is_authorized(handler: BaseHTTPRequestHandler) -> bool:
    if not AGENT_API_TOKEN:
        return True
    auth = str(handler.headers.get("Authorization") or "").strip()
    x_token = str(handler.headers.get("X-Agent-Token") or "").strip()
    return auth == f"Bearer {AGENT_API_TOKEN}" or x_token == AGENT_API_TOKEN


class AgentHandler(BaseHTTPRequestHandler):
    server_version = "InfraControlAgent/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[http] {self.address_string()} - {fmt % args}")

    def _require_auth(self) -> bool:
        if _is_authorized(self):
            return True
        _json_response(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
        return False

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/health":
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "agent_id": AGENT_ID,
                    "hostname": platform.node(),
                    "docker_available": _docker_available(),
                },
            )
            return

        if not self._require_auth():
            return

        if path == "/v1/diagnostics/host":
            result = _run_cmd(["sh", "-lc", "uptime && df -h && free -m || true"], timeout_s=30)
            _json_response(self, HTTPStatus.OK if result["ok"] else HTTPStatus.INTERNAL_SERVER_ERROR, result)
            return

        if path == "/v1/docker/ps":
            if not _docker_available():
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            result = _docker_ps()
            _json_response(self, HTTPStatus.OK if result["ok"] else HTTPStatus.INTERNAL_SERVER_ERROR, result)
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if not self._require_auth():
            return

        try:
            payload = _read_json_body(self)
        except Exception as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        if path == "/v1/docker/logs/tail":
            if not _docker_available():
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            container = str(payload.get("container") or "").strip()
            tail = max(10, min(5000, int(payload.get("tail") or 200)))
            if not container:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "container is required"})
                return
            result = _docker_logs_tail(container, tail)
            _json_response(self, HTTPStatus.OK if result["ok"] else HTTPStatus.INTERNAL_SERVER_ERROR, result)
            return

        if path == "/v1/docker/restart":
            if not _docker_available():
                _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "docker is not available"})
                return
            container = str(payload.get("container") or "").strip()
            if not container:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "container is required"})
                return
            result = _docker_restart(container)
            _json_response(self, HTTPStatus.OK if result["ok"] else HTTPStatus.INTERNAL_SERVER_ERROR, result)
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer((AGENT_HTTP_HOST, AGENT_HTTP_PORT), AgentHandler)
    print(f"[agent] listening on {AGENT_HTTP_HOST}:{AGENT_HTTP_PORT}, agent_id={AGENT_ID}")
    if not AGENT_API_TOKEN:
        print("[agent] AGENT_API_TOKEN is empty; protected endpoints are open")
    server.serve_forever()


if __name__ == "__main__":
    main()
