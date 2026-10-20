"""What this computer is: model, CPU, GPU, memory, kernel, storage and network.

Everything is read from the machine itself (DMI, /proc, /sys, psutil, the
package database) and anything that cannot be read is simply left out; nothing
here is illustrative. Used by the Home terminal card, the Devices page and the
APVIS terminal greeting (`python3 -m apvis_os.hostinfo`).
"""
from __future__ import annotations

import getpass
import os
import platform
import re
import socket
import sys
import time
from pathlib import Path
from typing import Any

RELEASE = Path("/usr/share/apvis-os/release")
DMI = Path("/sys/class/dmi/id")
PCI = Path("/sys/bus/pci/devices")
PCI_IDS = (Path("/usr/share/misc/pci.ids"), Path("/usr/share/hwdata/pci.ids"))
DPKG_STATUS = Path("/var/lib/dpkg/status")

# The APVIS mark (the ring emblem, V3) in braille dots, 8 per character.
LOGO = [
    "⠀⠀⠀⠀⠀⠀⣠⣤⣶⣶⣶⣶⣶⣶⣤⣄⠀⠀⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⠀⠈⠉⠁⢀⣀⣀⡀⠈⠉⠁⠀⠀⠀⠀⠀⠀",
    "⠀⠀⣠⡀⠀⠀⣀⠀⠀⠘⠛⠛⠃⠀⠀⣀⠀⠀⢀⣄⠀⠀",
    "⠀⢠⣿⠇⠀⣴⡟⠁⠀⠀⢀⡀⠀⠀⠈⢻⣦⠀⠸⣿⡄⠀",
    "⠀⢸⣿⠀⠀⠉⠀⠀⢀⣾⣿⣿⣷⡀⠀⠀⠉⠀⠀⣿⡇⠀",
    "⠀⢸⣿⠀⠀⣀⠀⠀⠈⢿⣿⣿⡿⠁⠀⠀⣀⠀⠀⣿⡇⠀",
    "⠀⠘⣿⡆⠀⠻⣧⡀⠀⠀⠈⠁⠀⠀⢀⣼⠟⠀⢰⣿⠃⠀",
    "⠀⠀⠙⠁⠀⠀⠉⠀⠀⢠⣤⣤⡄⠀⠀⠉⠀⠀⠈⠋⠀⠀",
    "⠀⠀⠀⠀⠀⠀⢀⣀⡀⠈⠉⠉⠁⢀⣀⡀⠀⠀⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⠀⠙⠛⠿⠿⠿⠿⠿⠿⠛⠋⠀⠀⠀⠀⠀⠀",
]
LOGO_SMALL = [
    "⠀⠀⠀⠀⠀⢤⣴⠶⠶⠶⠶⣦⡤⠀⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⠈⠀⠠⣤⣤⠄⠀⠁⠀⠀⠀⠀⠀",
    "⠀⢀⣷⠂⢠⡶⠀⠀⠀⠀⠀⠀⢶⡄⠐⣾⡀⠀",
    "⠀⢸⡇⠀⠛⠁⠀⣰⣾⣷⣆⠀⠈⠛⠀⢸⡇⠀",
    "⠀⢸⡇⠀⣤⡀⠀⠹⢿⡿⠏⠀⢀⣤⠀⢸⡇⠀",
    "⠀⠈⡿⠄⠘⠷⠀⠀⠀⠀⠀⠀⠾⠃⠠⢿⠁⠀",
    "⠀⠀⠀⠀⠀⢀⠀⠐⠛⠛⠂⠀⡀⠀⠀⠀⠀⠀",
    "⠀⠀⠀⠀⠀⠚⠻⠶⠶⠶⠶⠟⠓⠀⠀⠀⠀⠀",
]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def os_version(release: Path = RELEASE) -> str:
    for line in _read(release).splitlines():
        if line.startswith("product_version="):
            return "APVIS OS " + line.split("=", 1)[1].strip()
    return "APVIS OS (development run)"


def model(dmi: Path = DMI) -> str:
    """e.g. "Dell OptiPlex 9020M" (vendor names shortened; placeholders ignored)."""
    vendor = _read(dmi / "sys_vendor")
    product = _read(dmi / "product_name")
    junk = {"", "To Be Filled By O.E.M.", "System Product Name", "Default string", "Not Applicable"}
    if product in junk:
        return ""
    vendor = {"Dell Inc.": "Dell", "LENOVO": "Lenovo", "Hewlett-Packard": "HP", "HP": "HP"}.get(vendor, vendor)
    if vendor in junk or product.startswith(vendor):
        return product
    return f"{vendor} {product}"


def cpu_name(cpuinfo: Path = Path("/proc/cpuinfo")) -> str:
    for line in _read(cpuinfo).splitlines():
        if line.lower().startswith("model name"):
            name = line.split(":", 1)[1].strip()
            name = re.sub(r"\((R|TM|tm|r)\)", "", name)
            name = re.sub(r"\s+CPU\s+@", " @", name)
            return re.sub(r"\s+", " ", name).strip()
    return platform.processor() or ""


def _pci_name(vendor: str, device: str, ids: tuple[Path, ...] = PCI_IDS) -> str:
    for path in ids:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(rf"^{vendor}\s+(.+)$", text, re.M)
        if not m:
            continue
        block = text[m.end():]
        stop = re.search(r"^[0-9a-f]{4}\s", block, re.M)
        block = block[:stop.start()] if stop else block
        d = re.search(rf"^\t{device}\s+(.+)$", block, re.M)
        vendor_name = m.group(1).split(" [")[0].replace(" Corporation", "")
        if d:
            name = d.group(1)
            short = re.search(r"\[(.+?)\]", name)
            return f"{vendor_name} {short.group(1) if short else name}".strip()
        return vendor_name
    return ""


def gpu_name(pci: Path = PCI, ids: tuple[Path, ...] = PCI_IDS) -> str:
    """The first display controller, named from pci.ids when present."""
    try:
        devices = sorted(pci.iterdir())
    except OSError:
        return ""
    for dev in devices:
        if not _read(dev / "class").startswith("0x03"):
            continue
        vendor, device = _read(dev / "vendor")[2:], _read(dev / "device")[2:]
        return _pci_name(vendor, device, ids) or f"PCI {vendor}:{device}"
    return ""


def package_count(status: Path = DPKG_STATUS) -> int | None:
    text = _read(status)
    return text.count("Status: install ok installed") if text else None


def uptime_text(boot_epoch: float, now: float | None = None) -> str:
    s = max(0, int((now or time.time()) - boot_epoch))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    parts = ([f"{d} day{'s' if d != 1 else ''}"] if d else []) + ([f"{h} hour{'s' if h != 1 else ''}"] if h else [])
    parts.append(f"{m} min{'s' if m != 1 else ''}")
    return ", ".join(parts)


def host_info() -> dict[str, Any]:
    info: dict[str, Any] = {"user": _user(), "name": real_name(), "hostname": socket.gethostname(), "os": os_version(),
                            "model": model(), "kernel": platform.release(), "cpu": cpu_name(), "gpu": gpu_name(),
                            "shell": os.path.basename(os.environ.get("SHELL", "")) or "bash",
                            "packages": package_count()}
    try:
        import psutil
        info["cores"] = psutil.cpu_count(logical=False)
        info["threads"] = psutil.cpu_count(logical=True)
        info["memoryGb"] = round(psutil.virtual_memory().total / 1024 ** 3, 1)
        info["bootEpoch"] = psutil.boot_time()
    except (ImportError, OSError):
        pass
    return info


def real_name(user: str | None = None) -> str:
    """The account's full name (first GECOS field), else the user name, capitalised."""
    user = user or _user()
    try:
        import pwd
        gecos = pwd.getpwnam(user).pw_gecos.split(",")[0].strip()
        if gecos:
            return gecos
    except (ImportError, KeyError):
        pass
    return user[:1].upper() + user[1:]


def _user() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return "apvis"


def storage() -> list[dict[str, Any]]:
    try:
        import psutil
    except ImportError:
        return []
    out, seen = [], set()
    for part in psutil.disk_partitions(all=False):
        if part.device in seen or part.fstype in {"squashfs", "tmpfs", "overlay"} or part.mountpoint.startswith(("/snap", "/boot/efi")):
            continue
        seen.add(part.device)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        out.append({"device": part.device, "mount": part.mountpoint, "fs": part.fstype,
                    "totalGb": round(usage.total / 1e9, 1), "usedGb": round(usage.used / 1e9, 1), "pct": round(usage.percent)})
    return out[:8]


def network() -> list[dict[str, Any]]:
    try:
        import psutil
    except ImportError:
        return []
    stats, addrs = psutil.net_if_stats(), psutil.net_if_addrs()
    out = []
    for name, st in stats.items():
        if name == "lo" or name.startswith(("docker", "veth", "virbr", "Loopback")):
            continue
        ipv4 = [a.address for a in addrs.get(name, []) if a.family == socket.AF_INET]
        kind = "Wi-Fi" if name.startswith(("wl", "Wi-Fi", "wlan")) else "Ethernet" if name.startswith(("en", "eth", "Ethernet")) else "Network"
        out.append({"name": name, "kind": kind, "up": bool(st.isup), "speedMbps": st.speed or None, "ipv4": ipv4[:2]})
    out.sort(key=lambda n: (not n["up"], not n["ipv4"], n["name"]))
    return out[:8]


def devices() -> dict[str, Any]:
    return {"host": host_info(), "storage": storage(), "network": network()}


def greeting(info: dict[str, Any] | None = None, colour: bool = True) -> str:
    """fastfetch-style APVIS greeting for a new terminal."""
    info = info or host_info()
    g, b, d, r = ("\033[38;2;227;184;98m", "\033[1m", "\033[38;2;156;145;128m", "\033[0m") if colour else ("", "", "", "")
    rows = [(k, v) for k, v in (
        ("OS", info.get("os")), ("Host", info.get("model")), ("Kernel", info.get("kernel")),
        ("Uptime", uptime_text(info["bootEpoch"]) if info.get("bootEpoch") else None),
        ("Packages", f"{info['packages']} (dpkg)" if info.get("packages") else None), ("Shell", info.get("shell")),
        ("CPU", info.get("cpu")), ("GPU", info.get("gpu")),
        ("Memory", f"{info['memoryGb']} GiB" if info.get("memoryGb") else None)) if v]
    who = (info.get("name") or "").split(" ")[0].lower() or info.get("user", "apvis")
    title = f"{who}@{info.get('hostname', 'apvis')}"
    right = [f"{g}{b}{title}{r}", d + "─" * len(title) + r] + [f"{g}{b}{k}:{r} {v}" for k, v in rows]
    lines = []
    for i in range(max(len(LOGO), len(right))):
        left = LOGO[i] if i < len(LOGO) else " " * len(LOGO[0])
        lines.append(f"{g}{left}{r}   {right[i] if i < len(right) else ''}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:                      # a terminal without a UTF-8 locale still gets a readable greeting
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.stdout.write(greeting(colour=sys.stdout.isatty() and "--plain" not in args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
