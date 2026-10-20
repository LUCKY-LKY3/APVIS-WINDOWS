"""Meaning-based search for the Vault (V3 M1): a local embedding index beside the Markdown notes.

The Vault's Markdown files stay the only source of truth. This index is a cache that can be deleted and
rebuilt at any time: one SQLite file with a vector per chunk of each note, made by a local embedding model
through Ollama (nomic-embed-text, all-minilm as fallback). Nothing leaves this computer.

Search is hybrid: the Vault's own keyword score and cosine similarity, merged per note, so exact names and
numbers still win and differently worded questions still find the note. Whenever the index or Ollama is
unavailable, search quietly falls back to keywords only.
"""

from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import threading
import time
from array import array
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from . import scheduler as sched
from .ollama import OllamaClient, OllamaError
from .vault import Note, Vault

PREFERRED = "nomic-embed-text"
FALLBACK = "all-minilm"
MODELS = (PREFERRED, FALLBACK)
EMBED_KEEP_ALIVE = sched.EMBED_KEEP_LIVE   # small (~0.3 GB); stays loaded while you ask, then frees RAM
QUERY_TIMEOUT = 1.5               # an Ask never waits longer than this for the query vector
CHUNK_CHARS = 800                 # all-minilm reads ~256 tokens; nomic more. One size keeps both honest.
BATCH = 4                         # chunks per /api/embed call while indexing (short steps yield sooner)
SCHEMA = 1

# How each model's cosine similarity maps to a 0..1 relevance: at or under `low` is "unrelated" (never
# passes), `high` is "clearly the same topic". scripts/measure-m1.py prints raw scores for tuning.
# Measured on the OptiPlex (2026-09-27): unrelated questions score 0.39-0.47 with nomic-embed-text, so
# anything under 0.55 counts as nothing; a note needs about 0.62 to reach RELEVANT.
CALIBRATION = {PREFERRED: (0.55, 0.75), FALLBACK: (0.30, 0.60)}
DEFAULT_CALIBRATION = (0.40, 0.75)
RELEVANT = 0.34                   # same bar the keyword search uses for "relevant enough to show"


def index_path() -> Path:
    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "memory" / "vault-index.sqlite"


def base_name(model: str) -> str:
    return model.removesuffix(":latest")


def pick_model(installed: Iterable[str]) -> str | None:
    """The embedding model to use: nomic-embed-text if installed, else all-minilm, else none."""
    names = {base_name(n) for n in installed}
    return next((m for m in MODELS if m in names), None)


def _prefix(model: str, kind: str) -> str:
    # nomic-embed-text is trained with task prefixes; without them its scores are much weaker.
    if base_name(model).startswith("nomic-embed-text"):
        return "search_query: " if kind == "query" else "search_document: "
    return ""


def chunks(note: Note, size: int = CHUNK_CHARS) -> list[str]:
    """The note split on paragraph boundaries, each chunk led by the note's title so it stands alone."""
    body = note.body.strip()
    heading = f"# {note.title}"
    if body.startswith(heading):
        body = body[len(heading):].strip()
    head = note.title + (f" (tags: {', '.join(note.tags)})" if note.tags else "")
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()] or [""]
    out, current = [], ""
    for para in paragraphs:
        while len(para) > size:                      # one very long paragraph: hard split
            if current:
                out.append(current)
                current = ""
            out.append(para[:size])
            para = para[size:]
        if current and len(current) + len(para) + 2 > size:
            out.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current or not out:
        out.append(current)
    return [f"{head}\n\n{c}".strip() for c in out]


def _normalise(vector: list[float]) -> array:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return array("f", (v / norm for v in vector))


_sumprod = getattr(math, "sumprod", None)      # Python 3.12+ (Debian 13 ships 3.13): C speed


def _dot(a: array, b: array) -> float:
    if _sumprod is not None:
        return _sumprod(a, b)
    return sum(x * y for x, y in zip(a, b))


def relevance(model: str, cosine: float) -> float:
    low, high = CALIBRATION.get(base_name(model), DEFAULT_CALIBRATION)
    return max(0.0, min(1.0, (cosine - low) / (high - low)))


@dataclass
class SyncResult:
    model: str
    notes: int = 0           # notes in the vault
    embedded: int = 0        # notes (re)embedded this time
    removed: int = 0
    chunks: int = 0          # chunks in the index afterwards
    seconds: float = 0.0
    stopped: bool = False    # paused because the owner started asking something

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# Vectors of each index file kept in memory between searches: {path: (generation, rows)}.
_CACHE: dict[str, tuple[int, list[tuple[str, array]]]] = {}
_CACHE_LOCK = threading.Lock()


@contextmanager
def _nothing():
    yield None


class SemanticIndex:
    def __init__(self, client: OllamaClient, model: str, path: Path | None = None) -> None:
        self.client, self.model, self.path = client, base_name(model), path or index_path()

    # ---- storage
    @contextmanager
    def _db(self):
        """One connection per use (Home, the API and the indexer run on different threads)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield self._prepare(db)
        finally:
            db.close()

    def _prepare(self, db: sqlite3.Connection) -> sqlite3.Connection:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notes (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, hash TEXT);
            CREATE TABLE IF NOT EXISTS chunks (path TEXT NOT NULL, n INTEGER NOT NULL, vec BLOB NOT NULL,
                                               PRIMARY KEY (path, n));
        """)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        return db

    @staticmethod
    def _meta(db: sqlite3.Connection, key: str) -> str | None:
        row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _bump(db: sqlite3.Connection) -> None:
        gen = int(SemanticIndex._meta(db, "generation") or 0) + 1
        db.execute("INSERT OR REPLACE INTO meta VALUES ('generation', ?)", (str(gen),))

    def _check_model(self, db: sqlite3.Connection) -> None:
        """Vectors from different models can't be compared: a model change empties the index."""
        if self._meta(db, "model") != self.model or self._meta(db, "schema") != str(SCHEMA):
            db.execute("DELETE FROM chunks")
            db.execute("DELETE FROM notes")
            db.execute("INSERT OR REPLACE INTO meta VALUES ('model', ?)", (self.model,))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (str(SCHEMA),))
            self._bump(db)

    def _embed(self, texts: list[str], kind: str, timeout: float | None = None,
               keep_alive: str | int = EMBED_KEEP_ALIVE) -> list[array]:
        prefix = _prefix(self.model, kind)
        vectors = self.client.embed(self.model, [prefix + t for t in texts], keep_alive=keep_alive, timeout=timeout)
        return [_normalise(v) for v in vectors]

    # ---- indexing
    def sync(self, vault: Vault, *, should_stop: Callable[[], bool] = lambda: False,
             scheduler: sched.ModelScheduler | None = None) -> SyncResult:
        """Bring the index in line with the vault: embed new and changed notes, drop removed ones.
        Stops between batches when should_stop() says the owner needs the CPU; the next sync resumes.
        With a scheduler, each note is embedded as background work: only when the computer is quiet,
        and never beside an answer."""
        start = time.perf_counter()
        result = SyncResult(self.model)
        notes = vault.notes()
        result.notes = len(notes)
        root = vault.root
        with self._db() as db:
            self._check_model(db)
            known = {row[0]: row[1:] for row in db.execute("SELECT path, mtime, size, hash FROM notes")}
            present = set()
            todo: list[tuple[str, float, int, str, list[str]]] = []
            for note in notes:
                path = Path(note.path)
                rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else note.path
                present.add(rel)
                try:
                    st = path.stat()
                except OSError:
                    continue
                old = known.get(rel)
                if old and old[0] == st.st_mtime and old[1] == st.st_size:
                    continue
                parts = chunks(note)
                digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
                if old and old[2] == digest:              # touched but unchanged: just record the new stat
                    db.execute("UPDATE notes SET mtime = ?, size = ? WHERE path = ?", (st.st_mtime, st.st_size, rel))
                    continue
                todo.append((rel, st.st_mtime, st.st_size, digest, parts))
            for rel in set(known) - present:
                db.execute("DELETE FROM chunks WHERE path = ?", (rel,))
                db.execute("DELETE FROM notes WHERE path = ?", (rel,))
                result.removed += 1
            if result.removed:
                self._bump(db)
            db.commit()
            stop = (lambda: should_stop() or scheduler.should_yield()) if scheduler else should_stop
            keep = sched.EMBED_KEEP_BACKGROUND if scheduler else EMBED_KEEP_ALIVE
            for rel, mtime, size, digest, parts in todo:
                if should_stop():
                    result.stopped = True
                    break
                vectors: list[array] = []
                try:
                    with (scheduler.slot(sched.BACKGROUND, "indexing notes", cancelled=should_stop)
                          if scheduler else _nothing()):
                        for i in range(0, len(parts), BATCH):
                            if i and stop():
                                break                      # the owner wants the CPU: this note is redone later
                            vectors += self._embed(parts[i:i + BATCH], "document", keep_alive=keep)
                except sched.Cancelled:
                    result.stopped = True
                    break
                if len(vectors) < len(parts):
                    result.stopped = True
                    break
                db.execute("DELETE FROM chunks WHERE path = ?", (rel,))
                db.executemany("INSERT INTO chunks VALUES (?, ?, ?)",
                               [(rel, n, sqlite3.Binary(v.tobytes())) for n, v in enumerate(vectors)])
                db.execute("INSERT OR REPLACE INTO notes VALUES (?, ?, ?, ?)", (rel, mtime, size, digest))
                self._bump(db)
                db.commit()
                result.embedded += 1
            result.chunks = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        result.seconds = round(time.perf_counter() - start, 2)
        return result

    def status(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"model": self.model, "notes": 0, "chunks": 0, "ready": False}
        with self._db() as db:
            model = self._meta(db, "model")
            notes = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"model": model or self.model, "notes": notes, "chunks": count, "ready": model == self.model and count > 0}

    def clear(self) -> None:
        """Delete the index file (the notes themselves are untouched)."""
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)
        with _CACHE_LOCK:
            _CACHE.pop(str(self.path), None)

    # ---- search
    def _rows(self) -> list[tuple[str, array]]:
        with self._db() as db:
            if self._meta(db, "model") != self.model:
                return []
            generation = int(self._meta(db, "generation") or 0)
            key = str(self.path)
            with _CACHE_LOCK:
                cached = _CACHE.get(key)
                if cached and cached[0] == generation:
                    return cached[1]
            rows = []
            for path, blob in db.execute("SELECT path, vec FROM chunks"):
                vec = array("f")
                vec.frombytes(blob)
                rows.append((path, vec))
        with _CACHE_LOCK:
            _CACHE[key] = (generation, rows)
        return rows

    def query(self, text: str, limit: int = 8, *, timeout: float | None = QUERY_TIMEOUT) -> list[tuple[float, str]]:
        """[(cosine, note path relative to the vault)], best chunk per note, best first."""
        rows = self._rows()
        if not rows or not text.strip():
            return []
        # The owner is waiting for this one: a live job (inside a question's own slot it simply runs).
        with sched.SCHEDULER.slot(sched.LIVE, "memory search"):
            (q,) = self._embed([text.strip()], "query", timeout=timeout)
        best: dict[str, float] = {}
        for path, vec in rows:
            if len(vec) != len(q):
                continue
            score = _dot(q, vec)
            if score > best.get(path, -2.0):
                best[path] = score
        return sorted(((s, p) for p, s in best.items()), reverse=True)[:limit]


def hybrid_search(vault: Vault, query: str, limit: int = 8, index: SemanticIndex | None = None,
                  info: dict[str, Any] | None = None) -> list[tuple[float, Note]]:
    """Keyword and meaning scores merged per note. Without an index (or if it fails) this is exactly
    Vault.search. `info` (optional) receives {"mode": "hybrid" | "keyword", "error": ...}."""
    keyword = vault.search(query, limit=max(limit, 8))
    info = info if info is not None else {}
    info["mode"] = "keyword"
    if index is None:
        return keyword[:limit]
    try:
        semantic = index.query(query, limit=max(limit, 8))
    except (OllamaError, OSError, sqlite3.Error, ValueError) as exc:
        info["error"] = str(exc)
        return keyword[:limit]
    info["mode"] = "hybrid"
    root = vault.root
    by_path: dict[str, Note] = {}
    scores: dict[str, list[float]] = {}
    for score, note in keyword:
        rel = Path(note.path).relative_to(root).as_posix() if Path(note.path).is_relative_to(root) else note.path
        by_path[rel] = note
        scores[rel] = [score, 0.0]
    missing = [p for _, p in semantic if p not in by_path]
    if missing:
        wanted = set(missing)
        for note in vault.notes():
            rel = Path(note.path).relative_to(root).as_posix() if Path(note.path).is_relative_to(root) else note.path
            if rel in wanted:
                by_path[rel] = note
    for cosine, rel in semantic:
        if rel in by_path:
            scores.setdefault(rel, [0.0, 0.0])[1] = relevance(index.model, cosine)
    # Notes whose keyword scores tie tell keywords nothing apart: for them, meaning decides. The keyword
    # part is dropped when at least one of the tied notes has a meaning score to decide with.
    ties: dict[float, list[str]] = {}
    for rel, (kw, _) in scores.items():
        if kw > 0:
            ties.setdefault(round(kw, 4), []).append(rel)
    for group in ties.values():
        if len(group) > 1 and any(scores[rel][1] > 0 for rel in group):
            for rel in group:
                scores[rel][0] = 0.0
    merged = []
    for rel, (kw, sem) in scores.items():
        score = max(kw, sem) + 0.2 * min(kw, sem)      # agreeing signals rank higher than either alone
        if score > 0:
            merged.append((round(score, 4), sem, by_path[rel]))
    merged.sort(key=lambda item: (-item[0], -item[1], item[2].title))
    return [(score, note) for score, _, note in merged[:limit]]


# The embedding model found per Ollama address, so an Ask doesn't ask Ollama for its model list every time.
# Only a found model is remembered (a model pulled a moment ago is seen at once), for MODEL_CACHE_S.
MODEL_CACHE_S = 60.0
_MODEL_CACHE: dict[str, tuple[float, str]] = {}


def index_for(config: Any, client: OllamaClient | None = None, installed: Iterable[str] | None = None) -> SemanticIndex | None:
    """The index Ask and the API should use, or None when meaning search is off or no embedding model is
    installed. `config` is an AskConfig."""
    if not getattr(config, "semantic_memory", False):
        return None
    client = client or OllamaClient(config.ollama_url, timeout=4)
    model = config.embed_model or None
    cached = _MODEL_CACHE.get(config.ollama_url)
    if installed is None and cached and time.monotonic() - cached[0] < MODEL_CACHE_S and (not model or base_name(model) == cached[1]):
        return SemanticIndex(client, cached[1])
    if installed is not None or not model:
        try:
            names = list(installed) if installed is not None else [m.name for m in client.models()]
        except OllamaError:
            return None
        chosen = pick_model(names)
        if model and base_name(model) in {base_name(n) for n in names}:
            chosen = base_name(model)
        model = chosen
    if not model:
        _MODEL_CACHE.pop(config.ollama_url, None)
        return None
    _MODEL_CACHE[config.ollama_url] = (time.monotonic(), base_name(model))
    return SemanticIndex(client, model)


def search(vault: Vault, query: str, limit: int = 8, info: dict[str, Any] | None = None) -> list[tuple[float, Note]]:
    """Vault search as the owner has set it up: hybrid when meaning search is on, keywords otherwise.
    For callers without an AskService (Home's recall, the API, the CLI)."""
    from .ask import AskConfig             # ask imports this module; import late to avoid a cycle
    try:
        index = index_for(AskConfig.load())
    except (OSError, ValueError):
        index = None
    return hybrid_search(vault, query, limit, index, info)


class Indexer:
    """Keeps the index current in the background inside Home: on request (a note was written or
    forgotten) and every few minutes (notes edited in another app). Never runs while `busy()` says the
    owner is waiting for an answer."""

    def __init__(self, make_index: Callable[[], SemanticIndex | None], vault: Callable[[], Vault],
                 busy: Callable[[], bool] = lambda: False, on_status: Callable[[dict[str, Any]], None] = lambda s: None,
                 every: float = 300.0, scheduler: sched.ModelScheduler | None = None) -> None:
        self._make_index, self._vault, self._busy, self._on_status, self._every = make_index, vault, busy, on_status, every
        self._scheduler = scheduler
        self._wake = threading.Event()
        self._stop = False
        self._thread: threading.Thread | None = None
        self.last: dict[str, Any] = {}

    def start(self) -> None:
        self._stop = False                         # a thread still winding down from stop() carries on
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="apvis-vault-index", daemon=True)
            self._thread.start()
        self.request()

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def request(self) -> None:
        self._wake.set()

    def run_once(self) -> dict[str, Any]:
        try:
            index = self._make_index()
        except (OllamaError, OSError, ValueError) as exc:
            index, status = None, {"state": "error", "message": str(exc)}
            self.last = status
            self._on_status(status)
            return status
        if index is None:
            status = {"state": "no-model", "message": "No embedding model available yet (is local AI running?)."}
        else:
            try:
                result = index.sync(self._vault(), should_stop=lambda: self._stop or self._busy(),
                                    scheduler=self._scheduler)
                status = {"state": "paused" if result.stopped else "ready", **result.to_dict()}
            except (OllamaError, OSError, sqlite3.Error, ValueError) as exc:
                status = {"state": "error", "model": index.model, "message": str(exc)}
        self.last = status
        self._on_status(status)
        return status

    def _loop(self) -> None:
        while not self._stop:
            self._wake.wait(self._every)
            self._wake.clear()
            if self._stop:
                return
            while self._busy() and not self._stop:
                time.sleep(2.0)
            if self._stop:
                return
            status = self.run_once()
            if status.get("state") == "paused":
                self._wake.set()                   # resume once the owner is done
