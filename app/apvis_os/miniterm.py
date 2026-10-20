"""The Home mini terminal: a handful of safe APVIS commands, not a shell.

Nothing typed here is ever run as a program. Each command is looked up in a
fixed table; measurements come from the same code that answers Ask
(apvis_os.facts), and "open"/"ask" hand back an action for Home to carry out.
For a real shell, `terminal` opens one.
"""
from __future__ import annotations

import platform
import socket
import time
from typing import Any

from . import facts, hostinfo

OPENABLE = {"files": "launch:files", "apps": "launch:apps", "terminal": "launch:terminal", "editor": "launch:editor",
            "settings": "page:settings", "atlas": "page:atlas", "intelligence": "page:atlas", "system": "page:system",
            "devices": "page:devices", "memory": "page:notes", "automation": "page:missions", "missions": "page:missions"}

HELP = [
    ("help", "this list"), ("fastfetch", "this computer at a glance"), ("cpu | mem | disk", "what is using it"),
    ("ip", "this computer's address"), ("uptime", "how long it has been on"), ("check", "a full system check"),
    ("models", "local AI models installed"), ("open <place>", "files, apps, settings, atlas, system, devices…"),
    ("ask <question>", "ask APVIS"), ("clear", "clear this card"), ("terminal", "open a full terminal"),
]


def _line(text: str, tone: str = "text") -> dict[str, str]:
    return {"t": text, "c": tone}


def fastfetch(info: dict[str, Any] | None = None) -> list[dict[str, str]]:
    info = info or hostinfo.host_info()
    rows = [(k, v) for k, v in (
        ("OS", info.get("os")), ("Host", info.get("model") or info.get("hostname")), ("Kernel", info.get("kernel")),
        ("Uptime", hostinfo.uptime_text(info["bootEpoch"]) if info.get("bootEpoch") else None),
        ("CPU", info.get("cpu")), ("Memory", f"{info['memoryGb']} GiB" if info.get("memoryGb") else None)) if v]
    logo = hostinfo.LOGO_SMALL
    out = []
    for i in range(max(len(logo), len(rows))):
        left = logo[i] if i < len(logo) else " " * len(logo[0])
        right = f"{rows[i][0]}: {rows[i][1]}" if i < len(rows) else ""
        out.append({"t": left, "c": "accent", "r": right})
    return out


def run(line: str) -> dict[str, Any]:
    """One command → {"lines": [...], "action": optional key for Home}."""
    words = (line or "").strip().split()
    if not words:
        return {"lines": []}
    cmd, rest = words[0].lower(), " ".join(words[1:])
    if cmd in {"help", "?", "commands"}:
        return {"lines": [_line(f"{k:<16} {v}", "muted") for k, v in HELP]}
    if cmd in {"fastfetch", "neofetch", "about"}:
        return {"lines": fastfetch()}
    if cmd in {"clear", "cls"}:
        return {"lines": [], "action": "clear"}
    if cmd == "terminal":
        return {"lines": [_line("Opening a terminal…", "muted")], "action": "launch:terminal"}
    if cmd == "open":
        target = OPENABLE.get(rest.lower())
        if not target:
            return {"lines": [_line("open what? " + ", ".join(sorted(OPENABLE)), "warn")]}
        return {"lines": [_line(f"Opening {rest.lower()}…", "muted")], "action": target}
    if cmd == "ask":
        if not rest:
            return {"lines": [_line("ask <question>, e.g. ask what's using my memory", "warn")]}
        return {"lines": [_line("Asking APVIS…", "muted")], "action": "ask:" + rest}
    if cmd in {"cpu", "top"}:
        return {"lines": [_line(facts.answer("cpu_top"))]}
    if cmd in {"mem", "memory", "ram"}:
        return {"lines": [_line(facts.answer("memory")), _line(facts.answer("mem_top"), "muted")]}
    if cmd in {"disk", "df", "storage"}:
        rows = hostinfo.storage()
        return {"lines": [_line(f"{d['mount']:<12} {d['usedGb']:>7} / {d['totalGb']} GB  {d['pct']}%") for d in rows]
                or [_line("No disks reported.", "warn")]}
    if cmd in {"ip", "ifconfig"}:
        return {"lines": [_line(facts.answer("ip"))]}
    if cmd == "uptime":
        return {"lines": [_line(facts.answer("uptime"))]}
    if cmd in {"check", "health", "analyse", "analyze"}:
        return {"lines": [_line(facts.health_report())]}
    if cmd == "models":
        try:
            from .ask import AskConfig
            from .ollama import OllamaClient
            names = OllamaClient(AskConfig.load().ollama_url, timeout=3).models()
            return {"lines": [_line(n) for n in names] or [_line("No models installed yet. Settings → Local AI.", "warn")]}
        except Exception as exc:  # not running, not reachable
            return {"lines": [_line(f"Local AI not reachable: {exc}", "warn")]}
    if cmd in {"whoami", "hostname"}:
        return {"lines": [_line(hostinfo._user() if cmd == "whoami" else socket.gethostname())]}
    if cmd in {"date", "time"}:
        return {"lines": [_line(time.strftime("%A %d %B %Y, %H:%M:%S"))]}
    if cmd == "uname":
        return {"lines": [_line(f"{platform.system()} {platform.release()} {platform.machine()}")]}
    if cmd == "echo":
        return {"lines": [_line(rest)]}
    return {"lines": [_line(f"{cmd}: not an APVIS command. Type help, or terminal for a full shell.", "warn")]}
