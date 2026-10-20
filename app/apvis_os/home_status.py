"""Real, sourced state for the Home panels (no illustrative numbers).

Cheap readings (CPU, memory, disk) come from psutil; slower ones (Wi-Fi,
volume, the AI host) are read by the caller in a background thread. Every
reading says where it came from; anything unavailable is reported as such.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .ask import AskConfig, resolve_model
from .ollama import OllamaClient, OllamaError


def quick_status(home: Path | None = None) -> dict[str, Any]:
    try:
        import psutil
    except ImportError:
        return {"available": False}
    memory = psutil.virtual_memory()
    try:
        disk = shutil.disk_usage(home or Path.home())
        disk_pct = round(100 * disk.used / disk.total)
    except OSError:
        disk_pct = None
    battery = None
    try:
        sensor = psutil.sensors_battery()
        if sensor is not None:
            battery = {"percent": round(sensor.percent), "plugged": bool(sensor.power_plugged)}
    except (AttributeError, OSError):
        pass
    try:
        net = psutil.net_io_counters()
        net_bytes = {"rx": int(net.bytes_recv), "tx": int(net.bytes_sent), "at": time.monotonic()}
    except (AttributeError, OSError):
        net_bytes = None
    return {
        "net": net_bytes,
        "available": True,
        "cpu": round(psutil.cpu_percent(interval=None)),
        "memory": round(memory.percent),
        "disk": disk_pct,
        "battery": battery,
        "hostname": socket.gethostname(),
        "uptime_min": int((time.time() - psutil.boot_time()) // 60),
        "boot_epoch_ms": int(psutil.boot_time() * 1000),
    }


def net_rates(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any] | None:
    """Bytes per second between two counter readings (None until two readings exist)."""
    if not previous or not current:
        return None
    dt = current["at"] - previous["at"]
    if dt <= 0.2:
        return None
    return {"down": max(0, round((current["rx"] - previous["rx"]) / dt)),
            "up": max(0, round((current["tx"] - previous["tx"]) / dt))}


def _run(command: list[str]) -> str | None:
    if not shutil.which(command[0]) and not Path(command[0]).is_file():
        return None
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def slow_status() -> dict[str, Any]:
    """Wi-Fi and volume via nmcli/wpctl (only if installed)."""
    result: dict[str, Any] = {"wifi": None, "volume": None, "muted": False}
    wifi = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"])
    if wifi is not None:
        active = [line.split(":") for line in wifi.splitlines() if line.startswith("yes:")]
        result["wifi"] = {"connected": bool(active), "ssid": active[0][1] if active else "",
                          "signal": int(active[0][2]) if active and active[0][2].isdigit() else None}
    wired = _run(["nmcli", "-t", "-f", "TYPE,STATE", "dev"])
    if wired is not None:
        result["wired"] = any(line.startswith("ethernet:connected") for line in wired.splitlines())
    volume = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    if volume:
        m = re.search(r"Volume:\s*([\d.]+)", volume)
        if m:
            result["volume"] = round(float(m.group(1)) * 100)
            result["muted"] = "MUTED" in volume
    return result


def route_status() -> dict[str, Any]:
    """Which model Ask would use right now, and whether its host answers."""
    try:
        config = AskConfig.load()
    except (OSError, ValueError) as exc:
        return {"reachable": False, "error": f"Ask settings unreadable: {exc}"}
    host = re.sub(r"^https?://", "", config.ollama_url)
    local_machine = host.startswith(("127.", "localhost", "[::1]"))
    info: dict[str, Any] = {"endpoint": config.ollama_url, "host": host, "thisDevice": local_machine,
                            "policy": config.destination_policy, "reachable": False, "model": None}
    try:
        client = OllamaClient(config.ollama_url, timeout=3)
        info["version"] = client.version()
        installed = client.models()
        info["model"] = resolve_model("fast", config.roles, installed)
        info["reachable"] = True
    except (OllamaError, ValueError) as exc:
        info["error"] = str(exc)
    return info
