"""AI endpoints: the same brain as Home's Ask (instant, remembered, gaming PC, tuned local models)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any
from uuid import uuid4

from .. import brain
from ..ask import ROLES, AskConfig, AskService, resolve_model
from ..ollama import OllamaClient, OllamaError
from ..scheduler import PLAN, SCHEDULER
from .server import STATS, ApiError, Request, route


@route("GET", "/v1/health", "What would answer right now: instant answers, this computer, the gaming PC")
def health(request: Request) -> None:
    config = AskConfig.load()
    out: dict[str, Any] = {"instant": True, "answer_length": config.answer_length,
                           "boost": {"configured": bool(config.boost_url), "enabled": config.boost_enabled}}
    try:
        installed = OllamaClient(config.ollama_url, timeout=3).models()
        out["local"] = {"reachable": True, "roles": {r: resolve_model(r, config.roles, installed) for r in ROLES}}
    except OllamaError as exc:
        out["local"] = {"reachable": False, "error": str(exc)}
    if config.boost_enabled and config.boost_url:
        state = brain.BOOST.get(config.boost_url)
        out["boost"].update({"reachable": bool(state.get("reachable")),
                             "roles": {r: brain.pick_boost_model(r, state.get("models", [])) for r in ROLES}})
    request.send(200, out)


@route("GET", "/v1/models", "OpenAI-style model list; \"apvis\" picks the best model automatically")
def models(request: Request) -> None:
    names = ["apvis"]
    try:
        names += [m.name for m in OllamaClient(AskConfig.load().ollama_url, timeout=3).models()]
    except (OllamaError, ValueError):
        pass
    request.send(200, {"object": "list", "data": [{"id": n, "object": "model", "owned_by": "apvis"} for n in names]})


def _options(request: Request) -> tuple[str | None, str | None, bool]:
    data = request.json()
    model = data.get("model")
    model = model if isinstance(model, str) and model not in {"", "apvis", "auto"} else None
    role = data.get("role") if data.get("role") in ROLES else None
    return model, role, data.get("stream") is True


@route("POST", "/v1/ask", "Ask APVIS; add \"stream\": true for NDJSON lines as it writes",
       body='{"question": "...", "stream": false, "role": "fast|general|code|deep|chat", "model": "optional", '
            '"history": [{"role": "user|assistant", "content": "..."}]}')
def ask(request: Request) -> None:
    question = request.text("question")
    history = request.json().get("history") or []
    if not isinstance(history, list):
        raise ApiError(400, "bad_history", "history is a list of {role, content}")
    model, role, stream = _options(request)
    _answer(request, question, [m for m in history if isinstance(m, dict)], model, role, stream, openai=False)


@route("POST", "/v1/chat/completions", "OpenAI-compatible chat (works with OpenAI client libraries); streaming supported",
       body='{"model": "apvis", "messages": [{"role": "user", "content": "..."}], "stream": false}')
def chat_completions(request: Request) -> None:
    messages = [m for m in request.json().get("messages") or [] if isinstance(m, dict) and isinstance(m.get("content"), str)]
    if not messages or messages[-1].get("role") != "user":
        raise ApiError(400, "bad_messages", "the last message must be from the user")
    model, role, stream = _options(request)
    history = [m for m in messages[:-1] if m.get("role") in {"user", "assistant"}]
    _answer(request, messages[-1]["content"], history, model, role, stream, openai=True)


@route("POST", "/v1/embeddings", "OpenAI-compatible embeddings from a local embedding model (e.g. nomic-embed-text)",
       body='{"model": "nomic-embed-text", "input": "text or [texts]"}')
def embeddings(request: Request) -> None:
    data = request.json()
    texts = data.get("input")
    texts = [texts] if isinstance(texts, str) else texts
    if not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts) or len(texts) > 256:
        raise ApiError(400, "bad_input", "input is a string or a list of up to 256 strings")
    config = AskConfig.load()
    client = OllamaClient(config.ollama_url, timeout=5)
    try:
        installed = [m.name for m in client.models()]
    except OllamaError as exc:
        raise ApiError(503, "ollama_down", str(exc)) from None
    wanted = data.get("model") if isinstance(data.get("model"), str) else ""
    choices = [wanted] if wanted else ["nomic-embed-text", "mxbai-embed-large", "all-minilm", "bge-m3"]
    have = {n.removesuffix(":latest"): n for n in installed}
    model = next((have[c.removesuffix(":latest")] for c in choices if c.removesuffix(":latest") in have), None)
    if model is None:
        raise ApiError(503, "no_embedding_model", "no embedding model installed; run: ollama pull nomic-embed-text")
    try:
        with SCHEDULER.slot(PLAN, "api embeddings"):      # a program's batch: after the owner's questions
            vectors = client.embed(model, texts)
    except OllamaError as exc:
        raise ApiError(502, "ollama_error", str(exc)) from None
    request.send(200, {"object": "list", "model": model,
                       "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]})


def _answer(request: Request, question: str, history: list[dict[str, str]], model: str | None, role: str | None,
            stream: bool, openai: bool) -> None:
    chat_id, created = "apvis-" + uuid4().hex[:12], int(time.time())
    gone = threading.Event()
    sent = [""]

    def emit(delta: str, finish: str | None = None, meta: dict[str, Any] | None = None) -> None:
        if openai:
            payload = {"id": chat_id, "object": "chat.completion.chunk", "created": created, "model": (meta or {}).get("model") or "apvis",
                       "choices": [{"index": 0, "delta": {"content": delta} if delta else {}, "finish_reason": finish}]}
            ok = request.write(b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n")
        else:
            ok = request.write(json.dumps({"text": delta, **(meta or {})}).encode("utf-8") + b"\n")
        if not ok:
            gone.set()                      # the caller hung up: stop the model

    def on_text(text: str) -> None:
        if stream and text.startswith(sent[0]) and len(text) > len(sent[0]):
            emit(text[len(sent[0]):])
            sent[0] = text

    if stream:
        request.start_stream("text/event-stream" if openai else "application/x-ndjson")
    try:
        result = AskService().ask(question, role=role, model=model, history=history, on_text=on_text, cancelled=gone.is_set)
    except (ValueError, OSError) as exc:
        if not stream:
            raise ApiError(400, "bad_question", str(exc)) from None
        emit("", "error", {"error": str(exc), "done": True})
        return
    STATS.answered(result.source, result.first_token_s)
    meta = {"model": result.model or "", "source": result.source, "role": result.role, "first_token_s": result.first_token_s,
            "total_s": result.total_s, "tokens_per_s": result.tokens_per_s}
    if result.status != "completed":
        meta["error"] = result.error or result.status
    if stream:
        if result.status == "completed" and result.answer.startswith(sent[0]) and len(result.answer) > len(sent[0]):
            emit(result.answer[len(sent[0]):])
        if openai:
            emit("", "stop" if result.status == "completed" else "error", meta)
            request.write(b"data: [DONE]\n\n")
        else:
            request.write(json.dumps({"done": True, "answer": result.answer, **meta}).encode("utf-8") + b"\n")
        return
    if result.status != "completed":
        raise ApiError(503 if result.status == "unavailable" else 500, result.status, meta["error"])
    if openai:
        request.send(200, {"id": chat_id, "object": "chat.completion", "created": created, "model": result.model or "apvis",
                           "choices": [{"index": 0, "message": {"role": "assistant", "content": result.answer}, "finish_reason": "stop"}],
                           "apvis": meta})
    else:
        request.send(200, {"answer": result.answer, **meta})
