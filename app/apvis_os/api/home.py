"""Home endpoints: keyboard shortcuts and scripts steer the running Home (open a page, ask)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .server import HOST, PORT, ApiError, Request, route

# Home registers "command" here while it runs: (kind, value) -> None, e.g. ("page", "apps").
HOME_HOOKS: dict[str, Any] = {}
HOME_PAGES = {"", "apps", "settings", "system", "devices", "atlas", "missions", "notes"}


@route("POST", "/v1/home", "Open a Home page or ask on screen (Win+Space uses this)",
       body='{"page": "apps|settings|system|devices|atlas|missions|notes|\\"\\""}  or  {"ask": "question"}  or  {"restart": true}')
def home(request: Request) -> None:
    hook = HOME_HOOKS.get("command")
    if hook is None:
        raise ApiError(503, "home_not_running", "APVIS Home isn't running")
    data = request.json()
    if isinstance(data.get("page"), str) and data["page"] in HOME_PAGES:
        hook("page", data["page"])
    elif isinstance(data.get("ask"), str) and 0 < len(data["ask"].strip()) <= 4000:
        hook("ask", data["ask"].strip())
    elif data.get("power") in {"poweroff", "reboot"}:
        # Shut down or restart from a script or remote access (the owner's keys only): Home shows its goodbye
        # screen and asks the system after delay_s seconds, so a remote session can close first.
        delay = data.get("delay_s", 0)
        hook("power", f"{data['power']}:{max(0, min(300, int(delay) if isinstance(delay, (int, float)) else 0))}")
    elif data.get("restart") is True:
        hook("restart", "")                  # restart Home (e.g. after installing an update); nothing else changes
    elif isinstance(data.get("screen"), str):
        from ..screen import valid_capture
        if valid_capture(data["screen"]) is None:
            raise ApiError(400, "bad_capture", "only APVIS's own fresh screen captures are accepted")
        hook("screen", data["screen"])
    else:
        raise ApiError(400, "bad_command", "send {\"page\": one of " + ", ".join(sorted(p for p in HOME_PAGES if p)) + "} or {\"ask\": text}")
    request.send(200, {"ok": True})


def home_command(payload: dict[str, str], port: int = PORT) -> bool:
    """Send one command to a running Home (used by keyboard shortcuts); False when Home isn't there."""
    request = urllib.request.Request(f"http://{HOST}:{port}/v1/home", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False
