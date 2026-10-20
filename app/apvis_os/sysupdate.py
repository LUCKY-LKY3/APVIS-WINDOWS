"""System packages delivered by signed APVIS updates (so new features rarely need a new USB image).

An update's manifest may list Debian packages: {"packages": {"install": [...], "remove": [...]}}.
The manifest is inside the ed25519-signed bundle. The root helper
(/usr/local/lib/apvis-os/apvis-sysupdate, run through pkexec) never trusts the caller: it checks
the bundle's signature itself against the key built into the image, reads the list from the
signed manifest, accepts only plain Debian package names, and removes only packages that an
earlier APVIS update installed. Everything comes from the image's normal Debian sources.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any, Callable

HELPER = Path("/usr/local/lib/apvis-os/apvis-sysupdate")
PUBLIC_KEY = Path("/usr/share/apvis-os/update.pub")
SIGNIFY = "/usr/bin/signify-openbsd"
LEDGER = Path("/var/lib/apvis-os/sysupdate-installed.json")
NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]{1,62}$")
MAX_PACKAGES = 40


def packages_from(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """The validated package lists of a manifest (empty lists when it has none)."""
    raw = manifest.get("packages") or {}
    if not isinstance(raw, dict):
        raise ValueError("packages must be an object")
    out: dict[str, list[str]] = {}
    for key in ("install", "remove"):
        names = raw.get(key) or []
        if not isinstance(names, list) or len(names) > MAX_PACKAGES or not all(isinstance(n, str) and NAME.match(n) for n in names):
            raise ValueError(f"packages.{key} must be a short list of Debian package names")
        out[key] = sorted(set(names))
    return out


def needed(manifest: dict[str, Any]) -> bool:
    lists = packages_from(manifest)
    return bool(lists["install"] or lists["remove"])


def _signed_manifest(bundle: Path, signature: Path, run: Callable[..., Any]) -> dict[str, Any]:
    done = run([SIGNIFY, "-V", "-q", "-p", str(PUBLIC_KEY), "-m", str(bundle), "-x", str(signature)], capture_output=True, check=False)
    if done.returncode != 0:
        raise PermissionError("the update's signature doesn't match the APVIS key")
    with tarfile.open(bundle, "r:xz") as tar:
        for name in ("manifest.json", "./manifest.json"):
            try:
                handle = tar.extractfile(tar.getmember(name))
            except KeyError:
                continue
            if handle:
                return json.loads(handle.read().decode("utf-8"))
    raise ValueError("the update has no manifest")


def _ledger(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [n for n in data if isinstance(n, str) and NAME.match(n)] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def helper_main(argv: list[str], run: Callable[..., Any] = subprocess.run, ledger: Path = LEDGER) -> int:
    """Root side: argv = [bundle.tar.xz, bundle.tar.xz.sig]."""
    if len(argv) != 2:
        print("usage: apvis-sysupdate BUNDLE SIGNATURE")
        return 2
    import shutil
    import tempfile
    private = Path(tempfile.mkdtemp(prefix="apvis-sysupdate-"))       # root-only copy: can't be swapped after the check
    try:
        bundle, signature = private / "bundle.tar.xz", private / "bundle.tar.xz.sig"
        shutil.copyfile(argv[0], bundle)
        shutil.copyfile(argv[1], signature)
        manifest = _signed_manifest(bundle, signature, run)
        lists = packages_from(manifest)
    except (PermissionError, ValueError, OSError, tarfile.TarError) as exc:
        print(f"APVIS: refused: {exc}")
        return 3
    finally:
        shutil.rmtree(private, ignore_errors=True)
    owned = _ledger(ledger)
    remove = [n for n in lists["remove"] if n in owned]          # only what APVIS updates installed
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "DEBIAN_FRONTEND": "noninteractive", "LANG": "C.UTF-8"}
    if lists["install"]:
        lists_dir = Path("/var/lib/apt/lists")
        if not any(p.stat().st_mtime > time.time() - 86400 for p in lists_dir.glob("*_Packages")):
            print("APVIS: Refreshing the package list…", flush=True)
            run(["apt-get", "update", "-q"], env=env, check=False)
        print("APVIS: Installing " + ", ".join(lists["install"]) + "…", flush=True)
        done = run(["apt-get", "install", "-y", "-q", "-o", "APT::Status-Fd=1", "-o", "Dpkg::Use-Pty=0", *lists["install"]], env=env, check=False)
        if done.returncode != 0:
            return done.returncode
    if remove:
        print("APVIS: Removing " + ", ".join(remove) + "…", flush=True)
        run(["apt-get", "remove", "-y", "-q", *remove], env=env, check=False)
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps(sorted((set(owned) | set(lists["install"])) - set(remove))), encoding="utf-8")
    except OSError:
        pass
    return 0


def apply(bundle: Path, signature: Path, on_line: Callable[[str], None] = lambda line: None,
          popen: Callable[..., Any] = subprocess.Popen) -> None:
    """User side (from updates.install): run the root helper; raises RuntimeError when it fails."""
    if not HELPER.is_file():
        raise RuntimeError("This update adds system packages, which needs the APVIS OS dev.28 image or newer.")
    proc = popen(["/usr/bin/pkexec", str(HELPER), str(bundle), str(signature)], stdout=subprocess.PIPE,
                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, bufsize=1)
    tail = ""
    for line in proc.stdout:
        line = line.strip()
        if line:
            tail = line
            on_line(line)
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"System packages didn't install ({tail or f'exit code {code}'}).")


if __name__ == "__main__":
    import sys
    raise SystemExit(helper_main(sys.argv[1:]))
