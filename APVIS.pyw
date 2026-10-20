"""APVIS for Windows: APVIS Home full screen on its own monitor (the second one when it's connected).

Double-click this file (pythonw), or use the Start-menu shortcut the installer makes. Alt+F4 closes it.
Environment overrides: APVIS_SCREEN=<n> picks a monitor (1 = first); APVIS_WINDOWED=1 opens a normal window.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / "app"
QML = APP / "qml" / "Home.qml"
DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "APVIS"


def use_neural_look() -> None:
    """The Windows app's look is APVIS 7's blue "Neural Fabric" (owner, 2026-10-20). Set it once; a look picked in
    Settings afterwards is kept."""
    import json
    marker = DATA / "neural-look-set"
    if marker.exists():
        return
    prefs_file = Path.home() / ".config" / "apvis" / "ui.json"
    try:
        prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prefs = {}
    if not isinstance(prefs, dict):
        prefs = {}
    prefs["accent"] = "neural"
    try:
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
        marker.write_text("1", encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("APVIS_OS_STATE_DIR", str(DATA / "state"))
    os.environ.setdefault("XDG_RUNTIME_DIR", str(DATA / "run"))
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    os.environ.setdefault("APVIS_GAME_MODE", "1")
    (DATA / "run").mkdir(exist_ok=True)
    use_neural_look()
    sys.path.insert(0, str(APP))

    # pythonw has no console: keep a log of anything that goes wrong.
    log = open(DATA / "apvis.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    if sys.stdout is None or not sys.stdout.isatty():
        sys.stdout = sys.stderr = log

    # The world map and core data ship next to the QML, not in /usr/share as on APVIS OS.
    import apvis_os.nucleus as nucleus
    nucleus.EARTH_POINTS = APP / "geo" / "earth-land-points.json"
    local = lambda path=nucleus.EARTH_POINTS: nucleus.load_earth_points(path)  # noqa: E731
    import apvis_os.shell_app as shell
    shell.load_earth_points = local
    try:
        import apvis_os.nucleus_qt as nucleus_qt
        nucleus_qt.load_earth_points = local
    except ImportError:
        pass
    return shell.run(QML, windowed=os.environ.get("APVIS_WINDOWED") == "1")


if __name__ == "__main__":
    raise SystemExit(main())
