"""Developer Mode (V2-19): the real internals, each with its source and time.

Nothing here is summarised or smoothed for show: renderer frame times come
from the frame log, service states from systemd or the process table, the AI
route from the Ask host check, and logs are the files themselves (tails).
Off by default; the owner turns it on in Settings.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

SYSTEM_UNITS = (("ssh.service", "Remote access (sshd)"), ("NetworkManager.service", "Network"),
                ("greetd.service", "Login / session"), ("polkit.service", "Permissions (polkit)"))
USER_PROCESSES = (("labwc", "Window manager"), ("mako", "Notifications"), ("swayidle", "Screen / sleep timers"),
                  ("pipewire", "Sound server"), ("wireplumber", "Sound policy"))
FRAME_LINE = re.compile(r"^(\d\d:\d\d:\d\d) tier=(\w+) fps=([\d.]+) p95=([\d.]+)ms")


def flag_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".config/apvis/developer-mode"


def enabled(home: Path | None = None) -> bool:
    return flag_path(home).exists()


def set_enabled(on: bool, home: Path | None = None) -> bool:
    path = flag_path(home)
    if on:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    else:
        path.unlink(missing_ok=True)
    return enabled(home)


def tail(path: Path, lines: int = 12) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 16384))
            data = handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    return data[-lines:]


def frame_history(path: Path, points: int = 60) -> list[dict[str, Any]]:
    rows = []
    for line in tail(path, points):
        m = FRAME_LINE.match(line)
        if m:
            rows.append({"at": m.group(1), "tier": m.group(2), "fps": float(m.group(3)), "p95": float(m.group(4))})
    return rows


def _unit_state(unit: str, run: Callable[..., subprocess.CompletedProcess]) -> str:
    try:
        out = run(["/usr/bin/systemctl", "is-active", unit], capture_output=True, text=True, timeout=3, check=False)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def services(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> list[dict[str, str]]:
    rows = [{"name": label, "id": unit, "state": _unit_state(unit, run), "source": "systemctl is-active"}
            for unit, label in SYSTEM_UNITS]
    try:
        import psutil
        running = {p.info["name"] for p in psutil.process_iter(["name"])}
        for name, label in USER_PROCESSES:
            rows.append({"name": label, "id": name, "state": "running" if name in running else "not running",
                         "source": "process table"})
    except ImportError:
        pass
    return rows


def collect(render: dict[str, Any], frame_info: dict[str, Any], atlas: dict[str, Any], route: dict[str, Any],
            missions: list[dict[str, Any]], notes: int, inbox: int, runtime_dir: Path | None = None) -> dict[str, Any]:
    runtime = runtime_dir or Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    now = time.strftime("%H:%M:%S")
    statuses: dict[str, int] = {}
    for m in missions:
        statuses[m.get("status", "?")] = statuses.get(m.get("status", "?"), 0) + 1
    return {
        "at": now,
        "renderer": {**render, **{f"frame_{k}": v for k, v in frame_info.items()},
                     "source": "Home renderer + frame log", "history": frame_history(runtime / "apvis-nucleus-frames.log")},
        "launcher": tail(runtime / "apvis-home-attempts.log", 8),
        "services": services(),
        "route": {**{k: v for k, v in route.items() if k in {"endpoint", "reachable", "model", "version", "policy", "error"}},
                  "source": "Ask host check (Ollama /api/version, /api/tags)"},
        "feeds": [{"name": "OSIRIS aviation (ADSB.lol)", "status": atlas.get("status", "off"), "age_s": atlas.get("age_s"),
                   "count": atlas.get("count"), "error": atlas.get("error"),
                   "source": "polled only while Atlas is open"}],
        "memory": {"notes": notes, "inbox": inbox, "source": "~/APVIS Vault + Memory Inbox"},
        "missions": {"total": len(missions), "byStatus": statuses, "source": "Mission Control task store"},
    }
