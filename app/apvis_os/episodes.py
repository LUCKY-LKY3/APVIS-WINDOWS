"""Episodes (V3 M4): one-line summaries of your Ask sessions, kept for 30 days. Off until you switch them on.

A session is the questions you ask Home with no more than SESSION_GAP between them. When a session ends, its
summary is written as background work in the model scheduler (only while the computer is quiet, giving way
as soon as you type), by the fast local model, in one short sentence. Without a model the summary is simply
the questions themselves. Nothing leaves this computer.

Privacy:
  * nothing is recorded while the switch is off, and a session in progress is dropped when it is switched off;
  * the raw questions and answers of a session are only held in memory until it is summarised; the stored
    episode keeps the summary and the questions (shortened), with credentials redacted;
  * episodes older than RETENTION_DAYS are deleted; every episode can be viewed and forgotten (Memory page).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .common import redact_sensitive
from . import scheduler as sched

RETENTION_DAYS = 30
SESSION_GAP = 600.0           # seconds without a question that end a session
MAX_TURNS = 12                # turns of one session given to the summary
QUESTION_CHARS = 120
ANSWER_CHARS = 200
SUMMARY_PROMPT = (
    "Summarise the conversation between the owner and APVIS in ONE sentence of at most 25 words, "
    "starting with a past-tense verb such as 'Asked about' or 'Worked on'. Mention the main topics. "
    "Reply with the sentence only."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(stamp: str) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def store_path() -> Path:
    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "memory" / "episodes.json"


@dataclass
class Turn:
    question: str
    answer: str
    at: float                     # time.time()


@dataclass
class Episode:
    episode_id: str
    started: str
    ended: str
    summary: str
    questions: list[str] = field(default_factory=list)
    turns: int = 0
    summarised_by: str = ""       # the model's name, or "" when the summary is the questions themselves

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EpisodeStore:
    """The episodes file (owner-only), oldest dropped after RETENTION_DAYS."""

    def __init__(self, path: Path | None = None, *, now: Callable[[], datetime] = _now) -> None:
        self.path = path or store_path()
        self._now = now
        self._lock = threading.Lock()

    def _load(self) -> list[Episode]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for item in data if isinstance(data, list) else []:
            try:
                out.append(Episode(**{k: item[k] for k in Episode.__dataclass_fields__ if k in item}))
            except TypeError:
                continue
        return out

    def _save(self, items: list[Episode]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".episodes.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump([e.to_dict() for e in items], handle, indent=1)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _fresh(self, items: list[Episode]) -> list[Episode]:
        cutoff = self._now() - timedelta(days=RETENTION_DAYS)
        return [e for e in items if (_parse(e.ended) or self._now()) >= cutoff]

    def list(self) -> list[Episode]:
        """Newest first; expired ones are deleted on the way."""
        with self._lock:
            items = self._load()
            fresh = self._fresh(items)
            if len(fresh) != len(items):
                self._save(fresh)
        return sorted(fresh, key=lambda e: e.ended, reverse=True)

    def add(self, episode: Episode) -> None:
        with self._lock:
            items = self._fresh(self._load())
            items.append(episode)
            self._save(items)

    def forget(self, episode_id: str) -> bool:
        with self._lock:
            items = self._load()
            kept = [e for e in items if e.episode_id != episode_id]
            if len(kept) == len(items):
                return False
            self._save(kept)
            return True

    def forget_all(self) -> int:
        with self._lock:
            count = len(self._load())
            self.path.unlink(missing_ok=True)
            return count

    def search(self, query: str, limit: int = 5) -> list[Episode]:
        """Episodes whose summary or questions share words with the query, best first."""
        words = {w for w in re.findall(r"[a-z0-9]{3,}", query.lower())}
        if not words:
            return []
        scored = []
        for e in self.list():
            text = set(re.findall(r"[a-z0-9]{3,}", (e.summary + " " + " ".join(e.questions)).lower()))
            hits = len(words & text)
            if hits:
                scored.append((hits, e.ended, e))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [e for _, _, e in scored[:limit]]


def plain_summary(turns: list[Turn]) -> str:
    """The summary without a model: what was asked."""
    asked = [t.question.strip().rstrip("?.!") for t in turns if t.question.strip()]
    if not asked:
        return ""
    text = "Asked: " + "; ".join(q[:60] for q in asked[:4])
    return text + (f" (and {len(asked) - 4} more)" if len(asked) > 4 else "") + "."


def clean_summary(text: str) -> str:
    """The model's reply as one tidy sentence (no preamble, quotes or second paragraph)."""
    text = re.sub(r"(?is)<think>.*?</think>", "", text or "").strip()
    text = re.sub(r"(?i)^(?:here(?:'s| is) (?:a |the )?summary[:.]?|summary[:.])\s*", "", text).strip()
    text = text.splitlines()[0].strip() if text else ""
    text = re.sub(r"^[A-Z][a-z]+(?: [a-z]+){0,2}:\s+(?=\S)", "", text)   # "Worked on: The owner ..." -> "The owner ..."
    text = text.strip(" \"'“”")
    if len(text) > 220:
        text = text[:217].rsplit(" ", 1)[0] + "…"
    return text


class EpisodeRecorder:
    """Groups Home's questions into sessions and turns finished sessions into episodes (background work)."""

    def __init__(self, store: EpisodeStore | None = None, *, enabled: Callable[[], bool],
                 chat: Callable[[list[dict[str, str]], Callable[[], bool]], tuple[str, str]] | None = None,
                 scheduler: sched.ModelScheduler | None = None, gap: float = SESSION_GAP,
                 clock: Callable[[], float] = time.time, on_change: Callable[[], None] = lambda: None) -> None:
        self.store = store or EpisodeStore()
        self._enabled, self._chat, self._gap, self._clock, self._on_change = enabled, chat, gap, clock, on_change
        self._scheduler = scheduler or sched.SCHEDULER
        self._lock = threading.Lock()
        self._current: list[Turn] = []
        self._pending: list[list[Turn]] = []
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._stop = False

    # ---- recording
    def add_turn(self, question: str, answer: str) -> None:
        if not self._enabled() or not question.strip():
            return
        now = self._clock()
        with self._lock:
            if self._current and now - self._current[-1].at > self._gap:
                self._pending.append(self._current)
                self._current = []
            self._current.append(Turn(redact_sensitive(question.strip()), redact_sensitive(answer.strip()), now))
        self._wake.set()

    def drop(self) -> None:
        """Switched off: forget the session in progress and anything not yet summarised."""
        with self._lock:
            self._current, self._pending = [], []

    def close_stale(self) -> None:
        with self._lock:
            if self._current and self._clock() - self._current[-1].at > self._gap:
                self._pending.append(self._current)
                self._current = []

    def flush(self) -> None:
        """End the current session now (Home is closing)."""
        with self._lock:
            if self._current:
                self._pending.append(self._current)
                self._current = []

    # ---- summarising
    def summarise_pending(self) -> int:
        """Write the finished sessions as episodes; returns how many. Model work runs as background work."""
        done = 0
        while True:
            with self._lock:
                if not self._pending or not self._enabled():
                    return done
                turns = self._pending[0]
            summary, model = "", ""
            if self._chat is not None:
                try:
                    with self._scheduler.slot(sched.BACKGROUND, "session summary", cancelled=lambda: self._stop):
                        summary, model = self._chat(self._messages(turns), self._scheduler.should_yield)
                except sched.Cancelled:
                    return done
                except Exception:  # noqa: BLE001 - fall back to the plain summary
                    summary, model = "", ""
                summary = clean_summary(summary)
            if not summary:
                summary, model = plain_summary(turns), ""
            episode = Episode(uuid.uuid4().hex[:12], _iso(datetime.fromtimestamp(turns[0].at, timezone.utc)),
                              _iso(datetime.fromtimestamp(turns[-1].at, timezone.utc)), summary,
                              [t.question[:QUESTION_CHARS] for t in turns[:8]], len(turns), model)
            with self._lock:
                if not self._pending or self._pending[0] is not turns or not self._enabled():
                    continue                      # dropped meanwhile
                self._pending.pop(0)
            self.store.add(episode)
            done += 1
            self._on_change()

    @staticmethod
    def _messages(turns: list[Turn]) -> list[dict[str, str]]:
        lines = []
        for t in turns[-MAX_TURNS:]:
            lines.append("Owner: " + t.question[:QUESTION_CHARS * 2])
            lines.append("APVIS: " + t.answer[:ANSWER_CHARS])
        return [{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": "\n".join(lines)}]

    # ---- the background thread inside Home
    def start(self) -> None:
        self._stop = False
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="apvis-episodes", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop:
            self._wake.wait(60.0)
            self._wake.clear()
            if self._stop:
                return
            self.close_stale()
            try:
                self.summarise_pending()
            except OSError:
                pass


def ollama_chat(client: Any, model: str, options: dict[str, Any], keep_alive: Any
                ) -> Callable[[list[dict[str, str]], Callable[[], bool]], tuple[str, str]]:
    """A summariser that runs `model` through Ollama, stopping if the scheduler asks it to give way."""
    def chat(messages: list[dict[str, str]], should_yield: Callable[[], bool]) -> tuple[str, str]:
        parts = []
        for text in client.chat_stream(model, messages, max_tokens=60, read_timeout=120.0, cancelled=should_yield,
                                       options=options, keep_alive=keep_alive):
            parts.append(text)
        if should_yield():
            raise sched.Cancelled("the owner needs the computer")
        return "".join(parts), model
    return chat


def recent_lines(store: EpisodeStore, limit: int = 2, now: datetime | None = None) -> list[str]:
    """The latest episodes as short lines for "what was I doing?"."""
    now = now or _now()
    out = []
    for e in store.list()[:limit]:
        when = _parse(e.ended)
        age = ""
        if when:
            minutes = int((now - when).total_seconds() // 60)
            age = f"{minutes} min ago" if minutes < 60 else f"{minutes // 60} h ago" if minutes < 48 * 60 else f"{minutes // 1440} days ago"
        out.append(e.summary.rstrip(".") + (f" ({age})" if age else ""))
    return out
