"""The APVIS brain: fast answers tuned for the OptiPlex 9020M (i5-4590T, 4 cores, AI on the CPU).

Fastest first:
1. Instant answers: greetings, thanks, the time and date, simple sums. No model, under 1 ms.
2. Remembered answers: the same timeless question asked again comes from a small local cache.
3. Gaming PC boost: when the owner's gaming PC (GTX 1080 Ti) is on and runs Ollama, bigger
   models answer on its GPU. Its state is checked in the background, so when it is off
   nothing waits for it and the OptiPlex answers as usual.
4. Local Ollama tuned for the CPU: the same load settings everywhere (a change would make
   Ollama reload the model), physical-core threads, capped answer lengths, the fast model
   kept loaded, and a warm-up that runs the real system prompt so Ollama's prompt cache
   already holds it and only the question itself is processed.
"""

from __future__ import annotations

import ast
import json
import operator
import os
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .ollama import InstalledModel, OllamaClient, OllamaError, local_url
from .scheduler import BIG_MODEL_KEEP

# ---------------------------------------------------------------- 1. instant answers
_TAIL = r"(?:\s+(?:there|apvis|mate|bro|bruh|dude|man|buddy|pal|again))*\s*[!.?,:)]*\s*$"
_GREET = re.compile(r"(?i)^\s*(?:hi+|hello+|hey+|hiya|yo+|sup|howdy|hola|heya|greetings|good\s+(?:morning|afternoon|evening|day)|"
                    r"what'?s\s+up|wh?assup|morning|evening)" + _TAIL)
_THANKS = re.compile(r"(?i)^\s*(?:thanks?(?:\s+(?:you|u))?|thx|ty|cheers|ta|much\s+appreciated|appreciate\s+it)"
                     r"(?:\s+(?:so|very)\s+much|\s+a\s+lot|\s+loads)?" + _TAIL)
_NICE = re.compile(r"(?i)^\s*(?:nice(?:\s+one)?|great|cool|awesome|perfect|sweet|good\s+job|well\s+done|ok(?:ay)?|k|alright|got\s+it)" + _TAIL)
_BYE = re.compile(r"(?i)^\s*(?:bye+|good\s*bye|see\s+(?:you|ya)(?:\s+later)?|later|cya|good\s*night|night(?:\s+night)?|gn)" + _TAIL)
_HOW = re.compile(r"(?i)^\s*(?:how\s+(?:are|r)\s+(?:you|u)(?:\s+doing)?|how'?s\s+it\s+going|how\s+are\s+things|you\s+good|you\s+ok(?:ay)?)" + _TAIL)
_WHO = re.compile(r"(?i)^\s*(?:who\s+are\s+you|what\s+are\s+you|what\s+is\s+apvis|what'?s\s+apvis|who\s+made\s+you|"
                  r"what\s+can\s+you\s+do|what\s+do\s+you\s+do|help)" + _TAIL)
_TIME = re.compile(r"(?i)^\s*(?:what(?:'s|\s+is)\s+the\s+time|what\s+time\s+is\s+it|time|the\s+time|current\s+time)(?:\s+(?:now|please|rn))?" + _TAIL)
_DATE = re.compile(r"(?i)^\s*(?:what(?:'s|\s+is)\s+(?:the\s+|today'?s\s+)?date(?:\s+today)?|what\s+day\s+is\s+(?:it|today)|"
                   r"what(?:'s|\s+is)\s+today|today'?s\s+date|date|the\s+date)(?:\s+(?:now|please))?" + _TAIL)
_SUM = re.compile(r"(?i)^\s*(?:what(?:'s|\s+is)\s+|calculate\s+|calc\s+|compute\s+|work\s+out\s+)?"
                  r"([-+*/x×÷^%().\d\s,]+?)\s*(?:=|\?)*\s*$")
_OPS: dict[type, Callable[..., Any]] = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                                        ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
                                        ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 64 or abs(left) > 1e6):
            raise ValueError("too big")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("not a sum")


# Dates and sayings written like fractions ("what is 9/11", "24/7"): a question about them, not a division.
_NOT_SUMS = {"9/11", "24/7", "50/50", "20/20", "4/20", "7/11"}


def calculate(text: str) -> str | None:
    """A plain sum typed as a question ("what's 12*7", "2^10") -> its result; anything else -> None."""
    match = _SUM.match(text or "")
    if not match or match.group(1).replace(" ", "") in _NOT_SUMS:
        return None
    expr = match.group(1).replace(",", "").replace("×", "*").replace("x", "*").replace("÷", "/").replace("^", "**").strip()
    if not re.search(r"\d", expr) or not re.search(r"\d\s*(?:\*\*|[-+*/%])\s*[-+(.\d]", expr):
        return None                                # a bare number is not a sum
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, TypeError, RecursionError):
        return None
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        value = round(value, 10)
        if value == int(value) and abs(value) < 1e15:
            value = int(value)
    shown = f"{value:,}" if isinstance(value, int) else f"{value:,.10g}"
    return f"{match.group(1).strip()} = {shown}"


def _part_of_day(now: datetime) -> str:
    return "morning" if 5 <= now.hour < 12 else "afternoon" if 12 <= now.hour < 18 else "evening"


def instant_answer(question: str, name: str = "", now: datetime | None = None) -> str | None:
    """Everyday lines APVIS answers itself, straight away; None when a model should answer."""
    q = (question or "").strip()
    if not q or len(q) > 80:
        return None
    now = now or datetime.now()
    who = f", {name}" if name else ""
    if _GREET.match(q):
        return f"Good {_part_of_day(now)}{who}. What can I do for you?"
    if _HOW.match(q):
        return "All systems running smoothly. What do you need?"
    if _THANKS.match(q):
        return f"Any time{who}."
    if _NICE.match(q):
        return "👍 Anything else?"
    if _BYE.match(q):
        return f"See you later{who}." if now.hour < 21 else f"Good night{who}."
    if _WHO.match(q):
        return ("I'm APVIS, the assistant built into this computer. I answer questions with local AI models (and your gaming PC "
                "when it's on), check how this computer is doing, keep your notes, and plan actions that you approve first.")
    if _TIME.match(q):
        return f"It's {now.strftime('%H:%M')}."
    if _DATE.match(q):
        return f"It's {now.strftime('%A')} {now.day} {now.strftime('%B %Y')}."
    return calculate(q)


# ---------------------------------------------------------------- 2. remembered answers
_NOT_TIMELESS = re.compile(r"(?i)\b(my|mine|me|i|i'm|im|this|here|today|tonight|tomorrow|yesterday|now|current|currently|latest|recent|"
                           r"news|weather|price|stock|score|time|date|week|month|year|computer|pc|you|your|joke|random|story|poem)\b")


def cache_key(question: str) -> str:
    """Case, spacing and end punctuation never matter; symbols that change the meaning do: "C#" is not "C",
    ".NET" is not "NET" (V4: such questions used to share one remembered answer)."""
    text = re.sub(r"[^\w\s+*/=#.%&-]", "", (question or "").lower())
    text = re.sub(r"\.(?=\s|$)", "", text)          # a full stop ends a sentence; ".net" keeps its dot
    return re.sub(r"\s+", " ", text).strip()


class AnswerCache:
    """Answers to timeless questions (facts, definitions, how-tos), kept for a day, bounded, owner-only file."""

    def __init__(self, path: Path, *, ttl: float = 24 * 3600, limit: int = 300, clock: Callable[[], float] = time.time) -> None:
        self.path, self.ttl, self.limit, self._clock = path, ttl, limit, clock
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] | None = None

    @staticmethod
    def cacheable(question: str) -> bool:
        from .websearch import is_time_sensitive
        return 3 <= len(question) <= 300 and not _NOT_TIMELESS.search(question) and not is_time_sensitive(question)

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._items is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._items = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._items = {}
        return self._items

    def get(self, question: str) -> dict[str, Any] | None:
        if not self.cacheable(question):
            return None                                  # also drops entries saved under older, looser rules
        with self._lock:
            item = self._load().get(cache_key(question))
            if not item or self._clock() - float(item.get("at", 0)) > self.ttl:
                return None
            return item

    def put(self, question: str, answer: str, model: str) -> None:
        from .websearch import sounds_unsure
        if not self.cacheable(question) or not answer.strip() or sounds_unsure(answer):
            return                                       # an "I'm not sure" must not come back for a day
        with self._lock:
            items = self._load()
            items[cache_key(question)] = {"answer": answer, "model": model, "at": self._clock()}
            if len(items) > self.limit:
                for key in sorted(items, key=lambda k: items[k].get("at", 0))[: len(items) - self.limit]:
                    del items[key]
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_name(self.path.name + ".tmp")
                tmp.write_text(json.dumps(items), encoding="utf-8")
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
            except OSError:
                pass


# ---------------------------------------------------------------- 3. gaming PC boost
# Tried in order on the gaming PC (11 GB GPU): the first installed one per role answers.
BOOST_ROLES: dict[str, list[str]] = {
    "fast": ["llama3.1:8b", "qwen2.5:7b", "gemma3:12b", "llama3.2:3b", "llama3.2:1b"],
    "general": ["qwen2.5:14b", "gemma3:12b", "llama3.1:8b", "qwen2.5:7b", "llama3.2:3b"],
    "code": ["qwen2.5-coder:14b", "qwen2.5-coder:7b", "llama3.1:8b", "qwen2.5-coder:1.5b"],
    "deep": ["qwen3:14b", "qwen3:8b", "deepseek-r1:14b", "deepseek-r1:8b", "qwen2.5:14b", "llama3.1:8b"],
    "chat": ["llama3.1:8b", "qwen2.5:7b", "llama3.2:3b", "llama3.2:1b"],
    "vision": ["qwen2.5vl:7b", "gemma3:12b", "llama3.2-vision", "llava:13b", "llava:7b", "gemma3:4b", "moondream"],
}
BOOST_FRESH_S = 45.0          # a background check at most this old is trusted without waiting
BOOST_PROBE_TIMEOUT = 0.6


class BoostState:
    """What the gaming PC's Ollama looked like at the last check (shared by Home and the API)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {}

    def check(self, url: str) -> dict[str, Any]:
        """Probe now (short timeout); an unreachable PC costs well under a second."""
        state: dict[str, Any] = {"url": url, "checked": self._clock()}
        try:
            client = OllamaClient(url, timeout=BOOST_PROBE_TIMEOUT)
            state["models"] = [m.name for m in client.models()]
            state["reachable"] = True
        except (OllamaError, ValueError, OSError) as exc:
            state["reachable"], state["models"], state["error"] = False, [], str(exc)
        with self._lock:
            self._state = state
        return state

    def get(self, url: str, *, max_age: float = BOOST_FRESH_S) -> dict[str, Any]:
        with self._lock:
            state = dict(self._state)
        if state.get("url") == url and self._clock() - state.get("checked", -1e9) <= max_age:
            return state
        return self.check(url)

    def mark_down(self, url: str, reason: str) -> None:
        with self._lock:
            self._state = {"url": url, "checked": self._clock(), "reachable": False, "models": [], "error": reason}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {k: v for k, v in self._state.items() if k != "checked"}


BOOST = BoostState()


def pick_boost_model(role: str, installed: list[str]) -> str | None:
    have = {name.removesuffix(":latest"): name for name in installed}
    for candidate_role in ((role,) if role == "vision" else (role, "fast", "general")):
        for wanted in BOOST_ROLES.get(candidate_role, []):
            if wanted in have:
                return have[wanted]
    return None


def wake_on_lan(mac: str, *, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Send the standard Wake-on-LAN magic packet to the gaming PC's network card."""
    digits = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(digits) != 12:
        raise ValueError("a MAC address looks like 1C:1B:0D:12:34:56")
    packet = b"\xff" * 6 + bytes.fromhex(digits) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))


def _own_lan_address() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))          # no packet is sent; this only picks the outgoing interface
            return sock.getsockname()[0]
    except OSError:
        return None


def find_ollama_on_lan(port: int = 11434, *, timeout: float = 0.35) -> list[str]:
    """Look for Ollama servers on this home network (the /24 this computer is on), e.g. the gaming PC."""
    mine = _own_lan_address()
    if not mine or mine.startswith("127."):
        return []
    try:
        local_url(f"http://{mine}")
    except ValueError:
        return []                                   # not a private network: never scan
    prefix = mine.rsplit(".", 1)[0]

    def probe(host: str) -> str | None:
        if host == mine:
            return None
        try:
            with socket.create_connection((host, port), timeout=timeout):
                pass
        except OSError:
            return None
        try:
            OllamaClient(f"http://{host}:{port}", timeout=1.0).version()
        except (OllamaError, ValueError, OSError):
            return None
        return f"http://{host}:{port}"

    with ThreadPoolExecutor(max_workers=64) as pool:
        return [url for url in pool.map(probe, (f"{prefix}.{i}" for i in range(1, 255))) if url]


# ---------------------------------------------------------------- 4. local tuning
def physical_cores() -> int:
    try:
        import psutil
        cores = psutil.cpu_count(logical=False)
        if cores:
            return int(cores)
    except (ImportError, OSError):
        pass
    return os.cpu_count() or 4


def total_memory_gb() -> float:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1048576
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


LOCAL_CTX = 2048
BOOST_CTX = 8192
ANSWER_TOKENS = {"fast": 320, "chat": 200, "general": 640, "code": 900, "deep": 1500, "vision": 400}
BOOST_ANSWER_TOKENS = {"fast": 700, "chat": 400, "general": 1200, "code": 1800, "deep": 2500, "vision": 800}


def load_options(where: str = "local") -> dict[str, Any]:
    """Settings that decide how Ollama loads a model. They must be identical on every request
    (warm-up, routing, answers); any difference makes Ollama reload the model, which costs seconds."""
    if where == "boost":
        return {"num_ctx": BOOST_CTX}
    return {"num_ctx": LOCAL_CTX, "num_thread": max(1, min(physical_cores(), 8))}


def keep_alive(role: str, where: str = "local") -> str | int:
    """The fast model stays loaded for good on a machine with room for it. Bigger local models load when
    needed and free their RAM soon after (V3 M2 RAM budget); the gaming PC keeps its models longer."""
    if where == "local" and role in ("fast", "chat") and total_memory_gb() >= 7:
        return -1
    return BIG_MODEL_KEEP if where == "local" else "30m"
