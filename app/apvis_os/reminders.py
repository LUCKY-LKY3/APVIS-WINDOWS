"""Reminders and timers, understood from plain words and kept on this computer.

    "remind me in 20 minutes to check the oven"     "set a timer for 5 minutes"
    "remind me at 18:30 to call mum"                "in an hour remind me to stretch"
    "what are my reminders"                         "cancel my reminders"

Home checks every few seconds and shows a notification when one is due. Nothing leaves
this computer and no model is involved, so the times are exactly what the owner said.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

_UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
          "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10, "fifteen": 15, "twenty": 20,
          "thirty": 30, "forty": 40, "forty-five": 45, "sixty": 60, "half an": 0.5, "half a": 0.5}
_NUM = r"(\d+(?:\.\d+)?|half an|half a|an|a|one|two|three|four|five|ten|fifteen|twenty|thirty|forty-five|forty|sixty)"
_UNIT = r"(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)"
_LEAD = r"^\s*(?:(?:hey|ok|okay)\s+)?(?:apvis[,:]?\s+)?(?:please\s+|can you\s+|could you\s+)?"
_END = r"\s*(?:please)?\s*[.!?]*\s*$"
MAX_AHEAD = timedelta(days=7)


def _amount(word: str) -> float:
    return float(word) if re.fullmatch(r"\d+(?:\.\d+)?", word) else float(_WORDS[word])


def _clock_time(hour: int, minute: int, meridiem: str | None, now: datetime) -> datetime | None:
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem.lower().startswith("p") else 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return when if when > now else when + timedelta(days=1)


def parse(text: str, now: datetime | None = None) -> tuple[str, datetime, str] | None:
    """(what to say, when, "reminder"|"timer") for a reminder or timer request; None for anything else."""
    now = now or datetime.now()
    t = (text or "").strip()
    m = re.match(_LEAD + r"(?:set|start)\s+(?:a|an|the)?\s*timer\s+(?:for\s+)?" + _NUM + r"\s*" + _UNIT + _END, t, re.I) or \
        re.match(_LEAD + r"(?:a\s+)?" + _NUM + r"\s*" + _UNIT + r"\s+timer" + _END, t, re.I)
    if m:
        seconds = _amount(m.group(1).lower()) * _UNITS[m.group(2).lower()]
        if not 1 <= seconds <= MAX_AHEAD.total_seconds():
            return None
        label = f"{m.group(1)} {m.group(2)}".replace("half an ", "half an ").strip()
        return f"Timer done ({label})", now + timedelta(seconds=seconds), "timer"
    # "remind me in 20 minutes to X" / "remind me to X in 20 minutes" / "in 20 minutes remind me to X"
    patterns = (
        _LEAD + r"remind\s+me\s+in\s+" + _NUM + r"\s*" + _UNIT + r"(?:\s+(?:to|that|about)\s+(?P<what>.+?))?" + _END,
        _LEAD + r"remind\s+me\s+(?:to|that|about)\s+(?P<what>.+?)\s+in\s+" + _NUM + r"\s*" + _UNIT + _END,
        _LEAD + r"in\s+" + _NUM + r"\s*" + _UNIT + r",?\s+remind\s+me\s+(?:to|that|about)\s+(?P<what>.+?)" + _END,
    )
    for i, pattern in enumerate(patterns):
        m = re.match(pattern, t, re.I)
        if m:
            groups = [g for g in m.groups() if g is not None and g != m.group("what")]
            amount, unit = groups[0].lower(), groups[1].lower()
            seconds = _amount(amount) * _UNITS[unit]
            if not 1 <= seconds <= MAX_AHEAD.total_seconds():
                return None
            return (m.group("what") or "Reminder").strip(), now + timedelta(seconds=seconds), "reminder"
    # "remind me at 18:30 to X" / "remind me to X at 6pm"
    at = r"at\s+(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"
    for pattern in (_LEAD + r"remind\s+me\s+" + at + r"(?:\s+(?:to|that|about)\s+(?P<what>.+?))?" + _END,
                    _LEAD + r"remind\s+me\s+(?:to|that|about)\s+(?P<what>.+?)\s+" + at + _END):
        m = re.match(pattern, t, re.I)
        if m:
            nums = [g for g in m.groups() if g is not None and g != m.group("what")]
            hour = int(nums[0])
            minute = int(nums[1]) if len(nums) > 1 and nums[1].isdigit() else 0
            meridiem = next((g for g in nums[1:] if not g.isdigit()), None)
            when = _clock_time(hour, minute, meridiem, now)
            if when is None:
                return None
            return (m.group("what") or "Reminder").strip(), when, "reminder"
    return None


def is_list_request(text: str) -> bool:
    return bool(re.match(_LEAD + r"(?:what|which|show|list|any)\s+(?:are\s+)?(?:my\s+)?(?:reminders|timers)(?:\s+(?:are\s+)?(?:set|left|coming up))?" + _END, text or "", re.I)
                or re.match(_LEAD + r"(?:do\s+i\s+have\s+any|have\s+i\s+got\s+any)\s+(?:reminders|timers)" + _END, text or "", re.I))


def is_cancel_request(text: str) -> bool:
    return bool(re.match(_LEAD + r"(?:cancel|clear|delete|remove|stop)\s+(?:all\s+)?(?:my\s+|the\s+)?(?:reminders?|timers?)" + _END, text or "", re.I))


def describe(when: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now()
    seconds = (when - now).total_seconds()
    clock = when.strftime("%H:%M") if when.date() == now.date() else when.strftime("%a %H:%M")
    if seconds < 90:
        return f"in {max(1, round(seconds))} seconds"
    if seconds < 3600:
        return f"in {round(seconds / 60)} minutes ({clock})"
    return f"at {clock}"


@dataclass
class Reminder:
    id: str
    text: str
    due: float                 # epoch seconds
    kind: str                  # reminder | timer
    created: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Reminders:
    def __init__(self, path: Path | None = None, clock: Callable[[], float] = time.time) -> None:
        self.path = path or Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "reminders.json"
        self._clock = clock
        self._lock = threading.Lock()

    def _load(self) -> list[Reminder]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for item in data if isinstance(data, list) else []:
            try:
                out.append(Reminder(str(item["id"]), str(item["text"])[:300], float(item["due"]), str(item.get("kind", "reminder")),
                                    float(item.get("created", 0))))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def _save(self, items: list[Reminder]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps([r.to_dict() for r in items]), encoding="utf-8")
        os.replace(tmp, self.path)

    def add(self, text: str, due: datetime, kind: str = "reminder") -> Reminder:
        with self._lock:
            items = self._load()
            if len(items) >= 50:
                raise ValueError("That's 50 reminders already. Cancel some first.")
            item = Reminder(uuid4().hex[:10], text.strip()[:300] or "Reminder", due.timestamp(), kind, self._clock())
            self._save(items + [item])
            return item

    def pending(self) -> list[Reminder]:
        with self._lock:
            return sorted(self._load(), key=lambda r: r.due)

    def due_now(self) -> list[Reminder]:
        """Reminders whose time has come; they are removed as they are handed out."""
        now = self._clock()
        with self._lock:
            items = self._load()
            due = [r for r in items if r.due <= now]
            if due:
                self._save([r for r in items if r.due > now])
            return sorted(due, key=lambda r: r.due)

    def cancel_all(self) -> int:
        with self._lock:
            count = len(self._load())
            if count:
                self._save([])
            return count


def answer(text: str, store: Reminders | None = None, now: datetime | None = None) -> str | None:
    """Handle a reminder/timer sentence completely; None when the text is not about reminders."""
    now = now or datetime.now()
    store = store or Reminders()
    if is_list_request(text):
        items = store.pending()
        if not items:
            return "You have no reminders or timers set."
        lines = [f"• {r.text} — {describe(datetime.fromtimestamp(r.due), now)}" for r in items[:8]]
        more = f"\n…and {len(items) - 8} more." if len(items) > 8 else ""
        return f"You have {len(items)} set:\n" + "\n".join(lines) + more
    if is_cancel_request(text):
        count = store.cancel_all()
        return f"Cancelled {count} reminder{'s' if count != 1 else ''}." if count else "There were no reminders to cancel."
    parsed = parse(text, now)
    if parsed is None:
        return None
    what, when, kind = parsed
    store.add(what, when, kind)
    if kind == "timer":
        return f"Timer set. I'll let you know {describe(when, now)}."
    return f"Okay, I'll remind you {describe(when, now)}: {what}."
