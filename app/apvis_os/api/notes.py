"""Notes endpoints: search the owner's vault, and propose a memory (the owner still has to accept it)."""

from __future__ import annotations

from .. import guest as guest_mode
from .. import semantic
from ..vault import MemoryInbox, SensitiveContent, Vault
from .server import ApiError, Request, route


@route("GET", "/v1/notes", "Search your APVIS Vault notes by words and, when switched on, by meaning (?q=words&limit=8)")
def notes(request: Request) -> None:
    query = (request.query.get("q") or "").strip()
    if not query:
        raise ApiError(400, "missing_query", "add ?q=words")
    try:
        limit = max(1, min(25, int(request.query.get("limit", "8"))))
    except ValueError:
        raise ApiError(400, "bad_limit", "limit is a number from 1 to 25") from None
    vault = Vault()
    root = vault.ensure()
    info: dict[str, object] = {}
    hits = semantic.search(vault, query, limit=limit, info=info)
    request.send(200, {"mode": info.get("mode", "keyword"),
                       "notes": [{"score": round(score, 3), **note.summary(root)} for score, note in hits]})


@route("POST", "/v1/notes/propose", "Suggest a memory; it waits in Memory > Inbox until you accept it",
       body='{"text": "...", "reason": "why it is worth keeping"}')
def propose(request: Request) -> None:
    if guest_mode.this_session_is_guest():               # V4: Guest keeps nothing
        raise ApiError(403, "guest", guest_mode.refusal("Memory"))
    text = request.text("text", limit=4000)
    reason = request.text("reason", required=False, limit=300)
    try:
        proposal = MemoryInbox().propose(text, reason=reason or "Suggested by a program through the APVIS API")
    except SensitiveContent as exc:
        raise ApiError(400, "sensitive", str(exc)) from None
    request.send(200, {"ok": True, "id": proposal.proposal_id, "status": "waiting for you in Memory > Inbox"})
