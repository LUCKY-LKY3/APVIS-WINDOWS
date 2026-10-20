"""Ask about the screen (Win+Shift+S): drag over an area, APVIS answers about it.

    python3 -m apvis_os.screen          (the keybinding runs this)

The area is captured with grim + slurp into a private temporary file and handed to the running
Home over the local API. Home answers with a vision model when one is installed (this computer or
the gaming PC), otherwise from the text in the area (tesseract). The capture is deleted afterwards.
Needs grim, slurp and tesseract (image dev.27).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

CAPTURE_DIR = Path(tempfile.gettempdir())
CAPTURE_RE = re.compile(r"^apvis-screen-[0-9a-f]{12}\.png$")


def capture_path() -> Path:
    return CAPTURE_DIR / f"apvis-screen-{uuid4().hex[:12]}.png"


def valid_capture(path: str) -> Path | None:
    """Only our own fresh capture files are accepted from the API."""
    p = Path(path)
    if p.parent != CAPTURE_DIR or not CAPTURE_RE.match(p.name) or not p.is_file() or p.is_symlink():
        return None
    try:
        if p.stat().st_uid != os.getuid():
            return None
    except AttributeError:          # Windows development runs have no uids
        pass
    return p


def capture(region: bool = True) -> Path | None:
    """Take the screenshot; None when the owner cancels the area selection."""
    grim = shutil.which("grim")
    if not grim:
        raise FileNotFoundError("Screen questions come with the APVIS OS dev.27 image (grim and slurp).")
    out = capture_path()
    command = [grim]
    if region:
        slurp = shutil.which("slurp")
        if not slurp:
            raise FileNotFoundError("Screen questions come with the APVIS OS dev.27 image (slurp).")
        picked = subprocess.run([slurp, "-d", "-b", "00000088", "-c", "4cc983ff", "-s", "4cc98322"],
                                capture_output=True, text=True, timeout=120, check=False)
        if picked.returncode != 0 or not picked.stdout.strip():
            return None
        command += ["-g", picked.stdout.strip()]
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    done = subprocess.run(command + [str(out)], capture_output=True, timeout=20, check=False)
    if done.returncode != 0:
        out.unlink(missing_ok=True)
        raise OSError("The screenshot didn't work: " + done.stderr.decode("utf-8", "replace").strip()[:200])
    return out


def ocr(path: Path) -> str:
    tool = shutil.which("tesseract")
    if not tool:
        return ""
    done = subprocess.run([tool, str(path), "-", "-l", "eng", "--psm", "3"], capture_output=True, timeout=60, check=False)
    text = done.stdout.decode("utf-8", "replace") if done.returncode == 0 else ""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def main(argv: list[str] | None = None) -> int:
    from .api import home_command
    try:
        path = capture(region="--full" not in (argv or sys.argv[1:]))
    except (OSError, subprocess.SubprocessError) as exc:
        print(exc, file=sys.stderr)
        return 1
    if path is None:
        return 0                     # the owner pressed Escape
    if not home_command({"screen": str(path)}):
        path.unlink(missing_ok=True)
        print("APVIS Home isn't running.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
