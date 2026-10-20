"""First-boot local AI: install Ollama and the recommended models.

The installer leaves a request file when the owner ticks "Set up local AI";
apvis-ai-setup.service (root, in the background) then waits for the network,
runs Ollama's official installer, and downloads the models through Ollama's
own API. Progress goes to a world-readable status file that Home shows in
Active Task. A failure is reported as such and retried at the next start;
the request is only removed once every model is really installed.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

STATE = Path("/var/lib/apvis-os")
REQUEST = STATE / "ai-setup.request"
STATUS = STATE / "ai-setup.json"
INSTALL_SCRIPT_URL = "https://ollama.com/install.sh"
OLLAMA = Path("/usr/local/bin/ollama")
API = "http://127.0.0.1:11434"
MODELS = ("llama3.2:1b", "qwen2.5-coder:1.5b", "qwen2.5:0.5b")


def write_status(**fields: Any) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    data = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **fields}
    tmp = STATUS.with_name(STATUS.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATUS)


def read_status(path: Path = STATUS) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def online(host: str = "ollama.com", port: int = 443, timeout: float = 5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for(check: Callable[[], bool], seconds: float, step: float = 3) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(step)
    return check()


def api_up() -> bool:
    try:
        with urllib.request.urlopen(API + "/api/version", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def installed_models() -> list[str]:
    with urllib.request.urlopen(API + "/api/tags", timeout=10) as r:
        return [m.get("name", "") for m in json.loads(r.read().decode("utf-8")).get("models", [])]


def pull(model: str, on_progress: Callable[[int], None]) -> None:
    body = json.dumps({"model": model, "stream": True}).encode("utf-8")
    request = urllib.request.Request(API + "/api/pull", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as r:
        for raw in r:
            line = json.loads(raw.decode("utf-8") or "{}")
            if line.get("error"):
                raise RuntimeError(line["error"])
            if line.get("total"):
                on_progress(int(100 * (line.get("completed") or 0) / line["total"]))
            if line.get("status") == "success":
                on_progress(100)


def run() -> int:
    if not REQUEST.exists():
        return 0
    steps = ["Waiting for the internet", "Installing Ollama", *("Downloading " + m for m in MODELS)]
    write_status(state="running", step=0, steps=steps, pct=0, message="Waiting for an internet connection…")
    if not wait_for(online, 600, 10):
        write_status(state="waiting", step=0, steps=steps, pct=0,
                     message="No internet yet. Local AI will be set up the next time APVIS starts online.")
        return 1
    try:
        if not OLLAMA.is_file():
            write_status(state="running", step=1, steps=steps, pct=0, message="Installing Ollama (official installer)…")
            with tempfile.TemporaryDirectory() as tmp:
                script = Path(tmp) / "install.sh"
                with urllib.request.urlopen(INSTALL_SCRIPT_URL, timeout=60) as r:
                    script.write_bytes(r.read())
                done = subprocess.run(["sh", str(script)], capture_output=True, text=True, timeout=1800)
                if done.returncode != 0 or not OLLAMA.is_file():
                    tail = (done.stderr or done.stdout).strip().splitlines()
                    raise RuntimeError("the Ollama installer failed: " + (tail[-1] if tail else "no reason given"))
        subprocess.run(["systemctl", "enable", "--now", "ollama.service"], capture_output=True, timeout=60)
        if not wait_for(api_up, 120):
            raise RuntimeError("Ollama did not start")
        have = installed_models()
        for i, model in enumerate(MODELS):
            step = 2 + i
            if any(n == model or n.startswith(model + ":") for n in have):
                continue
            write_status(state="running", step=step, steps=steps, pct=0, message=f"Downloading {model}…")
            pull(model, lambda pct, step=step, model=model: write_status(state="running", step=step, steps=steps, pct=pct,
                                                                           message=f"Downloading {model}… {pct}%"))
        missing = [m for m in MODELS if not any(n == m or n.startswith(m + ":") for n in installed_models())]
        if missing:
            raise RuntimeError("not installed after download: " + ", ".join(missing))
    except Exception as exc:   # network, installer, API: reported, retried next start
        write_status(state="failed", steps=steps, pct=0, message=f"Local AI setup didn't finish: {exc}. It will try again next start.")
        return 1
    REQUEST.unlink(missing_ok=True)
    write_status(state="done", step=len(steps), steps=steps, pct=100, message="Local AI is ready: " + ", ".join(MODELS))
    return 0


if __name__ == "__main__":
    sys.exit(run())
