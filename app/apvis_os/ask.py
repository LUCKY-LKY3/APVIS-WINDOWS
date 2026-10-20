"""Ask: answer the owner's questions with local Ollama models (LOCAL ONLY by default).

Routing is owner-configured by role: a fast default, a smarter general model
for harder questions, and a code model for PC/code help. Answers are text only;
Ask never runs commands or changes the system (actions arrive with Mission
Control and always need approval).

V4: AI endpoints on the internet are still refused. Home's Ask (``web=True``) may
also catch the owner up on the news (public BBC feeds) and, while Settings ->
Ask -> "Search the web when unsure" is on (owner's choice, 2026-10-19), send the
search words only to DuckDuckGo or Wikipedia (see websearch.py).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .common import redact_sensitive, utc_now
from .missions import CAPABILITIES as MISSION_CAPABILITIES, is_question_like
from . import semantic
from .vault import Vault, notes_context
from .intelligence import CapabilityRequirement, DataSensitivity, DestinationPolicy, ProviderLocality, eligible_candidates
from .ollama import DEFAULT_URL, InstalledModel, OllamaAdapter, OllamaClient, OllamaError, local_url
from . import brain
from . import briefing, osint, websearch
from . import scheduler as sched
from .episodes import EpisodeStore

ROLES = ("fast", "general", "code", "deep", "chat", "vision")
# Owner decision 2026-09-23: llama3.2:1b is the fast default and the coder model
# handles PC/code help; qwen3:4b was to step in for harder questions only if fast
# enough. Measured on the OptiPlex (2026-09-24, CPU only) it always reasons first
# and took 2-5 minutes per answer, so it is the opt-in "deep" role and is never
# chosen automatically. Later entries are fallbacks when a model is not installed.
DEFAULT_ROLES: dict[str, list[str]] = {
    "fast": ["llama3.2:1b", "llama3.2:3b"],
    "general": ["llama3.2:3b", "llama3.2:1b"],
    "code": ["qwen2.5-coder:1.5b", "llama3.2:1b", "llama3.2:3b"],
    "deep": ["qwen3:4b", "qwen2.5-coder:7b", "llama3.2:3b", "llama3.2:1b"],
    # Small talk ("tell me a joke", "I'm bored"): the tiny model starts writing about twice as
    # fast on the OptiPlex CPU. Facts, code and harder questions never go to it.
    "chat": ["qwen2.5:0.5b", "llama3.2:1b", "llama3.2:3b"],
    # Screen questions: small vision models that can run on the OptiPlex CPU (slowly) or anywhere.
    "vision": ["moondream", "qwen2.5vl:3b", "gemma3:4b", "llava-phi3", "llava:7b", "minicpm-v"],
}
# V4: "If you don't know, say so" lets Ask notice an unsure answer and search the web instead; the old
# "say you cannot look things up" line made the model refuse questions about anything recent.
SYSTEM_PROMPT = (
    "You are APVIS, the assistant built into the owner's computer (APVIS OS). "
    "Answer the owner's latest question directly, confidently, clearly and briefly, like a knowledgeable friend. "
    "Do not apologise or describe your limitations unless the owner asks you to do something on the computer; "
    "then say you cannot do that yet. If you don't know something, say you don't know. "
    "Never invent specific numbers, names or dates you do not know."
)
# Owner's answer length (Settings): one line added to the system prompt (constant per setting,
# so Ollama's prompt cache still holds it) and a matching answer budget.
LENGTH_LINES = {"short": " Keep answers to one to three sentences unless the owner asks for more.",
                "normal": "",
                "detailed": " Give thorough, well-organised answers with the key details and examples."}
LENGTH_TOKENS = {"short": 0.5, "normal": 1.0, "detailed": 2.5}


def system_prompt(length: str = "normal") -> str:
    return SYSTEM_PROMPT + LENGTH_LINES.get(length, "")


MAX_QUESTION = 4000
HISTORY_LIMIT = 200
HISTORY_MESSAGES = 14            # six exchanges plus a file or screen text the chat is about
HISTORY_HARD_CHARS = 24000       # never more than this much earlier text in one prompt, whoever calls
WEB_TOKENS = 220                 # an answer from search results: a few sentences
WEB_OFF = "web search is off in Settings, so this is from the local model"
NOTES_INTRO = "Notes from the owner's vault (use them only if they answer the question; otherwise ignore them):\n"
EPISODES_INTRO = "Earlier Ask sessions (one-line summaries, newest first):\n"

_CODE = re.compile(r"(?i)\b(code|script|bash|python|terminal|command|error|traceback|compile|function|regex|sql|git|linux|sudo|apt|install|debug|bug)\b|```")
_HARD = re.compile(r"(?i)\b(explain|why|compare|difference|plan|design|analy[sz]e|pros and cons|step[- ]by[- ]step|summari[sz]e|essay|reason|prove|calculate|how does|how do)\b")


_ACTION = re.compile(
    r"(?i)^\s*(?:(?:hey|ok|okay)?\s*apvis[,:]?\s*)?(?:please\s+|can you\s+|could you\s+|would you\s+)?"
    r"(open|launch|start|run|close|quit|kill|install|uninstall|update|upgrade|delete|remove|erase|format|"
    r"shut\s*down|restart|reboot|turn\s+(?:on|off)|switch\s+(?:on|off)|enable|disable|set|change|mute|unmute|"
    r"play|pause|download|create|make\s+a\s+(?:file|folder)|move|copy|rename|send|email|buy)\b"
)
ACTION_REPLY = (
    "I can't do that one yet. Right now I can " + MISSION_CAPABILITIES + ". "
    "Anything that changes something asks for your approval first."
)


# Verbs that are just as often advice or writing requests ("set a goal for this month", "change my mindset",
# "run a 5k plan"): a request to act only when it names something on the computer or is a short name ("open
# spotify", "play some jazz").
_SOFT_VERBS = {"open", "launch", "start", "run", "update", "upgrade", "format", "set", "change", "play", "create", "make",
               "move", "copy"}
_DEVICEY = re.compile(r"(?i)\w\.[a-z0-9]{1,5}\b|/|~|\b(?:files?|folders?|apps?|programs?|window|tabs?|browser|wi-?fi|bluetooth|"
                      r"volume|sound|audio|music|songs?|playlist|video|movie|podcast|radio|computer|pc|laptop|desktop|"
                      r"documents|downloads|pictures|photos|trash|screen|brightness|wallpaper|theme|font|printer|keyboard|"
                      r"mouse|display|resolution|system|updates?|apvis|settings|timer|alarm|reminder)\b")


def is_action_request(question: str) -> bool:
    """Requests to act are answered honestly by APVIS itself, never by a model that might claim it acted.
    Questions that only start with a command word ("remove duplicates from a list in python", "set a goal for
    this month") are not."""
    m = _ACTION.match(question)
    if not m or is_question_like(question):
        return False
    if m.group(1).split()[0].lower() in _SOFT_VERBS:
        rest = question[m.end():]
        words = [w for w in re.findall(r"[\w'.%-]+", rest) if w.lower() not in {"the", "a", "an", "some", "for", "me", "please", "now"}]
        return bool(_DEVICEY.search(rest)) or (len(words) <= 2 and not re.match(r"(?i)\s*(?:my|our|your)\b", rest))
    return True


_QUESTIONY = re.compile(r"(?i)^\s*(?:who|what|what's|whats|when|where|which|why|how|is|are|was|were|do|does|did|can|could|should|"
                        r"would|will|tell\s+me\s+about|explain|define|list|give|write|make|create|summari[sz]e|translate|"
                        r"compare|find|show|name)\b")
# Small talk only: everything else is a question, and questions need the fast model, not the tiny one
# (V4: "recommend a book", "I need help with my CV" used to go to the 0.5B small-talk model, without notes).
_SMALL_TALK = re.compile(
    r"(?i)^\s*(?:(?:hey|ok|okay)\s+)?(?:apvis[,:]?\s+)?(?:"
    r"tell\s+me\s+(?:a|another)\s+(?:joke|riddle|fun\s+fact|story)(?:\s+about\s+.{1,40})?|make\s+me\s+(?:laugh|smile)|"
    r"i'?m\s+(?:so\s+|really\s+|very\s+)?(?:bored|tired|sad|happy|hungry|sleepy|lonely|stressed|back|home|here|excited)|"
    r"i\s+am\s+(?:so\s+|really\s+|very\s+)?(?:bored|tired|sad|happy|hungry|sleepy|lonely|stressed|back|home|here|excited)|"
    r"(?:you'?re|you\s+are|ur)\s+.{1,40}|i\s+(?:love|like|hate)\s+you|lol|lmao|rofl|haha+|hehe+|wow|omg|"
    r"how\s+was\s+your\s+day|sing\s+(?:me\s+)?a\s+song|entertain\s+me|(?:another|one\s+more)(?:\s+one)?|"
    r"do\s+you\s+(?:like|love|dream|sleep)\b.{0,40}|are\s+you\s+(?:real|alive|happy|ok|okay|there)"
    r")\s*[!.?]*\s*$")


def classify(question: str) -> str:
    """Pick a role from the question itself; everyday questions stay fast, only small talk goes to chat."""
    if _CODE.search(question):
        return "code"
    if _HARD.search(question) or len(question) > 220 or question.count("?") > 1:
        return "general"
    if _SMALL_TALK.match(question):
        return "chat"
    return "fast"


ROUTER_PROMPT = (
    "You route questions for a computer assistant. Reply with exactly one word:\n"
    "chat - everyday questions, facts, advice, conversation\n"
    "code - programming, scripts, terminal commands, Linux or PC problems, errors\n"
    "deep - long multi-step reasoning, detailed plans, maths proofs, in-depth analysis\n"
    "Reply with only chat, code or deep."
)
ROUTE_ROLES = {"chat": "fast", "code": "code", "deep": "deep"}


def parse_route(reply: str) -> str | None:
    """The router's one-word answer -> a role; None if it said something else."""
    words = re.findall(r"[a-z]+", (reply or "").lower())
    for word in words[:3]:
        if word in ROUTE_ROLES:
            return ROUTE_ROLES[word]
    return None


def _vision_names(roles: dict[str, list[str]], installed: list[InstalledModel]) -> set[str]:
    wanted = {m.removesuffix(":latest") for m in roles.get("vision", [])}
    return {m.name for m in installed if m.name.removesuffix(":latest") in wanted or m.name.split(":")[0] in wanted}


def resolve_model(role: str, roles: dict[str, list[str]], installed: list[InstalledModel]) -> str | None:
    # "llama3.2" and "llama3.2:latest" are the same model to Ollama.
    actual = {m.name.removesuffix(":latest"): m.name for m in installed}
    for candidate_role in (role, *ROLES):
        for wanted in roles.get(candidate_role, []):
            if wanted.removesuffix(":latest") in actual:
                return actual[wanted.removesuffix(":latest")]
    return None


def _state_dir() -> Path:
    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "ask"


# Small talk and pictures never look in the vault: the lookup would only cost time.
NO_MEMORY_ROLES = frozenset({"chat", "vision"})


@dataclass
class AskConfig:
    ollama_url: str = DEFAULT_URL
    roles: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_ROLES.items()})
    destination_policy: str = DestinationPolicy.LOCAL_ONLY.value
    # The owner's gaming PC running Ollama on the home network (optional; LAN addresses only).
    boost_url: str = ""
    boost_enabled: bool = False
    boost_mac: str = ""              # for Wake-on-LAN, optional
    api_enabled: bool = True         # the local APVIS API at http://127.0.0.1:8765
    answer_length: str = "normal"    # short | normal | detailed
    semantic_memory: bool = False    # V3: search the vault by meaning (local embedding model); off until switched on
    embed_model: str = ""            # "" = nomic-embed-text, else all-minilm (whichever is installed)
    episodes: bool = False           # V3 M4: remember one-line summaries of Ask sessions for 30 days; off until switched on
    web_search: bool = True          # V4 (owner, 2026-10-19): search words only, to DuckDuckGo/Wikipedia, when unsure

    def validate(self) -> "AskConfig":
        self.ollama_url = local_url(self.ollama_url)
        self.boost_url = local_url(self.boost_url) if (self.boost_url or "").strip() else ""
        self.boost_enabled = bool(self.boost_enabled and self.boost_url)
        self.api_enabled = bool(self.api_enabled)
        self.semantic_memory = bool(self.semantic_memory)
        self.episodes = bool(self.episodes)
        self.web_search = bool(self.web_search)
        self.embed_model = (self.embed_model or "").strip()
        if self.embed_model and not re.fullmatch(r"[a-z0-9][a-z0-9._-]*(:[a-z0-9._-]+)?", self.embed_model):
            raise ValueError("that is not a valid embedding model name")
        if self.answer_length not in LENGTH_LINES:
            raise ValueError("answer length is short, normal or detailed")
        mac = re.sub(r"[^0-9a-fA-F]", "", self.boost_mac or "")
        if self.boost_mac and len(mac) != 12:
            raise ValueError("a MAC address looks like 1C:1B:0D:12:34:56")
        self.boost_mac = ":".join(mac[i:i + 2] for i in range(0, 12, 2)).upper() if mac else ""
        DestinationPolicy(self.destination_policy)
        for role, models in self.roles.items():
            if role not in ROLES or not isinstance(models, list) or not all(isinstance(m, str) and m.strip() for m in models):
                raise ValueError(f"invalid model list for role {role!r}")
        for role in ROLES:
            self.roles.setdefault(role, list(DEFAULT_ROLES[role]))
        return self

    @classmethod
    def load(cls, path: Path | None = None) -> "AskConfig":
        path = path or _state_dir() / "config.json"
        config = cls()
        for source in (Path("/etc/apvis-os/ask.json"), path):
            try:
                data = json.loads(source.read_text(encoding="utf-8"))
            except FileNotFoundError:
                continue
            if not isinstance(data, dict):
                raise ValueError(f"{source} must contain an object")
            config.ollama_url = data.get("ollama_url", config.ollama_url)
            config.roles.update(data.get("roles", {}))
            config.destination_policy = data.get("destination_policy", config.destination_policy)
            for key in ("boost_url", "boost_enabled", "boost_mac", "api_enabled", "answer_length",
                        "semantic_memory", "embed_model", "episodes", "web_search"):
                if key in data:
                    setattr(config, key, data[key])
        if os.environ.get("APVIS_OLLAMA_URL"):
            config.ollama_url = os.environ["APVIS_OLLAMA_URL"]
        return config.validate()

    def save(self, path: Path | None = None) -> Path:
        self.validate()
        path = path or _state_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")
        return path


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- the conversation (follow-ups)

CONVERSATION_EXCHANGES = 6
RESUME_S = 30 * 60
HISTORY_CHARS = 3200             # ≈ 800 tokens of earlier chat: what the OptiPlex reads in a few seconds uncached
ANSWER_KEEP_CHARS = 1200
CONTEXT_FOLLOW_UPS = 3           # a file or screen text stays in the chat for this many follow-ups


class Conversation:
    """This chat's recent exchanges for follow-ups. Held in memory only (never written to disk, so nothing is
    kept without the owner's Save), and picked up again when Ask is reopened within RESUME_S.

    Ollama's prompt cache holds the chat so far, so a follow-up only costs its own words, as long as the earlier
    messages stay exactly as they were. So the chat grows unchanged until it passes its budget (or
    CONVERSATION_EXCHANGES), then drops back to its newest half in one go, instead of shifting by one exchange
    (which would make every follow-up re-read everything)."""

    def __init__(self, *, exchanges: int = CONVERSATION_EXCHANGES, budget: int = HISTORY_CHARS,
                 resume_s: float = RESUME_S, clock: Callable[[], float] = time.monotonic) -> None:
        self.exchanges, self.budget, self.resume_s, self._clock = exchanges, budget, resume_s, clock
        self._lock = threading.Lock()
        self._context: list[dict[str, str]] = []
        self._turns: list[tuple[str, str]] = []
        self._since_context = 0
        self._at = -1e18

    def _messages(self) -> list[dict[str, str]]:
        if self._clock() - self._at > self.resume_s:
            self._context, self._turns, self._since_context = [], [], 0
        out = [dict(m) for m in self._context]
        for question, answer in self._turns:
            out += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
        return out

    def messages(self) -> list[dict[str, str]]:
        with self._lock:
            return self._messages()

    def remember(self, history: list[dict[str, str]], question: str, answer: str) -> None:
        """Add one exchange. `history` is what that question was asked with: this chat (from messages()) or a
        file's text (documents.context), which then starts the chat."""
        answer = websearch.without_sources(answer).strip()
        if len(answer) > ANSWER_KEEP_CHARS:
            answer = answer[:ANSWER_KEEP_CHARS].rsplit(" ", 1)[0] + " …"
        with self._lock:
            if list(history) != self._messages():
                self._context, self._turns, self._since_context = [dict(m) for m in history], [], 0
            self._turns.append((question.strip(), answer))
            if self._context:
                self._since_context += 1
                if self._since_context > CONTEXT_FOLLOW_UPS:
                    self._context = []
            size = sum(len(q) + len(a) for q, a in self._turns)
            if len(self._turns) > self.exchanges or size > self.budget:
                kept, total = [], 0
                for q, a in reversed(self._turns):
                    if kept and (len(kept) >= max(1, self.exchanges // 2) or total + len(q) + len(a) > self.budget // 2):
                        break
                    kept.insert(0, (q, a))
                    total += len(q) + len(a)
                self._turns = kept
            self._at = self._clock()

    def clear(self) -> None:
        with self._lock:
            self._context, self._turns, self._since_context, self._at = [], [], 0, -1e18


def _cap_history(history: list[dict[str, str]], limit: int = HISTORY_HARD_CHARS) -> list[dict[str, str]]:
    """Drop the oldest messages until the earlier text fits; the newest message always stays."""
    out = list(history)
    while len(out) > 1 and sum(len(m["content"]) for m in out) > limit:
        out.pop(0)
    if out and out[0]["role"] == "assistant":
        out.pop(0)
    return out


_PAST = re.compile(r"(?i)\b(?:last\s+time|earlier|yesterday|before|previously|the\s+other\s+day|we\s+(?:talked|spoke|discussed|chatted)|"
                   r"you\s+(?:said|told\s+me|mentioned|suggested)|i\s+(?:asked|told\s+you|mentioned)|remember\s+when|"
                   r"did\s+i\s+ask|our\s+(?:last\s+)?(?:chat|conversation|session))\b")
_PAST_WORDS = set("last time earlier yesterday before previously other day talk talked spoke discussed chat chatted said told "
                  "mentioned suggested asked remember when session conversation we".split())


@dataclass
class AskResult:
    question: str
    status: str                       # completed | unavailable | failed | cancelled
    answer: str = ""
    role: str = ""
    model: str | None = None
    provider: str = "ollama"
    endpoint: str = ""
    locality: str = ProviderLocality.LOCAL.value
    error: str | None = None
    first_token_s: float | None = None
    memory_s: float | None = None      # time spent finding notes (query embedding + search); inside first_token_s
    queue_s: float | None = None       # time waiting for other local model work to give way; inside first_token_s
    notes_used: list[str] = field(default_factory=list)
    total_s: float | None = None
    routed_by: str | None = None       # the fast model that picked the role, when it did
    route_s: float | None = None
    source: str = "local"              # instant | remembered | local | gaming-pc | web | news
    tokens_per_s: float | None = None  # the model's writing speed, from Ollama's own timing
    history_used: int = 0              # earlier messages of this chat the model saw
    via: str = ""                      # V4: where else the answer came from, for its label ("from the web ...")
    sources: list[dict[str, str]] = field(default_factory=list)   # V4: {title, url} of web pages / headlines used
    search_s: float | None = None      # V4: time the web search took; inside first_token_s
    observed_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AskService:
    def __init__(self, config: AskConfig | None = None, client: OllamaClient | None = None,
                 history: Path | None = None, clock: Callable[[], float] = time.perf_counter,
                 vault: Vault | None = None, cache: brain.AnswerCache | None = None,
                 boost: brain.BoostState | None = None, name: str | None = None,
                 scheduler: sched.ModelScheduler | None = None, web: websearch.WebSearch | None = None,
                 news_fetch: Callable[[str], bytes] | None = None, episodes: EpisodeStore | None = None) -> None:
        self.config = config or AskConfig.load()
        self.client = client or OllamaClient(self.config.ollama_url)
        self.history = history or _state_dir() / "history.jsonl"
        self.vault = vault or Vault()
        self.cache = cache or brain.AnswerCache(self.history.parent / "answers.json")
        self.boost = boost or brain.BOOST
        self._name = name
        self._clock = clock
        self.scheduler = scheduler or sched.SCHEDULER
        self.web = web or websearch.WEB
        self.news_fetch = news_fetch
        self.episodes = episodes

    def note_search(self) -> Callable[..., list]:
        """Vault search for this question: hybrid (keywords + meaning) when meaning search is on and an
        embedding model is installed, keywords only otherwise. Never slower than QUERY_TIMEOUT."""
        try:
            index = semantic.index_for(self.config, self.client)
        except (OSError, ValueError):
            index = None
        if index is None:
            return self.vault.search
        return lambda query, limit=8: semantic.hybrid_search(self.vault, query, limit, index)

    def owner_name(self) -> str:
        if self._name is None:
            try:
                from .hostinfo import real_name
                self._name = real_name()
            except (ImportError, OSError, KeyError, ValueError):
                self._name = ""
            if self._name.lower() == "apvis":
                self._name = ""
        return self._name

    def boost_client(self, role: str) -> tuple[OllamaClient, str] | None:
        """The gaming PC and the model it would use for this role, if it is on right now."""
        if not (self.config.boost_enabled and self.config.boost_url):
            return None
        state = self.boost.get(self.config.boost_url)
        if not state.get("reachable"):
            return None
        chosen = brain.pick_boost_model(role, state.get("models", []))
        return (OllamaClient(self.config.boost_url, timeout=3), chosen) if chosen else None

    def warm(self, model: str | None = None) -> str | None:
        """Load the fast model with the real settings and run the system prompt once, so Ollama's
        prompt cache holds it and the next question only has to process its own words."""
        try:
            installed = self.client.models()
        except OllamaError:
            return None
        model = model or resolve_model("fast", self.config.roles, installed)
        if not model:
            return None
        try:
            with self.scheduler.slot(sched.PLAN, "warm-up"):
                return self._warm(model, installed)
        except sched.Cancelled:
            return None

    def _warm(self, model: str, installed: list[InstalledModel]) -> str | None:
        chat = resolve_model("chat", self.config.roles, installed)
        messages = [{"role": "system", "content": system_prompt(self.config.answer_length)}, {"role": "user", "content": "hi"}]
        for name, role in ((model, "fast"), (chat, "chat")):
            if not name or (role == "chat" and name == model):
                continue
            try:
                for _ in self.client.chat_stream(name, messages, max_tokens=1, read_timeout=240.0,
                                                 options=brain.load_options("local"), keep_alive=brain.keep_alive(role)):
                    pass
            except OllamaError:
                if role == "fast":
                    return None
        index = semantic.index_for(self.config, self.client, [m.name for m in installed])
        if index is not None:
            try:                                   # load it now so the first question doesn't pay for it
                self.client.embed(index.model, ["warm-up"], keep_alive=sched.EMBED_KEEP_LIVE, timeout=60.0)
            except OllamaError:
                pass
        return model

    def status(self) -> dict[str, Any]:
        """What Ask would use right now; never claims a model that was not observed."""
        result: dict[str, Any] = {"endpoint": self.client.url, "destination_policy": self.config.destination_policy,
                                  "observed_at": utc_now()}
        try:
            result["ollama_version"] = self.client.version()
            installed = self.client.models()
        except OllamaError as exc:
            result.update({"status": "unavailable", "error": str(exc)})
            return result
        result["installed"] = [m.name for m in installed]
        result["roles"] = {role: resolve_model(role, self.config.roles, installed) for role in ROLES}
        result["status"] = "available" if any(result["roles"].values()) else "no-model"
        return result

    def ask(self, question: str, *, role: str | None = None, model: str | None = None,
            on_text: Callable[[str], None] | None = None, cancelled: Callable[[], bool] = lambda: False,
            history: list[dict[str, str]] | None = None, images: list[str] | None = None,
            web: bool = False) -> AskResult:
        """`web=True` is Home's Ask: news catch-up, and web search when the owner's switch allows it.
        The API and the command line leave it off (their prompts may hold text that must stay here)."""
        question = (question or "").strip()
        if not question:
            raise ValueError("a question is required")
        if len(question) > MAX_QUESTION:
            raise ValueError(f"questions are limited to {MAX_QUESTION} characters")
        history = _cap_history([{"role": m["role"], "content": m["content"]} for m in (history or [])
                                if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)][-HISTORY_MESSAGES:])
        start = self._clock()

        def finish_now(answer: str, source: str, model_name: str, provider: str = "apvis") -> AskResult:
            result = AskResult(question, "completed", answer=answer, role=role or "fast", model=model_name,
                               provider=provider, endpoint=self.client.url, source=source)
            result.first_token_s = result.total_s = round(self._clock() - start, 3)
            if on_text:
                on_text(answer)
            return self._record(result)

        # 1. Instant answers and 2. remembered answers: no model, no waiting.
        if images:
            role = "vision"
        web_note = ""
        searchable = web and model is None and not images
        if model is None and not images:
            instant = brain.instant_answer(question, self.owner_name())
            if instant:
                return finish_now(instant, "instant", "APVIS")
            if searchable:
                topics = briefing.topics_for(question)
                if topics:
                    return self._news(question, topics, start, on_text, cancelled)
                explicit = websearch.explicit_query(question)
                if explicit or websearch.is_time_sensitive(question):
                    if not self.config.web_search:
                        web_note = WEB_OFF
                    else:
                        words = explicit or websearch.search_words(question, follow_up=bool(history))
                        if words:
                            found, web_note = self._web(question, words, start, on_text, cancelled,
                                                        why="asked" if explicit else "timely")
                            if found is not None:
                                return found
            if role is None and not history:
                remembered = self.cache.get(question)
                if remembered:
                    return finish_now(remembered["answer"], "remembered", remembered.get("model", ""), "ollama")
        if role is not None and role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        if model is None and is_action_request(question):
            result = AskResult(question, "completed", answer=ACTION_REPLY, role=role or classify(question), model="APVIS",
                               provider="apvis", endpoint=self.client.url, source="instant")
            result.first_token_s = result.total_s = round(self._clock() - start, 2)
            if on_text:
                on_text(ACTION_REPLY)
            return self._record(result)
        # Everything below makes this computer's models work: one job at a time (V3 M2 scheduler), so
        # background indexing never runs beside the answer.
        try:
            with self.scheduler.slot(sched.LIVE, "question", cancelled=cancelled):
                queue_s = round(self._clock() - start, 3)
                result = self._answer(question, role, model, on_text, cancelled, history, images, start, queue_s,
                                      record=not searchable)
        except sched.Cancelled:
            result = AskResult(question, "cancelled", role=role or classify(question), endpoint=self.client.url)
            result.total_s = round(self._clock() - start, 2)
            return self._record(result)
        if not searchable:
            return result
        if web_note:                                  # the web was wanted but is off or found nothing
            result.via = web_note if web_note == WEB_OFF else "the web search found nothing: " + web_note
        elif (result.status == "completed" and self.config.web_search and result.source in ("local", "gaming-pc")
              and websearch.sounds_unsure(result.answer)):
            words = websearch.search_words(question, follow_up=bool(history))
            if words:
                found, note = self._web(question, words, start, on_text, cancelled, why="unsure", local=result)
                if found is not None:
                    return found
            elif history and websearch.search_words(question) is not None:
                # Only this question's words may be searched, and alone they mean nothing ("and its population?").
                result.answer += "\n\n(Ask it as a full question and I'll check the web.)"
                if on_text:
                    on_text(result.answer)
        return self._record(result)

    def _answer(self, question: str, role: str | None, model: str | None, on_text: Callable[[str], None] | None,
                cancelled: Callable[[], bool], history: list[dict[str, str]], images: list[str] | None,
                start: float, queue_s: float, record: bool = True) -> AskResult:
        routed_by, route_s = None, None
        chosen_role = role
        if role is None and model is None:
            role, routed_by = self.route(question)
            route_s = round(self._clock() - start, 2) if routed_by else None
        role = role or classify(question)
        if role == "chat" and history and chosen_role is None:
            role = "fast"                     # a follow-up needs the model that can follow the chat
        result = AskResult(question, "failed", role=role, endpoint=self.client.url, routed_by=routed_by, route_s=route_s,
                           queue_s=queue_s)
        system = system_prompt(self.config.answer_length)
        result.history_used = len(history)
        blocks: list[str] = []
        if role not in NO_MEMORY_ROLES and not images:
            memory_start = self._clock()
            try:
                # One note when this computer answers: every extra line is prompt the OptiPlex CPU reads before
                # the first word (measured: two equally relevant notes pushed it past 1.5 s). The gaming PC
                # reads prompts far faster, so it may get a second, nearly-as-relevant note.
                note_limit = 2 if model is None and self.boost_client(role) else 1
                context, result.notes_used = notes_context(self.vault, question, limit=note_limit,
                                                           search=self.note_search())
            except OSError:
                context = ""
            if context:
                blocks.append(NOTES_INTRO + context)
            lines = self._episode_lines(question)
            if lines:
                blocks.append(EPISODES_INTRO + "\n".join(f"- {line}" for line in lines))
            result.memory_s = round(self._clock() - memory_start, 3)
        # The system prompt never changes, so Ollama's prompt cache (primed by warm()) still holds it and
        # the history; notes ride in this turn only, where the model has to read them anyway. Small models
        # follow the last thing they read, so the question always comes last.
        content = question
        if blocks:
            content = "\n\n".join(blocks) + "\n\nQuestion: " + question
        user: dict[str, Any] = {"role": "user", "content": content}
        if images:
            user["images"] = images[:2]               # base64 PNG/JPEG for a vision model
        messages = [{"role": "system", "content": system}, *history, user]
        parts: list[str] = []

        def stream(client: OllamaClient, chosen: str, where: str) -> None:
            # Hard privacy rule: only LOCAL candidates (this computer or the home network) under the configured policy.
            self._check_local(client, chosen, role)
            result.model, result.endpoint = chosen, client.url
            result.source = "gaming-pc" if where == "boost" else "local"
            tokens = (brain.BOOST_ANSWER_TOKENS if where == "boost" else brain.ANSWER_TOKENS).get(role, 640)
            tokens = int(tokens * LENGTH_TOKENS.get(self.config.answer_length, 1.0))
            stats: dict[str, Any] = {}
            for text in client.chat_stream(chosen, messages, cancelled=cancelled, max_tokens=tokens, stats=stats,
                                           options=brain.load_options(where), keep_alive=brain.keep_alive(role, where)):
                if result.first_token_s is None:
                    result.first_token_s = round(self._clock() - start, 2)
                parts.append(text)
                if on_text:
                    on_text("".join(parts))
            if stats.get("eval_count") and stats.get("eval_duration"):
                result.tokens_per_s = round(stats["eval_count"] / (stats["eval_duration"] / 1e9), 1)

        try:
            # 3. The gaming PC, when it is on (never for a specific local model the owner picked).
            boost = self.boost_client(role) if model is None else None
            if boost is not None:
                try:
                    stream(boost[0], boost[1], "boost")
                except OllamaError as exc:
                    self.boost.mark_down(self.config.boost_url, str(exc))
                    if parts:
                        raise OllamaError("the gaming PC stopped answering") from exc
                    boost = None       # it went away before answering: this computer answers instead
            if boost is None:
                # 4. This computer.
                installed = self.client.models()
                chosen = model if model and model in {m.name for m in installed} else resolve_model(role, self.config.roles, installed)
                if images and chosen not in _vision_names(self.config.roles, installed):
                    result.status = "unavailable"
                    result.error = "no vision model is installed"
                    return self._record(result) if record else result
                if model and chosen != model:
                    raise OllamaError(f"model {model} is not installed")
                if chosen is None:
                    result.status = "unavailable"
                    result.error = "no Ollama model is installed for Ask"
                    return self._record(result) if record else result
                stream(self.client, chosen, "local")
            result.answer = "".join(parts).strip()
            result.status = "cancelled" if cancelled() else "completed"
            if result.status == "completed" and not blocks and not history and model is None:
                self.cache.put(question, result.answer, result.model or "")
        except OllamaError as exc:
            result.status = "unavailable" if "not reachable" in str(exc) else "failed"
            result.error = str(exc)
        result.total_s = round(self._clock() - start, 2)
        return self._record(result) if record else result

    def _check_local(self, client: OllamaClient, chosen: str, role: str) -> None:
        adapter = OllamaAdapter(client, chosen)
        requirement = CapabilityRequirement.CODE if role == "code" else CapabilityRequirement.GENERAL
        if not eligible_candidates(requirement, DestinationPolicy(self.config.destination_policy),
                                   DataSensitivity.PRIVATE, [adapter.candidate]):
            raise OllamaError("routing policy refused the local model")

    def _episode_lines(self, question: str) -> list[str]:
        """Earlier sessions' one-line summaries, only while session memory is on and the question looks back."""
        if not self.config.episodes or not _PAST.search(question):
            return []
        try:
            items = (self.episodes or EpisodeStore()).list()
        except (OSError, ValueError):
            return []
        wanted = set(websearch.content_words(question)) - _PAST_WORDS
        if wanted:
            items = [e for e in items if wanted & set(websearch.content_words(e.summary + " " + " ".join(e.questions)))]
        return [e.summary.strip()[:160] for e in items[:2]]

    def _complete(self, result: AskResult, messages: list[dict[str, Any]], start: float, cancelled: Callable[[], bool],
                  emit: Callable[[str], None], *, tokens: int, read_timeout: float = 300.0) -> str:
        """One short answer from the fast model (on the gaming PC when it is on), for web and news answers."""
        targets: list[tuple[OllamaClient, str, str]] = []
        boost = self.boost_client("fast")
        if boost is not None:
            targets.append((boost[0], boost[1], "boost"))
        targets.append((self.client, "", "local"))
        for client, chosen, where in targets:
            if where == "local":
                chosen = resolve_model("fast", self.config.roles, self.client.models()) or ""
                if not chosen:
                    raise OllamaError("no Ollama model is installed for Ask")
            self._check_local(client, chosen, "fast")
            parts: list[str] = []
            stats: dict[str, Any] = {}
            try:
                for text in client.chat_stream(chosen, messages, cancelled=cancelled, stats=stats, read_timeout=read_timeout,
                                               max_tokens=int(tokens * LENGTH_TOKENS.get(self.config.answer_length, 1.0)),
                                               options=brain.load_options(where), keep_alive=brain.keep_alive("fast", where)):
                    if result.first_token_s is None:
                        result.first_token_s = round(self._clock() - start, 2)
                    parts.append(text)
                    emit("".join(parts))
            except OllamaError as exc:
                if where == "boost" and not parts:
                    self.boost.mark_down(self.config.boost_url, str(exc))
                    continue
                raise
            result.model, result.endpoint, result.provider = chosen, client.url, "ollama"
            if where == "boost":
                result.via = (result.via + " · " if result.via else "") + "written on the gaming PC"
            if stats.get("eval_count") and stats.get("eval_duration"):
                result.tokens_per_s = round(stats["eval_count"] / (stats["eval_duration"] / 1e9), 1)
            return "".join(parts)
        raise OllamaError("no model answered")

    def _web(self, question: str, words: str, start: float, on_text: Callable[[str], None] | None,
             cancelled: Callable[[], bool], *, why: str, local: AskResult | None = None) -> tuple[AskResult | None, str]:
        """Search the web for `words` (nothing else is sent) and answer from the results with the fast model.
        Returns (the answer, "") or (None, why nothing was found); with `local` (an unsure answer) that answer
        is kept, saying the web found nothing."""
        lead = (local.answer.strip() + "\n\n") if local is not None and local.answer.strip() else ""
        if on_text:
            on_text(lead + f"Searching the web for “{words}”…")
        search_start = self._clock()
        outcome = self.web.search(words, wiki=websearch.wiki_subject(question) if why != "timely" else None)
        search_s = round(self._clock() - search_start, 3)
        if cancelled():
            gone = AskResult(question, "cancelled", role="fast", endpoint=self.client.url, source="web", search_s=search_s)
            gone.total_s = round(self._clock() - start, 2)
            return self._record(gone), ""
        if not outcome.results:
            note = "; ".join(outcome.errors) or f"nothing useful came up for “{words}”"
            if local is None:
                return None, note
            local.answer = lead + f"(I also searched the web, but {note}.)"
            local.via, local.search_s = "searched the web too: nothing found", search_s
            if on_text:
                on_text(local.answer)
            return self._record(local), note
        result = AskResult(question, "completed", role="fast", model="APVIS", provider="apvis", endpoint=self.client.url,
                           source="web", search_s=search_s,
                           sources=[{"title": r.title, "url": r.url} for r in outcome.results],
                           via=f"from the web ({', '.join(outcome.sources)}) · sent only “{words}”")
        sources = websearch.sources_text(outcome.results)
        messages = [{"role": "system", "content": system_prompt(self.config.answer_length)},
                    {"role": "user", "content": websearch.answer_prompt(question, outcome.results)}]
        text = ""
        try:
            with self.scheduler.slot(sched.LIVE, "question", cancelled=cancelled):
                # Only the answer streams (the sources join it at the end), so the view stays on the answer.
                text = self._complete(result, messages, start, cancelled, on_text or (lambda t: None), tokens=WEB_TOKENS)
        except sched.Cancelled:
            result.status = "cancelled"
        except OllamaError as exc:                     # no model: the results themselves are the answer
            result.error = str(exc)
        if cancelled():
            result.status = "cancelled"
        text = text.strip()
        result.answer = (text + sources) if text else websearch.results_text(outcome)
        if result.first_token_s is None:
            result.first_token_s = round(self._clock() - start, 2)
        result.total_s = round(self._clock() - start, 2)
        return self._record(result), ""

    def _news(self, question: str, topics: tuple[str, ...], start: float, on_text: Callable[[str], None] | None,
              cancelled: Callable[[], bool]) -> AskResult:
        """The news catch-up: a short spoken summary from the fast model, then the newest headlines with their
        links (the headlines alone when the model is slow or unreachable). Only the summary streams: Home's
        answer view follows streaming text, and the list would push the summary out of sight."""
        groups, errors = briefing.gather(topics, self.news_fetch)
        result = AskResult(question, "completed", role="fast", model="APVIS", provider="apvis", endpoint=self.client.url,
                           source="news")
        if not groups:
            result.answer = briefing.unavailable(errors or [osint.BBC_FEEDS[t][0] for t in topics])
            result.via = "news feeds unreachable"
            result.first_token_s = result.total_s = round(self._clock() - start, 2)
            if on_text:
                on_text(result.answer)
            return self._record(result)
        listing = briefing.listing(groups, errors)
        result.sources = [{"title": r["title"], "url": r["url"]} for t in briefing.TOPICS for r in groups.get(t, [])]
        result.via = "headlines: " + ", ".join(osint.BBC_FEEDS[t][0] for t in briefing.TOPICS if t in groups)
        messages = [{"role": "system", "content": system_prompt(self.config.answer_length)},
                    {"role": "user", "content": briefing.summary_prompt(groups)}]
        summary = ""
        try:
            with self.scheduler.slot(sched.LIVE, "question", cancelled=cancelled):
                summary = self._complete(result, messages, start, cancelled, on_text or (lambda t: None),
                                         tokens=briefing.SUMMARY_TOKENS, read_timeout=12.0)
        except sched.Cancelled:
            result.status = "cancelled"
        except OllamaError as exc:
            result.error = str(exc)
            result.via += " · no summary: the local model didn't answer"
        if cancelled():
            result.status = "cancelled"
        summary = summary.strip()
        result.answer = (summary + "\n\n" + listing) if summary else listing
        if result.first_token_s is None:
            result.first_token_s = round(self._clock() - start, 2)
        result.total_s = round(self._clock() - start, 2)
        return self._record(result)

    def route(self, question: str) -> tuple[str | None, str | None]:
        """The fast model decides which role answers (owner's design, 2026-09-25).

        Skipped when every role would land on the same model anyway. Anything
        unexpected (no fast model, a timeout, a reply that is not one of the
        three words) falls back to the keyword rules in classify(). "deep" is
        answered by the general role: the reasoning model took minutes per answer
        on the OptiPlex, so it is only used when the owner picks it.
        """
        try:
            installed = self.client.models()
        except OllamaError:
            return None, None
        if classify(question) in ("fast", "chat"):
            return None, None     # short everyday question: no extra model call before answering
        fast = resolve_model("fast", self.config.roles, installed)
        targets = {resolve_model(r, self.config.roles, installed) for r in ("fast", "code", "general")}
        if fast is None or len(targets) < 2:
            return None, None
        messages = [{"role": "system", "content": ROUTER_PROMPT}, {"role": "user", "content": question[:1500]}]
        try:
            reply = "".join(self.client.chat_stream(fast, messages, max_tokens=4, read_timeout=20.0,
                                                    options=brain.load_options("local"), keep_alive=brain.keep_alive("fast")))
        except OllamaError:
            return None, None
        chosen = parse_route(reply)
        if chosen == "deep":
            chosen = "general"    # V4: the router picked the minutes-long model for "explain step by step"
        return (chosen, fast) if chosen else (None, None)

    def _record(self, result: AskResult) -> AskResult:
        """Keep a private local history (owner-only file, bounded, credentials redacted)."""
        try:
            self.history.parent.mkdir(parents=True, exist_ok=True)
            lines = self.history.read_text(encoding="utf-8").splitlines() if self.history.exists() else []
            lines.append(json.dumps(redact_sensitive(result.to_dict()), sort_keys=True))
            _atomic_write(self.history, "\n".join(lines[-HISTORY_LIMIT:]) + "\n")
        except OSError:
            pass  # history is a convenience; the answer itself must still be shown
        return result
