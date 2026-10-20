"""The APVIS login screen (V4): greetd's greeter on an installed APVIS OS.

greetd runs it at every boot as its greeter user, inside cage (/usr/local/lib/apvis-os/apvis-greeter-session
and apvis-greeter). The live USB keeps autologin and never shows it. Two accounts: APVIS (the owner, the
administrator; its own password) and Guest (no password; look around, nothing is saved).

It talks to greetd over $GREETD_SOCK: JSON messages, each after a 4-byte length in native byte order.
create_session -> answer PAM's questions (post_auth_message_response) -> start_session, then exit so
greetd starts the session. A failed attempt is always cancelled (cancel_session) so the next one starts
clean. The password goes to greetd only; it is never stored, logged or shown.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

QML_GREETER = Path("/usr/share/apvis-os/qml/greeter/Greeter.qml")
SESSION = "/usr/local/lib/apvis-os/apvis-v2-session"
SESSION_ENV = ("XDG_SESSION_TYPE=wayland", "XDG_SESSION_DESKTOP=labwc", "XDG_CURRENT_DESKTOP=labwc")
HEADER = struct.Struct("=I")          # u32, native byte order (greetd-ipc)
MAX_MESSAGE = 64 * 1024
MAX_STEPS = 12                        # PAM conversations are a few messages; more means something is wrong
CONSOLE_HINT = "press Ctrl+Alt+F2 for a text console"

# The accounts the login screen offers, in order. Never a real root login: APVIS is the administrator
# (in sudo, asks its own password for admin actions); Guest has no rights at all.
ACCOUNTS = (
    {"user": "apvis", "name": "APVIS", "role": "Administrator", "password": True},
    {"user": "guest", "name": "Guest", "role": "Look around, nothing is saved", "password": False},
)
# No password agent: the greeter's stdin is the console behind cage, where nobody could answer one.
POWER = {"reboot": ("/usr/bin/systemctl", "--no-ask-password", "reboot"),
         "poweroff": ("/usr/bin/systemctl", "--no-ask-password", "poweroff")}


class GreetdError(RuntimeError):
    """greetd could not be reached or answered something that isn't greetd-ipc."""


# ---------------------------------------------------------------- greetd-ipc framing

def encode(message: dict[str, Any]) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return HEADER.pack(len(body)) + body


def _read_exact(sock: Any, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise GreetdError("greetd closed the connection")
        data += chunk
    return data


def read_message(sock: Any) -> dict[str, Any]:
    (size,) = HEADER.unpack(_read_exact(sock, HEADER.size))
    if size > MAX_MESSAGE:
        raise GreetdError("greetd sent an oversized message")
    try:
        reply = json.loads(_read_exact(sock, size).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise GreetdError("greetd sent something that isn't JSON") from exc
    if not isinstance(reply, dict) or not isinstance(reply.get("type"), str):
        raise GreetdError("greetd sent an unexpected message")
    return reply


class Channel(Protocol):
    def request(self, message: dict[str, Any]) -> dict[str, Any]: ...
    def close(self) -> None: ...


class GreetdClient:
    """One connection to greetd: one request, one reply."""

    def __init__(self, sock: Any) -> None:
        self.sock = sock

    @classmethod
    def connect(cls, path: str | None = None, timeout: float = 30.0) -> "GreetdClient":
        path = path or os.environ.get("GREETD_SOCK", "")
        if not path:
            raise GreetdError("GREETD_SOCK is not set (the login screen only runs under greetd)")
        family = getattr(socket, "AF_UNIX", None)
        if family is None:
            raise GreetdError("this system has no Unix sockets")
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(timeout)          # PAM may wait a few seconds after a wrong password
        try:
            sock.connect(path)
        except OSError as exc:
            sock.close()
            raise GreetdError(str(exc.strerror or exc)) from exc
        return cls(sock)

    def request(self, message: dict[str, Any]) -> dict[str, Any]:
        try:
            self.sock.sendall(encode(message))
            return read_message(self.sock)
        except OSError as exc:
            raise GreetdError(f"lost the connection to greetd ({exc.strerror or exc})") from exc

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------- the login conversation

@dataclass
class Outcome:
    ok: bool
    message: str = ""
    rejected: bool = False


def _cancel(channel: Channel) -> None:
    try:
        channel.request({"type": "cancel_session"})
    except GreetdError:
        pass


def _plain(text: str) -> str:
    text = " ".join(str(text or "").split())
    return text[:1].upper() + text[1:] if text else ""


def login(channel: Channel, username: str, password: str, *, cmd: list[str] | None = None,
          env: tuple[str, ...] | list[str] = SESSION_ENV, secret_needed: bool = True) -> Outcome:
    """Sign one account in: create the session, answer PAM, start the session. Any failure cancels it."""
    cmd = list(cmd or [SESSION])
    reply = channel.request({"type": "create_session", "username": username})
    if reply.get("type") == "error" and "already" in str(reply.get("description", "")).lower():
        # A session left half-configured (e.g. the greeter restarted mid-login): cancel it, start again.
        _cancel(channel)
        reply = channel.request({"type": "create_session", "username": username})
    answered = False
    notes: list[str] = []
    for _ in range(MAX_STEPS):
        kind = reply.get("type")
        if kind == "success":
            started = channel.request({"type": "start_session", "cmd": cmd, "env": list(env)})
            if started.get("type") == "success":
                return Outcome(True, "")
            _cancel(channel)
            return Outcome(False, "The session didn't start: " + (_plain(started.get("description", "")) or "no reason given") + ".")
        if kind == "error":
            _cancel(channel)
            if reply.get("error_type") == "auth_error":
                if not secret_needed:
                    return Outcome(False, notes[-1] if notes else "Guest isn't available on this computer right now.")
                return Outcome(False, notes[-1] if notes else "That password isn't right.", rejected=True)
            return Outcome(False, _plain(reply.get("description", "")) or "Sign-in failed.")
        if kind != "auth_message":
            _cancel(channel)
            return Outcome(False, "The login service answered something unexpected.")
        prompt_type = reply.get("auth_message_type")
        prompt = str(reply.get("auth_message", ""))
        if prompt_type == "secret":
            if answered:
                # A second secret question (a new password, a one-time code): this screen only knows one.
                _cancel(channel)
                return Outcome(False, _plain(prompt.rstrip(": ")) + f" is needed, which this screen can't ask for: {CONSOLE_HINT}.")
            answered = True
            reply = channel.request({"type": "post_auth_message_response", "response": password})
        elif prompt_type == "visible":
            if any(word in prompt.lower() for word in ("login", "user", "name")):
                reply = channel.request({"type": "post_auth_message_response", "response": username})
            else:
                _cancel(channel)
                return Outcome(False, _plain(prompt.rstrip(": ")) + f" is needed, which this screen can't ask for: {CONSOLE_HINT}.")
        else:                                    # info or error from PAM: keep it for the message, carry on
            if prompt.strip():
                notes.append(_plain(prompt))
            reply = channel.request({"type": "post_auth_message_response"})
    _cancel(channel)
    return Outcome(False, "Sign-in took too many steps; try again.")


def attempt(connect: Callable[[], Channel], username: str, password: str, *, secret_needed: bool = True,
            cmd: list[str] | None = None) -> Outcome:
    """One sign-in over a fresh connection; a greetd that can't be reached is said plainly."""
    try:
        channel = connect()
    except GreetdError as exc:
        return Outcome(False, f"The login service isn't answering ({exc}). Try again, or {CONSOLE_HINT}.")
    try:
        outcome = login(channel, username, password, cmd=cmd, secret_needed=secret_needed)
    except GreetdError as exc:
        outcome = Outcome(False, f"The login service stopped answering ({exc}). Try again.")
    if not outcome.ok:
        channel.close()                          # after success the socket stays open until the greeter exits
    return outcome


def available_accounts(exists: Callable[[str], bool] | None = None) -> list[dict[str, Any]]:
    """The accounts to show: APVIS always; Guest only when the account exists on this computer."""
    if exists is None:
        def exists(user: str) -> bool:
            try:
                import pwd
            except ImportError:                  # not Linux (render harness): show both
                return True
            try:
                pwd.getpwnam(user)
                return True
            except KeyError:
                return False
    return [dict(a) for a in ACCOUNTS if a["user"] == "apvis" or exists(a["user"])]


def power(action: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> tuple[bool, str]:
    """Restart or shut down from the login screen (logind allows the local greeter; see 64-apvis-greeter.rules)."""
    if action not in POWER:
        return False, "Unknown power action."
    word = "Restart" if action == "reboot" else "Shut down"
    try:
        done = run(list(POWER[action]), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{word} didn't work: {exc}"
    if done.returncode:
        reason = (done.stderr or done.stdout or "").strip().splitlines()
        return False, f"{word} was refused: {reason[-1] if reason else 'no reason given'}"
    return True, "Restarting…" if action == "reboot" else "Shutting down…"


# ---------------------------------------------------------------- the screen

def run(qml_path: Path = QML_GREETER, *, connect: Callable[[], Channel] | None = None,
        power_runner: Callable[[str], tuple[bool, str]] | None = None, windowed: bool = False,
        size: tuple[int, int] | None = None, screenshot: Path | None = None, preview: str = "",
        delay_ms: int = 1500, accounts: list[dict[str, Any]] | None = None) -> int:
    from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    connect = connect or GreetdClient.connect
    power_runner = power_runner or power
    software = os.environ.get("QT_QUICK_BACKEND") == "software" or os.environ.get("QSG_RHI_BACKEND") == "software"

    class GreeterBridge(QObject):
        busyChanged = Signal()
        messageChanged = Signal()
        signedIn = Signal()                       # QML fades out; the app quits and greetd starts the session
        wrongPassword = Signal()
        _finished = Signal(bool, str, bool)       # from the worker thread (delivered queued)

        def __init__(self) -> None:
            super().__init__()
            self._busy = False
            self._message = ""
            self._tone = "info"
            self._accounts = accounts if accounts is not None else available_accounts()
            self._finished.connect(self._done)

        @Property("QVariantList", constant=True)
        def accounts(self) -> list[dict[str, Any]]:
            return self._accounts

        @Property(bool, constant=True)
        def software(self) -> bool:
            return software

        @Property(bool, notify=busyChanged)
        def busy(self) -> bool:
            return self._busy

        @Property(str, notify=messageChanged)
        def message(self) -> str:
            return self._message

        @Property(str, notify=messageChanged)
        def tone(self) -> str:
            return self._tone

        def _say(self, message: str, tone: str = "info") -> None:
            self._message, self._tone = message, tone
            self.messageChanged.emit()

        def _set_busy(self, busy: bool) -> None:
            self._busy = busy
            self.busyChanged.emit()

        @Slot(str, str)
        def login(self, user: str, password: str) -> None:
            if self._busy:
                return
            account = next((a for a in self._accounts if a["user"] == user), None)
            if account is None:
                self._say("That account isn't on this computer.", "error")
                return
            if account["password"] and not password:
                self._say("Type the APVIS password, then press Enter.", "info")
                return
            self._set_busy(True)
            self._say("", "info")                # the field says "Checking…" / the button "Opening…"

            def work(secret: str = password if account["password"] else "") -> None:
                outcome = attempt(connect, user, secret, secret_needed=bool(account["password"]))
                self._finished.emit(outcome.ok, outcome.message, outcome.rejected)

            threading.Thread(target=work, name="apvis-greeter-login", daemon=True).start()

        @Slot(bool, str, bool)
        def _done(self, ok: bool, message: str, wrong: bool) -> None:
            if ok:
                self._say("Welcome.", "info")
                self.signedIn.emit()
                QTimer.singleShot(450, QGuiApplication.quit)      # greetd starts the session once we exit
                return
            self._set_busy(False)
            self._say(message, "error")
            if wrong:
                self.wrongPassword.emit()

        @Slot()
        def clearMessage(self) -> None:
            if not self._busy:
                self._say("", "info")

        @Slot(str)
        def power(self, action: str) -> None:
            if self._busy:
                return
            self._say("Restarting…" if action == "reboot" else "Shutting down…", "info")

            def work() -> None:
                ok, message = power_runner(action)
                if not ok:
                    self._finished.emit(False, message, False)

            threading.Thread(target=work, name="apvis-greeter-power", daemon=True).start()

    try:                                          # plain controls: the screen draws its own fields
        from PySide6.QtQuickControls2 import QQuickStyle
        QQuickStyle.setStyle("Basic")
    except ImportError:
        pass
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("APVIS OS login")
    app.setDesktopFileName("apvis-greeter")
    fonts = qml_path.resolve().parent.parent / "fonts"
    if fonts.is_dir():
        for font in sorted(fonts.glob("*.[ot]tf")):
            QFontDatabase.addApplicationFont(str(font))
    if "Inter" in QFontDatabase.families():
        base = QFont(app.font())
        base.setFamily("Inter")
        app.setFont(base)
    bridge = GreeterBridge()
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty("greeter", bridge)
    context.setContextProperty("previewWindowed", windowed)
    context.setContextProperty("previewState", preview)
    context.setContextProperty("previewSize", {"width": size[0] if size else 0, "height": size[1] if size else 0})
    engine.load(QUrl.fromLocalFile(str(qml_path.resolve())))
    if not engine.rootObjects():
        return 2
    window = engine.rootObjects()[0]
    engine._greeter_bridge = bridge               # keep the context property alive
    captured = {"ok": False}
    if screenshot is not None:
        screenshot.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            image = window.grabWindow()
            captured["ok"] = not image.isNull() and image.save(str(screenshot))

        QTimer.singleShot(delay_ms, capture)
        QTimer.singleShot(delay_ms + 400, app.quit)
    status = int(app.exec())
    # Tear the screen down while the bridge still exists (otherwise its bindings see a null bridge).
    del window
    del engine
    return 3 if screenshot is not None and not captured["ok"] else status


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="APVIS OS login screen (a greetd greeter)")
    parser.add_argument("--qml", type=Path, default=QML_GREETER)
    parser.add_argument("--windowed", action="store_true", help="a normal window, for development")
    args = parser.parse_args(argv)
    return run(args.qml, windowed=args.windowed)


if __name__ == "__main__":
    raise SystemExit(main())
