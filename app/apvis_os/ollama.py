"""Bounded client for an Ollama server on this machine or the owner's own network.

Only loopback, private-LAN and link-local addresses (or single-label/.local/.lan
host names) count as local. Anything else is refused, so LOCAL ONLY can never
silently become an internet request.
"""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit

from .intelligence import CapabilityRequirement, ProviderCandidate, ProviderLocality
from .providers import ProviderRequest, ProviderResponse

DEFAULT_URL = "http://127.0.0.1:11434"
_LOCAL_SUFFIXES = (".local", ".lan", ".home", ".internal")


KEEP_ALIVE = "30m"
NUM_CTX = 2048

class OllamaError(RuntimeError):
    """Ollama is unreachable, refused the request, or answered malformed data."""


def local_url(url: str) -> str:
    """Return a normalised base URL, or raise if it is not on this machine/LAN."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Ollama URL is required")
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Ollama URL must be http(s)://host[:port]")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in {"", "/"}:
        raise ValueError("Ollama URL must not contain credentials, a path or a query")
    host = parts.hostname.lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not (host == "localhost" or "." not in host or host.endswith(_LOCAL_SUFFIXES)):
            raise ValueError("Ollama host is not on this machine or the local network") from None
    else:
        if not (address.is_loopback or address.is_private or address.is_link_local) or address.is_unspecified:
            raise ValueError("Ollama host is not on this machine or the local network")
    port = f":{parts.port}" if parts.port else ""
    bracketed = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{bracketed}{port}"


@dataclass(frozen=True)
class InstalledModel:
    name: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "size": self.size}


class OllamaClient:
    def __init__(self, url: str = DEFAULT_URL, *, timeout: float = 5.0) -> None:
        self.url = local_url(url)
        self.timeout = timeout

    def _open(self, path: str, body: dict[str, Any] | None, timeout: float):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - URL validated as local
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8", "replace")).get("error", "")
            except (ValueError, AttributeError, OSError):
                pass
            raise OllamaError(detail or f"Ollama returned HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise OllamaError(f"Ollama is not reachable at {self.url}") from exc

    def version(self) -> str:
        with self._open("/api/version", None, self.timeout) as response:
            return str(json.load(response).get("version", "unknown"))

    def pull(self, model: str, on_progress: Callable[[str, int, int], None] | None = None,
             cancelled: Callable[[], bool] = lambda: False) -> None:
        """Download a model through Ollama itself (no root needed); reports (status, done, total)."""
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*(:[a-z0-9._-]+)?", model):
            raise OllamaError("that is not a valid model name")
        with self._open("/api/pull", {"model": model, "stream": True}, 3600.0) as response:
            for raw in response:
                if cancelled():
                    return
                if not raw.strip():
                    continue
                try:
                    chunk = json.loads(raw)
                except ValueError:
                    raise OllamaError("Ollama sent a malformed progress line") from None
                if chunk.get("error"):
                    raise OllamaError(str(chunk["error"]))
                if on_progress:
                    on_progress(str(chunk.get("status", "")), int(chunk.get("completed") or 0), int(chunk.get("total") or 0))

    def preload(self, model: str, *, options: dict[str, Any] | None = None, keep_alive: str | int = KEEP_ALIVE) -> None:
        """Load a model into memory now (no prompt), so the first question is quick.

        Pass the same options the questions will use: different load settings make
        Ollama load the model again on the first question."""
        body = {"model": model, "keep_alive": keep_alive, "options": {"num_ctx": NUM_CTX, **(options or {})}}
        with self._open("/api/generate", body, 180.0) as response:
            response.read()

    def running(self) -> list[dict[str, Any]]:
        """Ollama's /api/ps entries (name, size, size_vram: the part on the GPU, ...)."""
        with self._open("/api/ps", None, self.timeout) as response:
            payload = json.load(response)
        return [m for m in payload.get("models", []) if isinstance(m, dict)]

    def loaded(self) -> list[str]:
        """Models Ollama holds in memory right now (/api/ps)."""
        return [str(m.get("name") or m.get("model")) for m in self.running() if m.get("name") or m.get("model")]

    def unload(self, model: str) -> None:
        """Free a loaded model's memory now (keep_alive 0, no prompt)."""
        with self._open("/api/generate", {"model": model, "keep_alive": 0}, self.timeout) as response:
            response.read()

    def embed(self, model: str, texts: list[str], *, keep_alive: str | int = KEEP_ALIVE,
              timeout: float | None = None) -> list[list[float]]:
        """Embedding vectors from a local embedding model (/api/embed)."""
        with self._open("/api/embed", {"model": model, "input": texts, "keep_alive": keep_alive},
                        timeout if timeout is not None else 120.0) as response:
            payload = json.load(response)
        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise OllamaError("Ollama sent no embeddings")
        return vectors

    def models(self) -> list[InstalledModel]:
        with self._open("/api/tags", None, self.timeout) as response:
            payload = json.load(response)
        return sorted(
            (InstalledModel(str(m["name"]), int(m.get("size", 0))) for m in payload.get("models", []) if m.get("name")),
            key=lambda m: m.name,
        )

    def chat_stream(self, model: str, messages: list[dict[str, str]], *, max_tokens: int = 1024,
                    read_timeout: float = 300.0, cancelled: Callable[[], bool] = lambda: False,
                    options: dict[str, Any] | None = None, keep_alive: str | int = KEEP_ALIVE,
                    stats: dict[str, Any] | None = None, fmt: dict[str, Any] | str | None = None) -> Iterator[str]:
        """Yield answer text as the model writes it. Cold model loads can take a while.

        Reasoning is never shown: Ollama's separate "thinking" field is ignored and
        inline <think>…</think> blocks are dropped. "think": false is not sent,
        because Ollama 0.32 then leaks a thinking model's reasoning into the answer.
        """
        # Stay loaded between questions (a cold load costs seconds on the OptiPlex) and
        # keep the context small so the CPU starts writing sooner.
        body = {"model": model, "messages": messages, "stream": True, "keep_alive": keep_alive,
                "options": {"num_ctx": NUM_CTX, **(options or {}), "num_predict": max_tokens}}
        if fmt is not None:              # structured output: "json" or a JSON schema the reply must follow
            body["format"] = fmt
        inside_think = False
        with self._open("/api/chat", body, read_timeout) as response:
            for raw in response:
                if cancelled():
                    return
                if not raw.strip():
                    continue
                try:
                    chunk = json.loads(raw)
                except ValueError:
                    raise OllamaError("Ollama sent a malformed stream line") from None
                if chunk.get("error"):
                    raise OllamaError(str(chunk["error"]))
                text = (chunk.get("message") or {}).get("content", "")
                visible = []
                while text:
                    if inside_think:
                        end = text.find("</think>")
                        if end < 0:
                            break
                        text, inside_think = text[end + len("</think>"):], False
                    else:
                        start = text.find("<think>")
                        if start < 0:
                            visible.append(text)
                            break
                        visible.append(text[:start])
                        text, inside_think = text[start + len("<think>"):], True
                if "".join(visible):
                    yield "".join(visible)
                if chunk.get("done"):
                    if stats is not None:     # Ollama's own timing: tokens written and how long it took
                        stats.update({k: chunk[k] for k in ("eval_count", "eval_duration", "prompt_eval_count",
                                                            "prompt_eval_duration", "load_duration") if k in chunk})
                    return
        raise OllamaError("Ollama stream ended before the answer finished")


class OllamaAdapter:
    """ProviderAdapter for the Intelligence Fabric registry (always a LOCAL candidate)."""

    def __init__(self, client: OllamaClient, model: str, *, available: bool = True) -> None:
        self.client = client
        self.model = model
        self._candidate = ProviderCandidate(
            f"ollama:{model}", ProviderLocality.LOCAL,
            frozenset({CapabilityRequirement.GENERAL, CapabilityRequirement.FAST,
                       CapabilityRequirement.LOCAL, CapabilityRequirement.CODE}),
            available,
        )

    @property
    def candidate(self) -> ProviderCandidate:
        return self._candidate

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        messages = [{"role": "user", "content": request.prompt}]
        try:
            text = "".join(self.client.chat_stream(self.model, messages, max_tokens=request.max_output_tokens))
        except OllamaError as exc:
            return ProviderResponse(self._candidate.provider_id, request.request_id, "failed", error=str(exc))
        return ProviderResponse(self._candidate.provider_id, request.request_id, "completed", text=text,
                                evidence=[{"model": self.model, "endpoint": self.client.url}])
