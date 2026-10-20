"""Ask about the owner's files: "summarise report.docx", "what's in notes.txt in my documents".

Only files inside the home folder are read (never hidden folders), and only to answer that
question with the same brain as Ask. Word (.docx), OpenDocument (.odt/.ods/.odp), text, Markdown,
code and web pages are read with Python itself; PDFs use pdftotext (poppler-utils, image dev.27).
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".toml",
                 ".py", ".sh", ".js", ".ts", ".qml", ".c", ".h", ".cpp", ".hpp", ".java", ".rs", ".go", ".rb", ".php", ".css", ".sql",
                 ".xml", ".tex", ".srt", ".html", ".htm"}
OFFICE_SUFFIXES = {".docx", ".odt", ".ods", ".odp"}
MAX_BYTES = 30 * 1024 ** 2
SEARCH_DEPTH = 5
FOLDERS = {"documents": "Documents", "downloads": "Downloads", "desktop": "Desktop", "pictures": "Pictures", "music": "Music",
           "videos": "Videos", "home": "", "vault": "APVIS Vault"}

_ASK = re.compile(
    r"(?i)^\s*(?:hey\s+apvis[,\s]*)?(?:please\s+)?(?:can you\s+|could you\s+)?"
    r"(?P<verb>summari[sz]e|sum up|read|explain|check|proofread|review|translate|"
    r"what(?:'s| is)\s+in|what\s+does|tell\s+me\s+(?:about|what's\s+in)|give\s+me\s+(?:the\s+)?key\s+points\s+(?:of|from))\s+"
    r"(?:the\s+|my\s+|this\s+)?(?:file\s+|document\s+|doc\s+)?"
    r"(?P<name>[~/\w .()'&,-]+?\.(?P<ext>[a-z0-9]{1,5}))"
    r"(?:\s+(?:in|from|on)\s+(?:my\s+|the\s+)?(?P<where>\w+)(?:\s+folder)?)?"
    r"(?P<rest>\s+(?:say|mean|about|for me|in\s+\w+))?\s*[?.!]*\s*$")


class DocumentError(ValueError):
    """The file can't be found or read (the message is shown to the owner)."""


def match(question: str) -> dict[str, str] | None:
    m = _ASK.match(question or "")
    if not m or ("." + m.group("ext").lower()) not in TEXT_SUFFIXES | OFFICE_SUFFIXES | {".pdf"}:
        return None
    found = {"name": m.group("name").strip(), "where": (m.group("where") or "").lower()}
    # "explain node.js" / "tell me about three.js" name a library, not one of the owner's files (V4: these got
    # "I couldn't find a file called 'node.js'" instead of an answer). Only an existing file counts then.
    if (m.group("ext").lower() in ("js", "ts") and re.fullmatch(r"[\w-]+\.(?:js|ts)", found["name"], re.I)
            and not found["where"] and not re.search(r"(?i)\b(?:file|document|doc|my|this)\b", question[:m.start("name")])):
        try:
            find(found["name"])
        except DocumentError:
            return None
    return found


def find(name: str, where: str = "", home: Path | None = None) -> Path:
    """The owner's file by name (or a path inside home); the closest match wins."""
    home = (home or Path.home()).resolve()
    raw = os.path.expanduser(name.strip())
    if "/" in raw:
        path = (Path(raw) if Path(raw).is_absolute() else home / raw).resolve()
        if home not in path.parents or any(p.startswith(".") for p in path.relative_to(home).parts):
            raise DocumentError("APVIS only reads files inside your home folder (not hidden ones).")
        if not path.is_file():
            raise DocumentError(f"There's no file at {path}.")
        return path
    base = home / FOLDERS[where] if where in FOLDERS else home
    wanted = raw.lower()
    exact: list[Path] = []
    close: list[Path] = []
    for top, dirs, files in os.walk(base):
        depth = len(Path(top).relative_to(base).parts)
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__"} and depth < SEARCH_DEPTH]
        for f in files:
            low = f.lower()
            if low == wanted:
                exact.append(Path(top, f))
            elif wanted in low or low.startswith(wanted.rsplit(".", 1)[0]):
                close.append(Path(top, f))
    for group in (exact, close):
        if group:
            return sorted(group, key=lambda p: (len(p.parts), -p.stat().st_mtime))[0]
    raise DocumentError(f"I couldn't find a file called {name!r}" + (f" in {FOLDERS.get(where, where)}" if where else " in your home folder") + ".")


def _strip_xml(xml: str, paragraph: str) -> str:
    xml = re.sub(rf"</?{paragraph}\b[^>]*>", "\n", xml)
    xml = re.sub(r"<(w:tab|text:tab)\b[^>]*/?>", "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def extract(path: Path) -> str:
    """The readable text of one file."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise DocumentError(f"Couldn't open {path.name}: {exc.strerror or exc}") from None
    if size > MAX_BYTES:
        raise DocumentError(f"{path.name} is too big to read ({size // 1048576} MB).")
    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            if suffix in {".html", ".htm", ".xml"}:
                text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
                text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        elif suffix == ".docx":
            with zipfile.ZipFile(path) as z:
                text = _strip_xml(z.read("word/document.xml").decode("utf-8", "replace"), "w:p")
        elif suffix in {".odt", ".ods", ".odp"}:
            with zipfile.ZipFile(path) as z:
                text = _strip_xml(z.read("content.xml").decode("utf-8", "replace"), "text:(?:p|h)")
        elif suffix == ".pdf":
            tool = shutil.which("pdftotext")
            if not tool:
                raise DocumentError("Reading PDFs comes with the APVIS OS dev.27 image (pdftotext).")
            done = subprocess.run([tool, "-layout", "-l", "40", str(path), "-"], capture_output=True, timeout=45, check=False)
            if done.returncode != 0:
                raise DocumentError(f"{path.name} couldn't be read as a PDF.")
            text = done.stdout.decode("utf-8", "replace")
        else:
            raise DocumentError(f"APVIS can't read {suffix} files yet.")
    except (zipfile.BadZipFile, KeyError):
        raise DocumentError(f"{path.name} doesn't look like a valid {suffix} file.") from None
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DocumentError(f"Couldn't read {path.name}: {exc}") from None
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise DocumentError(f"{path.name} has no readable text (a scanned document or an image?).")
    return text


def context(path: Path, text: str, limit: int, home: Path | None = None) -> list[dict[str, str]]:
    """The file as earlier chat turns, so the question stays short and the file is context."""
    home = home or Path.home()
    shown = (path.relative_to(home) if path.is_relative_to(home) else path).as_posix()
    cut = "" if len(text) <= limit else f"\n\n[The file continues; only the first {limit} characters are shown.]"
    return [{"role": "user", "content": f"Here is my file ~/{shown}:\n\n{text[:limit]}{cut}"},
            {"role": "assistant", "content": "I've read the file. What would you like to know?"}]
