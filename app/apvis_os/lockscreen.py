"""The Home lock screen's password check.

The password is checked by the system's own PAM helper (unix_chkpwd, the
program pam_unix uses), which lets a user verify their own password without
root. APVIS never stores, logs or compares the password itself; a wrong
password is answered after a short pause.
"""
from __future__ import annotations

import getpass
import subprocess
import time
from pathlib import Path
from typing import Callable

HELPERS = (Path("/usr/sbin/unix_chkpwd"), Path("/sbin/unix_chkpwd"))
FAIL_DELAY_S = 1.2


def check_password(password: str, user: str | None = None, *, run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                   helpers: tuple[Path, ...] = HELPERS, sleep: Callable[[float], None] = time.sleep) -> tuple[bool, str]:
    helper = next((h for h in helpers if h.is_file()), None)
    if helper is None:
        return False, "Password checking isn't available on this computer."
    if not password:
        return False, "Type your password."
    user = user or getpass.getuser()
    try:
        done = run([str(helper), user, "nullok"], input=password.encode("utf-8") + b"\0",
                   capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False, "The password check didn't answer. Try again."
    if done.returncode == 0:
        return True, ""
    sleep(FAIL_DELAY_S)
    return False, "That password isn't right."
