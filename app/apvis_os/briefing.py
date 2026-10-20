"""News catch-up for Ask (V4): "catch me up", "what's the news", "what's happening", "any tech news".

A short spoken-style briefing from the newest BBC headlines (world and technology by default; science
when asked), each with its link. Headlines Home already fetched (the Atlas news layer) are reused; the
others are fetched with short timeouts and reused for 15 minutes. Nothing about the owner is sent: these
are plain public feed downloads. When the fast model is slow or unreachable the headlines are shown on
their own, and a feed that is down is named as down.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable

from . import osint

TOPICS = ("world", "tech", "science")
SECTION = {"world": "World", "tech": "Tech", "science": "Science"}
PER_TOPIC = 3
MAX_AGE_S = 15 * 60
FEED_TIMEOUT_S = 4.0
SUMMARY_TOKENS = 140

_TOPIC = r"(?:(?:the\s+)?(?:latest\s+|top\s+)?(?:world|tech|technology|science|international|global)\s+)?"
_NEWS = re.compile(
    r"(?i)^\s*(?:(?:hey|ok|okay|so)\s+)?(?:apvis[,:]?\s+)?(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:"
    r"catch\s+me\s+up(?:\s+on\s+" + _TOPIC + r"(?:the\s+)?(?:news|headlines|world|tech|technology|science))?"
    r"|(?:what'?s|whats|what\s+is|what\s+are)\s+(?:the\s+)?(?:latest\s+|top\s+)?" + _TOPIC + r"(?:news|headlines)(?:\s+today)?"
    r"|what'?s\s+(?:been\s+)?(?:happening|going\s+on)(?:\s+(?:in\s+the\s+world|in\s+tech|today|right\s+now|lately))?"
    r"|(?:is\s+there\s+)?(?:any|anything)\s+(?:new\s+(?:in\s+)?)?" + _TOPIC + r"(?:news|headlines)(?:\s+today)?"
    r"|(?:give|tell|read|show)\s+me\s+(?:the\s+)?(?:latest\s+|top\s+)?" + _TOPIC + r"(?:news|headlines)"
    r"|" + _TOPIC + r"(?:the\s+)?(?:latest\s+)?(?:news|headlines)(?:\s+(?:today|please|now))?"
    r"|update\s+me(?:\s+on\s+(?:the\s+)?news)?|brief\s+me|(?:morning|daily|news)\s+briefing"
    r")\s*[?.!]*\s*$")


def topics_for(question: str) -> tuple[str, ...] | None:
    """The news topics a catch-up question asks for; None when it isn't one."""
    if not _NEWS.match(question or ""):
        return None
    low = question.lower()
    asked = tuple(t for t, words in (("world", ("world", "international", "global")), ("tech", ("tech",)),
                                    ("science", ("science",))) if any(w in low for w in words))
    return asked or ("world", "tech")


def gather(topics: tuple[str, ...], fetch: Callable[[str], bytes] | None = None,
           max_age: float = MAX_AGE_S) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """({topic: newest headlines}, [sources that could not be reached]); feeds are fetched at the same time."""
    fetch = fetch or (lambda url: osint._fetch(url, timeout=FEED_TIMEOUT_S))

    def one(topic: str) -> tuple[str, list[dict[str, Any]] | None]:
        rows = osint.recent_headlines(topic, max_age)
        if rows is None:
            try:
                rows = osint.fetch_bbc(fetch, topic)
            except Exception:                         # network, HTTP or a feed APVIS cannot read
                return topic, None
        return topic, rows[:PER_TOPIC]

    with ThreadPoolExecutor(max_workers=max(1, len(topics))) as pool:
        found = list(pool.map(one, topics))
    groups = {topic: rows for topic, rows in found if rows}
    errors = [osint.BBC_FEEDS[topic][0] for topic, rows in found if rows is None]
    return groups, errors


def listing(groups: dict[str, list[dict[str, Any]]], errors: list[str]) -> str:
    """The headlines with their links, grouped by topic (shown under the spoken summary, or alone)."""
    parts = []
    for topic in TOPICS:
        if groups.get(topic):
            parts.append(SECTION[topic] + "\n" + "\n".join(f"• {r['title']} — {r['url']}" for r in groups[topic]))
    if errors:
        parts.append(("Couldn't reach " + " or ".join(errors) + " just now."))
    return "\n\n".join(parts)


def summary_prompt(groups: dict[str, list[dict[str, Any]]], now: datetime | None = None) -> str:
    now = now or datetime.now()
    lines = [f"{SECTION[t]}: " + "; ".join(r["title"] for r in groups[t]) for t in TOPICS if groups.get(t)]
    return (f"Today's top headlines ({now.strftime('%A')} {now.day} {now.strftime('%B')}):\n" + "\n".join(lines)
            + "\n\nCatch the owner up in two or three short spoken sentences, using only these headlines. "
              "Add no facts, numbers or names that are not in them."
            + "\nQuestion: What's the news?")


def unavailable(errors: list[str]) -> str:
    return ("I couldn't reach the news feeds just now (" + ", ".join(errors) + "). "
            "Check the internet connection, or try again in a minute.")
