"""One queue for all local model work (V3 M2).

On the OptiPlex (4 cores, AI on the CPU) Home, the chat model and the embedding model fight for the same
cores, and every overlap shows up as a slower first word. So everything that makes this computer's Ollama
work goes through one scheduler:

  * one job at a time, highest priority first: your live question > an approved plan step (and the
    warm-up) > background work (indexing notes, later summaries and routine detection);
  * a live question's own embedding runs inside the question's turn, so embeddings never run beside an
    answer;
  * background work starts only when the computer has been quiet for a moment (no question, no typing)
    and gives way between steps as soon as you type or ask;
  * a live question never waits long: if something is still running after LIVE_MAX_WAIT it goes ahead
    anyway (counted as an overlap), because a stuck job must not block you.

The gaming PC is not scheduled here: it has its own GPU and never competes with this computer's cores.
Home and the local API run in one process, so one process-wide SCHEDULER covers both; `apvisctl` runs on
its own and is not queued.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

LIVE, PLAN, BACKGROUND = 0, 1, 2
PRIORITY_NAMES = {LIVE: "live", PLAN: "plan", BACKGROUND: "background"}

IDLE_AFTER = 8.0        # background waits this long after the last question or keystroke
TYPING_HOLD = 6.0       # one keystroke keeps background work away this long
LIVE_MAX_WAIT = 2.5     # a live question never waits longer than this behind other work

# How long Ollama keeps each kind of model loaded (its per-request keep_alive). The fast and chat
# models stay resident (brain.keep_alive decides that), the embedding model stays while you are
# asking and leaves soon after background indexing, bigger local models load when needed.
EMBED_KEEP_LIVE = "30m"
EMBED_KEEP_BACKGROUND = "5m"
BIG_MODEL_KEEP = "10m"


class Cancelled(Exception):
    """The job was given up while it waited (a newer question replaced it, or indexing stopped)."""


@dataclass
class Job:
    priority: int
    what: str
    seq: int
    queued: float
    started: float | None = None

    def view(self, now: float) -> dict[str, Any]:
        out: dict[str, Any] = {"what": self.what, "priority": PRIORITY_NAMES.get(self.priority, str(self.priority))}
        if self.started is not None:
            out["running_s"] = round(now - self.started, 2)
        else:
            out["waiting_s"] = round(now - self.queued, 2)
        return out


@dataclass
class _Stats:
    jobs: Counter = field(default_factory=Counter)
    live_waits: deque = field(default_factory=lambda: deque(maxlen=50))
    overlaps: int = 0
    yields: int = 0


class ModelScheduler:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic, idle_after: float = IDLE_AFTER,
                 typing_hold: float = TYPING_HOLD, live_max_wait: float = LIVE_MAX_WAIT) -> None:
        self._clock = clock
        self.idle_after, self.typing_hold, self.live_max_wait = idle_after, typing_hold, live_max_wait
        self._cond = threading.Condition()
        self._running: list[Job] = []          # normally one; two only after a live overlap
        self._waiting: list[Job] = []
        self._seq = itertools.count()
        self._quiet_until = float("-inf")       # background may not start before this
        self._stats = _Stats()
        self._local = threading.local()

    # ---- hints from Home
    def owner_active(self, hold: float | None = None) -> None:
        """The owner is typing or asking: background work stops at its next step and stays away a while."""
        with self._cond:
            self._quiet_until = max(self._quiet_until, self._clock() + (self.typing_hold if hold is None else hold))
            self._cond.notify_all()

    # ---- the queue
    def _next(self) -> Job | None:
        return min(self._waiting, key=lambda j: (j.priority, j.seq)) if self._waiting else None

    def _may_start(self, job: Job) -> bool:
        if self._running or self._next() is not job:
            return False
        return job.priority != BACKGROUND or self._clock() >= self._quiet_until

    @contextmanager
    def slot(self, priority: int, what: str = "", *, cancelled: Callable[[], bool] = lambda: False) -> Iterator[Job]:
        """Hold this computer's models for one job. Re-entrant on the same thread (a question's own
        routing and embedding run inside its slot)."""
        outer = getattr(self._local, "job", None)
        if outer is not None:
            yield outer
            return
        now = self._clock()
        job = Job(priority, what or PRIORITY_NAMES.get(priority, "job"), next(self._seq), now)
        with self._cond:
            self._waiting.append(job)
            try:
                while not self._may_start(job):
                    if cancelled():
                        raise Cancelled(job.what)
                    waited = self._clock() - job.queued
                    if priority == LIVE and waited >= self.live_max_wait:
                        self._stats.overlaps += 1      # something overran: the owner goes ahead regardless
                        break
                    timeout = 0.25
                    if priority == LIVE:
                        timeout = min(timeout, max(0.01, self.live_max_wait - waited))
                    self._cond.wait(timeout)
            except BaseException:
                self._waiting.remove(job)
                self._cond.notify_all()
                raise
            self._waiting.remove(job)
            job.started = self._clock()
            self._running.append(job)
            self._stats.jobs[PRIORITY_NAMES.get(priority, str(priority))] += 1
            if priority == LIVE:
                self._stats.live_waits.append(job.started - job.queued)
        self._local.job = job
        try:
            yield job
        finally:
            self._local.job = None
            with self._cond:
                self._running.remove(job)
                if job.priority != BACKGROUND:
                    self._quiet_until = max(self._quiet_until, self._clock() + self.idle_after)
                self._cond.notify_all()

    def should_yield(self) -> bool:
        """Asked by background work between steps: is someone more important waiting, or is the owner busy?"""
        with self._cond:
            yielding = any(j.priority < BACKGROUND for j in self._waiting) or self._clock() < self._quiet_until
            if yielding and any(j.priority == BACKGROUND for j in self._running):
                self._stats.yields += 1
            return yielding

    def busy(self) -> bool:
        """A question or plan step is running or waiting."""
        with self._cond:
            return any(j.priority < BACKGROUND for j in self._running + self._waiting)

    def snapshot(self) -> dict[str, Any]:
        """What the queue is doing, for Settings, the Memory page and GET /v1/stats."""
        with self._cond:
            now = self._clock()
            running = [j.view(now) for j in self._running]
            waiting = [j.view(now) for j in sorted(self._waiting, key=lambda j: (j.priority, j.seq))]
            waits = list(self._stats.live_waits)
            quiet = max(0.0, self._quiet_until - now)
            state = running[0]["priority"] if running else ("waiting" if waiting else "idle")
            return {"state": state, "running": running, "waiting": waiting,
                    "background_held_s": round(quiet, 1) if quiet != float("inf") else None,
                    "jobs": dict(self._stats.jobs), "overlaps": self._stats.overlaps, "yields": self._stats.yields,
                    "live_wait_s": {"count": len(waits), "max": round(max(waits), 3) if waits else 0.0,
                                    "average": round(sum(waits) / len(waits), 3) if waits else 0.0}}


SCHEDULER = ModelScheduler()
