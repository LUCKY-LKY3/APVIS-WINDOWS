"""Continuity: answer "what was I doing?" from recorded local state, not a model.

Sources are the saved Focus, Mission Control records and vault notes. Nothing
is invented: when a source is empty the answer says so, and saved work is
never claimed to still be running.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_ASKS = re.compile(
    r"(?i)^\s*(?:hey\s+apvis[,\s]*)?(?:so\s+)?(?:"
    r"what\s+was\s+i\s+(?:doing|working\s+on|up\s+to)"
    r"|where\s+(?:was\s+i|did\s+i\s+(?:leave\s+off|stop))"
    r"|what\s+am\s+i\s+(?:doing|working\s+on)"
    r"|what\s+did\s+i\s+(?:do|work\s+on)\s+(?:today|recently|earlier|last(?:\s+time)?)"
    # A bare "catch me up" asks for the news (V4, owner); catching up on work stays here.
    r"|catch\s+me\s+up\s+on\s+(?:my\s+work|what\s+i\s+was\s+doing|where\s+i\s+was)"
    r"|resume(?:\s+where\s+i\s+(?:was|left\s+off))?"
    r")(?:\s+(?:today|now|please|earlier|yesterday))?\s*[?.!]*\s*$")

STATUS_WORDS = {
    "approval_required": "waiting for your approval",
    "running": "was running (not confirmed since)",
    "completed": "done",
    "failed": "did not complete",
    "cancelled": "cancelled",
}


def is_continuity_question(text: str) -> bool:
    return bool(_ASKS.match(text or ""))


def _ago(stamp: str, now: datetime) -> str:
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    minutes = int((now - when).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"
    return f"{minutes // 1440} days ago"


def continuity_answer(focus: dict[str, Any] | None, missions: list[dict[str, Any]],
                      notes: list[dict[str, Any]], now: datetime | None = None,
                      episodes: list[str] | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    lines: list[str] = []
    if focus and focus.get("label"):
        lines.append(f"Your Focus is “{focus['label']}”.")
    else:
        lines.append("No Focus is set.")
    waiting = [m for m in missions if m.get("status") == "approval_required"]
    recent = [m for m in missions if m.get("status") != "approval_required"][:3]
    if waiting:
        lines.append("Waiting for your approval: " + "; ".join(m.get("preview", "?") for m in waiting[:3]) + ".")
    if recent:
        parts = []
        for m in recent:
            age = _ago(str(m.get("updatedAt", "")), now)
            parts.append(f"{m.get('preview', '?')} — {STATUS_WORDS.get(m.get('status', ''), m.get('status', ''))}" + (f" ({age})" if age else ""))
        lines.append("Recent missions: " + "; ".join(parts) + ".")
    if not missions:
        lines.append("No missions recorded.")
    if notes:
        latest = notes[0]
        age = _ago(str(latest.get("updated", "")), now)
        lines.append(f"Last note saved: “{latest.get('title', '?')}”" + (f" ({age})" if age else "") + ".")
    else:
        lines.append("Your vault has no notes yet.")
    if episodes:                                   # V3 M4: only when session memory is switched on
        lines.append("Earlier sessions: " + "; ".join(episodes) + ".")
    return " ".join(lines)
