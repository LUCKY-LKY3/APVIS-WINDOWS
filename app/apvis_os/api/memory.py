"""Memory endpoints (V3 M2): what APVIS remembers, searched by words and meaning, and what the model queue is doing.

Read-only here: changing memory stays on the OptiPlex screen (Memory page) or goes through the Inbox
(POST /v1/notes/propose), where the owner accepts it.
"""

from __future__ import annotations

from collections import Counter

from .. import semantic
from ..scheduler import SCHEDULER
from ..vault import MemoryInbox, Vault
from .server import ApiError, Request, route


def _limit(request: Request, default: int, top: int) -> int:
    try:
        return max(1, min(top, int(request.query.get("limit", str(default)))))
    except ValueError:
        raise ApiError(400, "bad_limit", f"limit is a number from 1 to {top}") from None


def _meaning_status() -> dict[str, object]:
    from ..ask import AskConfig                 # ask imports semantic; import late like semantic.search does
    try:
        config = AskConfig.load()
    except (OSError, ValueError):
        return {"enabled": False}
    out: dict[str, object] = {"enabled": config.semantic_memory}
    if config.semantic_memory:
        index = semantic.index_for(config)
        if index is None:
            out["model"] = None
        else:
            try:
                out.update(index.status())
            except OSError:
                out["model"] = index.model
    return out


@route("GET", "/v1/memory", "What APVIS remembers: your notes (newest first, ?limit=50), counts, Inbox size, meaning-search status")
def memory(request: Request) -> None:
    limit = _limit(request, 50, 500)
    vault = Vault()
    root = vault.ensure()
    notes = vault.notes()
    request.send(200, {"count": len(notes), "kinds": dict(Counter(n.kind for n in notes)),
                       "inbox_waiting": len(MemoryInbox(vault).pending()),
                       "meaning_search": _meaning_status(),
                       "notes": [n.summary(root) for n in notes[:limit]]})


@route("GET", "/v1/memory/search", "Search memory by words and, when switched on, by meaning (?q=words&limit=8); best first")
def search(request: Request) -> None:
    query = (request.query.get("q") or "").strip()
    if not query:
        raise ApiError(400, "missing_query", "add ?q=words")
    limit = _limit(request, 8, 25)
    vault = Vault()
    root = vault.ensure()
    info: dict[str, object] = {}
    hits = semantic.search(vault, query[:300], limit=limit, info=info)
    request.send(200, {"mode": info.get("mode", "keyword"),
                       "notes": [{"score": round(score, 3), **note.summary(root)} for score, note in hits]})


@route("GET", "/v1/memory/episodes", "Session memory: one-line summaries of Ask sessions (last 30 days; only while switched on)")
def episodes(request: Request) -> None:
    from ..ask import AskConfig
    from ..episodes import EpisodeStore
    try:
        enabled = AskConfig.load().episodes
    except (OSError, ValueError):
        enabled = False
    query = (request.query.get("q") or "").strip()[:300]
    store = EpisodeStore()
    items = store.search(query, limit=_limit(request, 20, 60)) if query else store.list()[:_limit(request, 20, 60)]
    request.send(200, {"enabled": enabled, "episodes": [e.to_dict() for e in items]})


@route("GET", "/v1/queue", "The local model queue: what is running or waiting (answers first, background only when idle)")
def queue(request: Request) -> None:
    request.send(200, SCHEDULER.snapshot())
