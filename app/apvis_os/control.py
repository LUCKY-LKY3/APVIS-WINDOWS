"""Control Centre: the owner's direct quick controls (V2-12).

The owner pressing a control is the approval, so these run at once, but every
change is read back and the result says whether it actually took effect.
Unavailable hardware or services are reported as such, never guessed.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Any, Callable

WPCTL = "/usr/bin/wpctl"
PLAYERCTL = "/usr/bin/playerctl"
MEDIA_ACTIONS = ("play-pause", "next", "previous")
NMCLI = "/usr/bin/nmcli"
SYSTEMCTL = "/usr/bin/systemctl"
PKILL = "/usr/bin/pkill"
# Screen-off / sleep choices offered in Settings (minutes; 0 = never).
SCREEN_CHOICES = (0, 2, 5, 10, 15, 30)
SLEEP_CHOICES = (0, 15, 30, 60, 120)
SINK = "@DEFAULT_AUDIO_SINK@"

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    if not Path(argv[0]).is_file():
        raise FileNotFoundError(f"{Path(argv[0]).name} is not installed")
    return subprocess.run(argv, capture_output=True, text=True, timeout=4, check=False)


def lan_addresses() -> list[str]:
    """This computer's private (home network) IPv4 addresses."""
    try:
        import psutil
    except ImportError:
        return []
    found = []
    for name, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET:
                ip = ipaddress.ip_address(a.address)
                if ip.is_private and not ip.is_loopback:
                    found.append(a.address)
    return sorted(set(found))


class ControlCentre:
    def __init__(self, runner: Runner = _run, home: Path | None = None) -> None:
        self.run = runner
        self.home = home or Path.home()
        self.remote_flag = self.home / ".config/apvis/remote-access"
        self.power_file = self.home / ".config/apvis/power.json"

    # ---- reading
    def sound(self) -> dict[str, Any]:
        try:
            done = self.run([WPCTL, "get-volume", SINK])
            m = re.search(r"Volume:\s*([\d.]+)", done.stdout)
            if done.returncode or not m:
                return {"available": False, "detail": "No sound output found"}
            return {"available": True, "volume": round(float(m.group(1)) * 100), "muted": "MUTED" in done.stdout}
        except (OSError, subprocess.SubprocessError):
            return {"available": False, "detail": "Sound service unavailable"}

    def wifi(self) -> dict[str, Any]:
        try:
            radio = self.run([NMCLI, "radio", "wifi"])
            if radio.returncode:
                return {"available": False, "detail": "Network service unavailable"}
            active = self.run([NMCLI, "-t", "-f", "NAME,TYPE", "connection", "show", "--active"]).stdout
            devices = self.run([NMCLI, "-t", "-f", "TYPE", "device"]).stdout.split()
        except (OSError, subprocess.SubprocessError):
            return {"available": False, "detail": "Network service unavailable"}
        connections = [line.rsplit(":", 1) for line in active.splitlines() if ":" in line]
        wireless = next((name for name, kind in connections if kind.endswith("wireless")), "")
        wired = next((name for name, kind in connections if kind.endswith("ethernet")), "")
        return {"available": True, "hasWifi": "wifi" in devices, "on": radio.stdout.strip() == "enabled",
                "network": wireless, "wired": wired}

    def remote(self) -> dict[str, Any]:
        """Remote access (sshd): running or not, and how many keys the owner has authorised."""
        try:
            done = self.run([SYSTEMCTL, "is-active", "ssh.service"])
        except (OSError, subprocess.SubprocessError):
            return {"available": False, "detail": "Remote access is not installed"}
        keys = 0
        try:
            lines = (self.home / ".ssh/authorized_keys").read_text(encoding="utf-8").splitlines()
            keys = sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))
        except OSError:
            pass
        return {"available": True, "on": done.stdout.strip() == "active", "keys": keys,
                "addresses": lan_addresses(), "remembered": self.remote_flag.exists()}

    def power_settings(self) -> dict[str, Any]:
        try:
            data = json.loads(self.power_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        screen = data.get("screen_off_min", 10)
        sleep = data.get("sleep_min", 0)
        return {"screenOff": screen if screen in SCREEN_CHOICES else 10,
                "sleep": sleep if sleep in SLEEP_CHOICES else 0,
                "screenChoices": list(SCREEN_CHOICES), "sleepChoices": list(SLEEP_CHOICES)}

    def media(self) -> dict[str, Any]:
        """What's playing (Spotify, VLC, the browser… anything with MPRIS), via playerctl."""
        if not Path(PLAYERCTL).is_file():
            return {"available": False}
        try:
            done = self.run([PLAYERCTL, "metadata", "--format", "{{status}}\t{{playerName}}\t{{artist}}\t{{title}}"])
        except (OSError, subprocess.SubprocessError):
            return {"available": False}
        parts = (done.stdout or "").strip().split("\t")
        if done.returncode or len(parts) < 4 or not parts[3].strip():
            return {"available": True, "playing": False, "title": ""}
        return {"available": True, "playing": parts[0] == "Playing", "player": parts[1], "artist": parts[2].strip(), "title": parts[3].strip()}

    def state(self) -> dict[str, Any]:
        return {"sound": self.sound(), "wifi": self.wifi(), "remote": self.remote(), "power": self.power_settings(), "media": self.media()}

    # ---- changing (each one reads back)
    def media_command(self, action: str) -> dict[str, Any]:
        if action not in MEDIA_ACTIONS:
            raise ValueError("unknown media action")
        if not Path(PLAYERCTL).is_file():
            return {"ok": False, "message": "Media controls come with the APVIS OS dev.27 image (playerctl).", "state": self.state()}
        done = self.run([PLAYERCTL, action])
        return {"ok": not done.returncode, "message": "" if not done.returncode else "Nothing is playing.", "state": self.state()}

    def set_volume(self, percent: int) -> dict[str, Any]:
        percent = max(0, min(100, int(percent)))
        done = self.run([WPCTL, "set-volume", SINK, f"{percent / 100:.2f}"])
        now = self.sound()
        ok = not done.returncode and now.get("available") and abs(now.get("volume", -99) - percent) <= 1
        return {"ok": bool(ok), "message": f"Volume {now.get('volume')}%" if ok else "Volume did not change", "state": self.state()}

    def set_muted(self, muted: bool) -> dict[str, Any]:
        done = self.run([WPCTL, "set-mute", SINK, "1" if muted else "0"])
        now = self.sound()
        ok = not done.returncode and now.get("muted") == muted
        word = "Muted" if muted else "Sound on"
        return {"ok": bool(ok), "message": word if ok else "Mute did not change", "state": self.state()}

    def set_wifi(self, on: bool) -> dict[str, Any]:
        done = self.run([NMCLI, "radio", "wifi", "on" if on else "off"])
        now = self.wifi()
        ok = not done.returncode and now.get("on") == on
        message = ("Wi-Fi on" if on else "Wi-Fi off") if ok else (done.stderr.strip() or "Wi-Fi did not change")
        return {"ok": bool(ok), "message": message, "state": self.state()}

    def set_remote(self, on: bool) -> dict[str, Any]:
        done = self.run([SYSTEMCTL, "start" if on else "stop", "ssh.service"])
        now = self.remote()
        ok = not done.returncode and now.get("on") == on
        if ok:
            # Remembered across restarts (the session autostart starts it again).
            if on:
                self.remote_flag.parent.mkdir(parents=True, exist_ok=True)
                self.remote_flag.touch()
            else:
                self.remote_flag.unlink(missing_ok=True)
        if not ok:
            reason = (done.stderr or "").strip().splitlines()
            message = "Remote access did not change" + (f": {reason[-1]}" if reason else "")
        elif on and not now.get("keys"):
            message = "Remote access on, but no keys are authorised yet, so nobody can log in."
        else:
            message = "Remote access on" if on else "Remote access off"
        return {"ok": bool(ok), "message": message, "state": self.state()}

    def set_power_timers(self, screen_off_min: int, sleep_min: int) -> dict[str, Any]:
        """Save the idle timers; the session's idle watcher restarts with them."""
        if screen_off_min not in SCREEN_CHOICES or sleep_min not in SLEEP_CHOICES:
            raise ValueError("unsupported timer value")
        self.power_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.power_file.with_name(self.power_file.name + ".tmp")
        tmp.write_text(json.dumps({"screen_off_min": screen_off_min, "sleep_min": sleep_min}), encoding="utf-8")
        os.replace(tmp, self.power_file)
        # apvis-idle loops: ending swayidle makes it start again with the new timers.
        try:
            self.run([PKILL, "-u", str(os.getuid()) if hasattr(os, "getuid") else "0", "-x", "swayidle"])
        except (OSError, subprocess.SubprocessError):
            pass
        now = self.power_settings()
        ok = now["screenOff"] == screen_off_min and now["sleep"] == sleep_min
        words = lambda m: "never" if m == 0 else f"{m} min"
        return {"ok": ok, "message": f"Screen off after {words(screen_off_min)}, sleep after {words(sleep_min)}"
                if ok else "Timers were not saved", "state": self.state()}

    # ---- power (the UI asks for a second press before calling this)
    POWER = {
        "suspend": (["/usr/bin/systemctl", "suspend"], "Going to sleep"),
        "reboot": (["/usr/bin/systemctl", "reboot"], "Restarting"),
        "poweroff": (["/usr/bin/systemctl", "poweroff"], "Shutting down"),
        "logout": (["/usr/bin/labwc", "--exit"], "Logging out"),
    }

    def power(self, action: str) -> dict[str, Any]:
        if action not in self.POWER:
            raise ValueError("unknown power action")
        argv, word = self.POWER[action]
        done = self.run(argv)
        if done.returncode and argv[0].endswith("systemctl"):
            # An app holding a shutdown lock (or another open session) blocks the plain request; retry ignoring locks.
            done = self.run(argv + ["-i"])
        if done.returncode and action == "logout" and os.environ.get("XDG_SESSION_ID"):
            # labwc --exit finds labwc through LABWC_PID; without it, end this login session directly
            # (greetd then shows the login screen).
            done = self.run(["/usr/bin/loginctl", "terminate-session", os.environ["XDG_SESSION_ID"]])
        if done.returncode:
            reason = (done.stderr or done.stdout).strip().splitlines()
            return {"ok": False, "message": f"{word} was refused: {reason[-1] if reason else 'no reason given'}"}
        # The session or machine is going away; success cannot be observed from here.
        return {"ok": True, "message": f"{word}…"}
