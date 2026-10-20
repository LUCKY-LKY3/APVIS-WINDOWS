"""HTTP plumbing for the APVIS API: one route table, one set of safety checks, one error shape.

Every endpoint lives in its own module (ai, home, system, apps, notes) and registers with
@route. Safety for every request, before any route runs:
  - loopback only (the server never binds anything else);
  - the Host header must be 127.0.0.1/localhost with our port (stops DNS-rebinding pages);
  - no Origin header (browser pages always send one, so web pages can't use the API);
  - request bodies must be JSON objects of at most 256 KB.
Errors always look like {"error": {"code": "...", "message": "..."}}.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 256 * 1024

Handler = Callable[["Request"], None]


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    summary: str
    handler: Handler
    body: str = ""                      # what to send, for the index at /v1


ROUTES: dict[tuple[str, str], Route] = {}


def route(method: str, path: str, summary: str, body: str = "") -> Callable[[Handler], Handler]:
    """Register one endpoint; the summary shows in GET /v1 so the API documents itself."""
    def register(handler: Handler) -> Handler:
        ROUTES[(method, path)] = Route(method, path, summary, handler, body)
        return handler
    return register


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class Stats:
    """Counters since the API started (GET /v1/stats)."""
    started: float = field(default_factory=time.time)
    requests: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    answers: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def count(self, key: str) -> None:
        with self.lock:
            self.requests[key] += 1

    def answered(self, source: str, seconds: float | None) -> None:
        if seconds is None:
            return
        with self.lock:
            self.answers[source] = (self.answers[source] + [seconds])[-200:]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"uptime_s": round(time.time() - self.started), "requests": dict(self.requests),
                    "first_words_s": {k: {"count": len(v), "average": round(sum(v) / len(v), 3), "best": round(min(v), 3)}
                                      for k, v in self.answers.items() if v}}


STATS = Stats()


class Request:
    """What a route sees: the parsed request and helpers to answer it."""

    def __init__(self, raw: "RawHandler", method: str) -> None:
        self.raw, self.method = raw, method
        parts = urlsplit(raw.path)
        self.path = parts.path.rstrip("/") or "/"
        self.query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
        self._body: dict[str, Any] | None = None
        self.streaming = False

    def json(self) -> dict[str, Any]:
        if self._body is not None:
            return self._body
        if (self.raw.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            raise ApiError(415, "json_required", "send JSON (Content-Type: application/json)")
        try:
            length = int(self.raw.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length > MAX_BODY:
            raise ApiError(413, "too_large", f"bodies are limited to {MAX_BODY // 1024} KB")
        if length <= 0:
            raise ApiError(400, "empty_body", "send a JSON object")
        try:
            data = json.loads(self.raw.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "bad_json", "that is not valid JSON") from None
        if not isinstance(data, dict):
            raise ApiError(400, "bad_json", "send a JSON object")
        self._body = data
        return data

    def text(self, key: str, *, required: bool = True, limit: int = 4000) -> str:
        value = self.json().get(key)
        if value is None and not required:
            return ""
        if not isinstance(value, str) or not value.strip():
            raise ApiError(400, "missing_field", f"{key} is required")
        if len(value) > limit:
            raise ApiError(400, "too_long", f"{key} is limited to {limit} characters")
        return value.strip()

    def send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.raw.send_response(status)
        self.raw.send_header("Content-Type", "application/json")
        self.raw.send_header("Content-Length", str(len(body)))
        if self.raw.close_connection:
            self.raw.send_header("Connection", "close")
        self.raw.end_headers()
        self.raw.wfile.write(body)

    def fail(self, status: int, code: str, message: str) -> None:
        """Error reply. A body the route never read is drained first, then the connection closes,
        so the caller always gets the error instead of a reset connection."""
        if self._body is None:
            try:
                length = int(self.raw.headers.get("Content-Length") or 0)
                if 0 < length <= MAX_BODY:
                    self.raw.rfile.read(length)
            except (ValueError, OSError):
                pass
        self.raw.close_connection = True
        try:
            self.send(status, {"error": {"code": code, "message": message}})
        except OSError:
            pass

    def start_stream(self, content_type: str) -> None:
        self.streaming = True
        self.raw.send_response(200)
        self.raw.send_header("Content-Type", content_type)
        self.raw.send_header("Cache-Control", "no-cache")
        self.raw.send_header("Connection", "close")
        self.raw.end_headers()
        self.raw.close_connection = True

    def write(self, chunk: bytes) -> bool:
        """Stream a chunk; False once the caller has hung up."""
        try:
            self.raw.wfile.write(chunk)
            self.raw.wfile.flush()
            return True
        except OSError:
            return False


class RawHandler(BaseHTTPRequestHandler):
    server_version = "APVIS-API/2"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:     # noqa: A002 - questions stay out of logs
        pass

    def _dispatch(self, method: str) -> None:
        request = Request(self, method)
        try:
            host = (self.headers.get("Host") or "").lower()
            port = self.server.server_address[1]
            if host not in {f"127.0.0.1:{port}", f"localhost:{port}"} or self.headers.get("Origin"):
                raise ApiError(403, "local_only", "the APVIS API only answers programs on this computer")
            found = ROUTES.get((method, request.path))
            if found is None:
                known = any(path == request.path for _, path in ROUTES)
                raise ApiError(405 if known else 404, "method_not_allowed" if known else "not_found",
                               "wrong method for this endpoint" if known else "unknown endpoint; GET /v1 lists them all")
            STATS.count(f"{method} {request.path}")
            found.handler(request)
        except ApiError as exc:
            if not request.streaming:
                request.fail(exc.status, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - one broken route must never take the API down
            if not request.streaming:
                request.fail(500, "internal", f"{type(exc).__name__}: {exc}")

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")


@route("GET", "/v1", "Every endpoint, what it does and what to send")
def index(request: Request) -> None:
    request.send(200, {"api": "APVIS API", "version": 2, "base": f"http://{HOST}:{request.raw.server.server_address[1]}",
                       "local_only": True,
                       "endpoints": [{"method": r.method, "path": r.path, "summary": r.summary, **({"body": r.body} if r.body else {})}
                                     for r in sorted(ROUTES.values(), key=lambda r: (r.path, r.method))]})


@route("GET", "/v1/stats", "Requests served and how fast answers started, by source")
def stats(request: Request) -> None:
    request.send(200, STATS.snapshot())


def serve(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("the APVIS API only listens on this computer")
    server = ThreadingHTTPServer((host, port), RawHandler)
    server.daemon_threads = True
    return server


def start_background(port: int = PORT) -> ThreadingHTTPServer | None:
    """Home runs the API while it is open; None when something else already serves the port."""
    try:
        server = serve(HOST, port)
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, name="apvis-api", daemon=True).start()
    return server
