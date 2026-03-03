from __future__ import annotations

import json
import os
import platform
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


CONTROL_API_URL = str(os.getenv("CONTROL_API_URL") or "http://localhost:8090").rstrip("/")
AGENT_ID = str(os.getenv("AGENT_ID") or "").strip().lower() or secrets.token_hex(8)
AGENT_NODE_UUID = str(os.getenv("AGENT_NODE_UUID") or "").strip().lower()
AGENT_DISPLAY_NAME = str(os.getenv("AGENT_DISPLAY_NAME") or platform.node()).strip() or AGENT_ID
ENROLL_TOKEN = str(os.getenv("AGENT_ENROLL_TOKEN") or "").strip()
ACCESS_TOKEN = str(os.getenv("AGENT_ACCESS_TOKEN") or "").strip()
POLL_INTERVAL_S = max(2, int(os.getenv("AGENT_POLL_INTERVAL_S") or "8"))
HEARTBEAT_INTERVAL_S = max(5, int(os.getenv("AGENT_HEARTBEAT_INTERVAL_S") or "20"))
STATE_PATH = Path(str(os.getenv("AGENT_STATE_PATH") or "/agent/data/state.json"))
VERIFY_TLS = str(os.getenv("AGENT_VERIFY_TLS") or "true").strip().lower() in {"1", "true", "yes", "on"}


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _gen_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _request(method: str, path: str, *, token: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{CONTROL_API_URL}{path}"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    resp = requests.request(
        method,
        url,
        data=body if method.upper() in {"POST", "PUT", "PATCH"} else None,
        headers=headers,
        timeout=30,
        verify=VERIFY_TLS,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _register_if_needed(state: dict[str, Any]) -> dict[str, Any]:
    current_token = str(state.get("access_token") or ACCESS_TOKEN).strip()
    if current_token:
        return state
    enroll_token = str(state.get("enroll_token") or ENROLL_TOKEN).strip()
    if not enroll_token:
        raise RuntimeError("Agent has no AGENT_ENROLL_TOKEN and no saved access token")
    private_pem, public_pem = _gen_keypair()
    data = _request(
        "POST",
        "/control/v1/agents/register",
        payload={
            "enroll_token": enroll_token,
            "agent_id": AGENT_ID,
            "node_uuid": AGENT_NODE_UUID,
            "display_name": AGENT_DISPLAY_NAME,
            "public_key_pem": public_pem,
            "capabilities": {
                "docker": True,
                "host_diagnostics": True,
                "commands_allowlist": True,
            },
        },
    )
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Control API register returned empty access_token")
    state.update(
        {
            "agent_id": AGENT_ID,
            "node_uuid": AGENT_NODE_UUID,
            "display_name": AGENT_DISPLAY_NAME,
            "private_key_pem": private_pem,
            "public_key_pem": public_pem,
            "access_token": token,
            "registered_at": time.time(),
        }
    )
    _save_state(state)
    return state


def _run_cmd(cmd: list[str], *, timeout_s: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout[-4000:], proc.stderr[-4000:]


def _exec_action(action: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    act = str(action or "").strip().lower()
    if act == "diagnostics.host":
        code, out, err = _run_cmd(["sh", "-lc", "uptime && df -h && free -m || true"], timeout_s=30)
        status = "done" if code == 0 else "failed"
        return status, {"stdout": out, "stderr": err}, ""

    if act == "docker.ps":
        code, out, err = _run_cmd(["docker", "ps", "--format", "{{.ID}} {{.Names}} {{.Status}}"], timeout_s=30)
        status = "done" if code == 0 else "failed"
        return status, {"stdout": out, "stderr": err}, ""

    if act == "docker.logs.tail":
        container = str(payload.get("container") or "").strip()
        tail = max(10, min(5000, int(payload.get("tail") or 200)))
        if not container:
            return "failed", {}, "container is required"
        code, out, err = _run_cmd(["docker", "logs", "--tail", str(tail), container], timeout_s=60)
        status = "done" if code == 0 else "failed"
        return status, {"stdout": out, "stderr": err}, ""

    if act == "docker.restart":
        container = str(payload.get("container") or "").strip()
        if not container:
            return "failed", {}, "container is required"
        code, out, err = _run_cmd(["docker", "restart", container], timeout_s=60)
        status = "done" if code == 0 else "failed"
        return status, {"stdout": out, "stderr": err}, ""

    return "skipped", {}, f"unsupported action: {act}"


def main() -> None:
    state = _load_state()
    if "enroll_token" not in state and ENROLL_TOKEN:
        state["enroll_token"] = ENROLL_TOKEN
    state = _register_if_needed(state)
    token = str(state.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("access_token is missing after registration")

    last_hb = 0.0
    while True:
        now = time.time()
        if now - last_hb >= HEARTBEAT_INTERVAL_S:
            try:
                _request(
                    "POST",
                    "/control/v1/agents/heartbeat",
                    token=token,
                    payload={"status": "active"},
                )
                last_hb = now
            except Exception as exc:
                print(f"[agent] heartbeat failed: {exc}")

        try:
            data = _request("GET", "/control/v1/agents/poll?limit=3", token=token)
            runs = data.get("runs") if isinstance(data.get("runs"), list) else []
            for run in runs:
                run_id = str(run.get("run_id") or "").strip()
                action = str(run.get("action") or "").strip()
                payload = run.get("payload") if isinstance(run.get("payload"), dict) else {}
                if not run_id:
                    continue
                status, result, error = _exec_action(action, payload)
                try:
                    _request(
                        "POST",
                        f"/control/v1/agents/runs/{run_id}/result",
                        token=token,
                        payload={"status": status, "result": result, "error": error},
                    )
                except Exception as exc:
                    print(f"[agent] failed to submit result run={run_id}: {exc}")
        except Exception as exc:
            print(f"[agent] poll failed: {exc}")

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()

