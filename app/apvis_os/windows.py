"""Open app windows, for the APVIS logo's menu (V4, owner: "when you click the apvis logo it shows a drop down of
all the current apps"). Wayland apps can't see each other, so this asks the compositor through wlrctl (on the V4
image); without wlrctl the list is empty and says why."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, Callable

HIDDEN = {"apvis-home", "apvis-greeter"}          # Home itself is the first menu entry; the greeter never shows


def parse_list(text: str) -> list[dict[str, str]]:
    """`wlrctl toplevel list` prints one window per line as "app_id: title"."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        app, sep, title = line.partition(": ")
        if not sep:
            app, title = line.rstrip(":"), ""
        app, title = app.strip(), title.strip()
        if not app or app in HIDDEN:
            continue
        out.append({"app": app, "title": title or app})
    return out[:30]


def available() -> bool:
    return shutil.which("wlrctl") is not None


def list_windows(run: Callable[..., Any] = subprocess.run) -> list[dict[str, str]]:
    tool = shutil.which("wlrctl")
    if not tool:
        return []
    try:
        done = run([tool, "toplevel", "list"], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_list(done.stdout if done.returncode == 0 else "")


def focus(window: dict[str, str], run: Callable[..., Any] = subprocess.run) -> bool:
    """Bring that window forward (and out of minimised). Matches its app and, when known, its title."""
    tool = shutil.which("wlrctl")
    if not tool or not window.get("app"):
        return False
    args = [tool, "toplevel", "focus", f"app_id:{window['app']}"]
    if window.get("title") and window["title"] != window["app"]:
        args.append(f"title:{window['title']}")
    try:
        return run(args, capture_output=True, timeout=3, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
