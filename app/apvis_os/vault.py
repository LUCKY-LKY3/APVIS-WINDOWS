"""The APVIS Vault and Memory Inbox: human-readable memory the owner controls.

The vault is a plain folder of Markdown notes (Obsidian-compatible, YAML front
matter) that stays useful without APVIS. Nothing is written into it silently:
"remember …" creates an Inbox proposal showing its source, sensitivity and any
similar notes, and only an explicit Accept turns it into a note. Credentials
are refused outright. Decisions keep their reasons and what they replace.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .common import redact_sensitive, utc_now
from .trash import move_to_trash

KINDS = {"note": "Notes", "decision": "Decisions", "research": "Research"}
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{1,31}")
_STOP = set("the a an and or of to in on for is are was were be it this that with at by from as i my me you your we our".split())
_REMEMBER = re.compile(r"(?i)^\s*(?:(?:hey\s+)?apvis[,:]?\s+)?(?:please\s+)?(?:remember|note|save a note)(?:\s+that)?[:,]?\s+(.+?)\s*$")
_RECALL = re.compile(r"(?i)^\s*(?:what do you (?:remember|know) about|search my notes for|find (?:my )?notes? (?:about|on)|what did i (?:say|note) about)\s+(.+?)\s*[?.!]*$")
_DECISION = re.compile(r"(?i)^\s*(?:we|i)\s+decided\s+(?:to\s+|that\s+)?(.+?)(?:\s+because\s+(.+?))?\s*[.!]*$")


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def slug(title: str) -> str:
    base = re.sub(r"[^A-Za-z0-9 ._-]+", "", title).strip(" .")
    base = re.sub(r"\s+", " ", base)[:60].strip()
    return base or "Untitled"


def _frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(json.dumps(v) for v in value)}]")
        elif value is None:
            continue
        else:
            lines.append(f"{key}: {json.dumps(value)}")
    return "\n".join(lines + ["---", ""])


def _parse_note(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    meta: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip()
        try:
            meta[key.strip()] = json.loads(value) if not value.startswith("[") else json.loads(value)
        except ValueError:
            meta[key.strip()] = value
    return meta, text[end + 4:].lstrip("\n")


@dataclass
class Note:
    path: str
    title: str
    kind: str
    body: str
    tags: list[str]
    created: str
    updated: str
    source: str

    def summary(self, root: Path) -> dict[str, Any]:
        rel = Path(self.path).relative_to(root).as_posix() if Path(self.path).is_relative_to(root) else self.path
        first = next((line.strip() for line in self.body.splitlines() if line.strip() and not line.startswith("#")), "")
        if first.rstrip(".!?") == self.title.rstrip(".!?"):
            first = ""  # a short note's text is already its title
        return {"path": rel, "title": self.title, "kind": self.kind, "tags": self.tags, "updated": self.updated,
                "source": self.source, "excerpt": first[:200]}


class Vault:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path.home() / "APVIS Vault").resolve()

    def ensure(self) -> Path:
        for folder in KINDS.values():
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        readme = self.root / "README.md"
        if not readme.exists():
            readme.write_text("# APVIS Vault\n\nYour notes, decisions and research conclusions as plain Markdown.\n"
                              "APVIS only adds notes you accept from the Memory Inbox. You can edit, move or delete\n"
                              "anything here with any editor (Obsidian works too).\n", encoding="utf-8")
        return self.root

    def notes(self) -> list[Note]:
        found = []
        if not self.root.is_dir():
            return found
        for path in sorted(self.root.rglob("*.md")):
            if path.name == "README.md" or any(part.startswith(".") for part in path.relative_to(self.root).parts):
                continue
            try:
                meta, body = _parse_note(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            kind = meta.get("kind") or next((k for k, folder in KINDS.items() if folder == path.parent.name), "note")
            found.append(Note(str(path), str(meta.get("title") or path.stem), str(kind), body,
                              [str(t) for t in meta.get("tags", []) if isinstance(t, str)] if isinstance(meta.get("tags"), list) else [],
                              str(meta.get("created") or ""), str(meta.get("updated") or ""), str(meta.get("source") or "")))
        found.sort(key=lambda n: n.updated, reverse=True)
        return found

    def search(self, query: str, limit: int = 8) -> list[tuple[float, Note]]:
        """Keyword score per note, 0..~2: a title match counts 3, a tag 2, the body 1, each weighted by how
        rare the word is in this vault (BM25-style IDF), so a word most notes contain (say "apvis") counts
        for little and can't tie every note. Question words no note contains weigh like the rarest word,
        so with no common words the scores match the V2 ones."""
        wanted = words(query)
        if not wanted:
            return []
        notes = [(note, words(note.title), words(note.body), {t.lower() for t in note.tags}) for note in self.notes()]
        n = len(notes)
        df = {w: sum(1 for _, title, body, tags in notes if w in title or w in body or w in tags) for w in wanted}
        idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items() if d}
        rarest = math.log(1 + (n - 0.5) / 1.5) if n else 1.0       # the weight of a word only one note has
        weight = {w: idf.get(w, rarest) for w in wanted}
        total = 3 * sum(weight.values()) or 1.0
        scored = []
        for note, title, body, tags in notes:
            score = sum(weight[w] * (3 * (w in title) + 2 * (w in tags) + (w in body)) for w in wanted)
            if score > 0:
                scored.append((round(score / total, 4), note))
        scored.sort(key=lambda item: (-item[0], item[1].title))
        return scored[:limit]

    def write(self, title: str, body: str, *, kind: str = "note", tags: list[str] | None = None,
              source: str = "owner", extra: dict[str, Any] | None = None) -> Path:
        if kind not in KINDS:
            raise ValueError(f"unknown note kind {kind!r}")
        self.ensure()
        folder = self.root / KINDS[kind]
        name, n = slug(title), 1
        path = folder / f"{name}.md"
        while path.exists():
            n += 1
            path = folder / f"{name} {n}.md"
        now = utc_now()
        meta = {"title": title, "kind": kind, "tags": tags or [], "created": now, "updated": now, "source": source,
                **(extra or {})}
        _atomic(path, _frontmatter(meta) + f"# {title}\n\n{body.strip()}\n")
        return path


    def forget(self, rel_path: str, home: Path | None = None) -> Path:
        """Forget one memory: its Markdown file goes to the Trash (restorable), never deleted."""
        path = (self.root / rel_path).resolve()
        if not path.is_relative_to(self.root) or path.suffix != ".md" or not path.is_file():
            raise ValueError("that memory is not in your vault")
        return move_to_trash(path, home)


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class SensitiveContent(ValueError):
    """The text looks like a credential; APVIS will not store it."""


@dataclass
class Proposal:
    proposal_id: str
    text: str
    kind: str                    # note | decision
    title: str
    reason: str = ""             # for decisions: why
    source: str = "you asked APVIS to remember this"
    asked: str = ""
    sensitivity: str = "private"
    similar: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"      # pending | accepted | rejected
    created: str = field(default_factory=utc_now)
    decided: str | None = None
    note_path: str | None = None


def _title_from(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return (first[:57] + "…") if len(first) > 58 else first.rstrip(".!?")


class MemoryInbox:
    """Proposed memories wait here until the owner accepts or rejects them."""

    def __init__(self, vault: Vault | None = None, path: Path | None = None) -> None:
        self.vault = vault or Vault()
        self.path = path or Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "memory-inbox.json"

    def _load(self) -> list[Proposal]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        return [Proposal(**item) for item in raw if isinstance(item, dict)]

    def _save(self, items: list[Proposal]) -> None:
        _atomic(self.path, json.dumps([asdict(p) for p in items[-200:]], indent=2) + "\n")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def propose(self, text: str, *, kind: str = "note", reason: str = "", asked: str = "") -> Proposal:
        text = text.strip()
        if not text:
            raise ValueError("nothing to remember")
        if redact_sensitive(text) != text:
            raise SensitiveContent("That looks like a password, key or token. APVIS won't store credentials; "
                                   "use a password manager for those.")
        similar = [{"title": n.title, "path": n.summary(self.vault.root)["path"], "score": round(score, 2)}
                   for score, n in self.vault.search(text, limit=3) if score >= 0.34]
        proposal = Proposal(uuid4().hex[:12], text, kind, _title_from(text), reason=reason, asked=asked or text,
                            similar=similar)
        items = self._load()
        items.append(proposal)
        self._save(items)
        return proposal

    def pending(self) -> list[Proposal]:
        return [p for p in self._load() if p.status == "pending"]

    def _decide(self, proposal_id: str, status: str, edited_text: str | None = None) -> Proposal:
        items = self._load()
        for proposal in items:
            if proposal.proposal_id == proposal_id:
                if proposal.status != "pending":
                    raise ValueError(f"this proposal was already {proposal.status}")
                proposal.status, proposal.decided = status, utc_now()
                if status == "accepted":
                    text = (edited_text or proposal.text).strip()
                    if redact_sensitive(text) != text:
                        raise SensitiveContent("That looks like a credential; not stored.")
                    body = text
                    extra: dict[str, Any] = {}
                    if proposal.kind == "decision":
                        body = f"**Decision:** {text}\n\n**Why:** {proposal.reason or '(no reason given yet)'}\n"
                        extra = {"status": "current"}
                    if proposal.similar:
                        body += "\n\nRelated: " + ", ".join(f"[[{s['title']}]]" for s in proposal.similar) + "\n"
                    path = self.vault.write(proposal.title, body, kind=proposal.kind,
                                            source=f"Memory Inbox, accepted {proposal.decided[:10]}", extra=extra)
                    proposal.note_path = str(path)
                self._save(items)
                return proposal
        raise KeyError(f"no proposal {proposal_id}")

    def accept(self, proposal_id: str, edited_text: str | None = None) -> Proposal:
        return self._decide(proposal_id, "accepted", edited_text)

    def reject(self, proposal_id: str) -> Proposal:
        return self._decide(proposal_id, "rejected")


def parse_memory_request(text: str) -> tuple[str, dict[str, str]] | None:
    """('remember', {text}) | ('decision', {text, reason}) | ('recall', {query}) | None."""
    m = _RECALL.match(text)
    if m:
        return "recall", {"query": m.group(1)}
    m = _DECISION.match(text)
    if m:
        return "decision", {"text": m.group(1).rstrip("."), "reason": (m.group(2) or "").rstrip(".")}
    m = _REMEMBER.match(text)
    if m:
        return "remember", {"text": m.group(1)}
    return None


CONTEXT_MIN_SCORE = 0.34    # a note must score at least this to be shown to the model
CONTEXT_SECOND = 0.90       # one note by default; a second only if it scores this share of the best one


def snippet(note: Note, limit: int = 200) -> str:
    """The note's text without its heading, on one line, cut at a word boundary."""
    body = note.body.strip()
    if body.startswith(f"# {note.title}"):
        body = body[len(note.title) + 2:]
    text = " ".join(body.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def notes_context(vault: Vault, question: str, limit: int = 2, max_chars: int = 200,
                  search: Callable[..., list[tuple[float, Note]]] | None = None) -> tuple[str, list[str]]:
    """The best clearly relevant note for a local model (a second one only when it is nearly as good),
    each a short snippet (every extra character is prompt the CPU has to read before the first word),
    and their titles for the answer's label.
    `search` defaults to the keyword search; Ask passes the hybrid one when meaning search is on."""
    hits = [(score, note) for score, note in (search or vault.search)(question, limit=limit) if score >= CONTEXT_MIN_SCORE]
    if not hits:
        return "", []
    best = max(score for score, _ in hits)
    parts, used = [], []
    for score, note in hits[:limit]:
        if used and score < best * CONTEXT_SECOND:
            continue
        text = snippet(note, max_chars) or note.title
        parts.append(f"Note \"{note.title}\" ({note.updated[:10] or 'undated'}): {text}")
        used.append(note.title)
    return "\n".join(parts), used
