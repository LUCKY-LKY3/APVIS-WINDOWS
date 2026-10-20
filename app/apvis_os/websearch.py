"""Web search when Ask is unsure (owner's choice, 2026-10-19; Settings -> Ask -> "Search the web when unsure").

Ask searches when the owner asks it to ("search for ...", "look up ...", "google ..."), when a question is
clearly about now (latest, today, prices, scores, who won, this year...), and when the local model's own
answer says it doesn't know. It then answers again, with the fast model, from a few trimmed results, and
shows the sources.

Privacy: only the search words leave this computer, and only to two key-free sources over https:
DuckDuckGo's HTML results and Wikipedia. Never vault notes, earlier messages, file contents or device data;
questions about the owner's own things (my notes, my files, this computer...) and anything that looks
like a credential, an e-mail address, a phone number or an address on the network are never searched.
Responses are size-limited, time-limited (5 s) and kept in a small in-memory cache. AI endpoints on the
internet are still refused (ollama.local_url).
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Callable

from .common import redact_sensitive

ALLOWED_HOSTS = frozenset({"html.duckduckgo.com", "en.wikipedia.org"})
TIMEOUT_S = 5.0
MAX_BYTES = 768 * 1024          # a DuckDuckGo results page is ~30-80 KB; Wikipedia answers are a few KB
CACHE_TTL_S = 15 * 60
CACHE_LIMIT = 64
MAX_RESULTS = 3                 # each result is ~60 prompt tokens: three keep the answer prompt small
SNIPPET_CHARS = 240
MAX_QUERY_WORDS = 16
SOURCES_HEADER = "\n\nSources:\n"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 APVIS-OS/4"
WIKI_AGENT = "APVIS-OS/4 (personal desktop assistant; looks up what its owner asks about)"
DDG_URL = "https://html.duckduckgo.com/html/?q="
WIKI_SEARCH = "https://en.wikipedia.org/w/api.php?action=query&list=search&srlimit=1&srprop=&format=json&srsearch="
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"

Fetch = Callable[[str], bytes]


class SearchError(OSError):
    """A source could not be reached or sent something APVIS will not read."""


# ---------------------------------------------------------------- fetching (https, fixed hosts, bounded)

def allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return (parts.scheme == "https" and (parts.hostname or "").lower() in ALLOWED_HOSTS and not parts.username
            and not parts.password and parts.port in (None, 443))


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        if not allowed(newurl):
            raise SearchError("a search source tried to send APVIS elsewhere")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_Redirects)


def fetch(url: str, timeout: float = TIMEOUT_S) -> bytes:
    """GET one allowed https URL; at most MAX_BYTES; SearchError on anything else."""
    if not allowed(url):
        raise SearchError("only DuckDuckGo and Wikipedia are searched")
    # DuckDuckGo's HTML page expects a browser; Wikimedia asks API clients to say who they are.
    agent = WIKI_AGENT if urllib.parse.urlsplit(url).hostname == "en.wikipedia.org" else USER_AGENT
    request = urllib.request.Request(url, headers={"User-Agent": agent, "Accept-Language": "en-GB,en;q=0.8",
                                                   "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"})
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
    except SearchError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SearchError(f"could not be reached ({getattr(exc, 'reason', exc)})") from None
    if len(data) > MAX_BYTES:
        raise SearchError("sent more than APVIS reads")
    return data


# ---------------------------------------------------------------- results

@dataclass
class WebResult:
    title: str
    url: str
    snippet: str
    source: str                      # DuckDuckGo | Wikipedia

    @property
    def site(self) -> str:
        host = (urllib.parse.urlsplit(self.url).hostname or "").lower()
        return host.removeprefix("www.")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class SearchOutcome:
    query: str
    results: list[WebResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0
    cached: bool = False

    @property
    def sources(self) -> list[str]:
        return sorted({r.source for r in self.results})


def _plain(text: str, limit: int = SNIPPET_CHARS) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _result_url(href: str) -> str | None:
    """A DuckDuckGo result link -> the page it points at (its /l/?uddg= redirect unwrapped); ads -> None."""
    href = (href or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    parts = urllib.parse.urlsplit(href)
    host = (parts.hostname or "").lower()
    if host.endswith("duckduckgo.com"):
        if parts.path.startswith("/l/"):
            target = urllib.parse.parse_qs(parts.query).get("uddg", [""])[0]
            return _result_url(target) if target and "duckduckgo.com" not in target[:40] else None
        return None                                  # /y.js ads and DuckDuckGo's own pages
    if parts.scheme not in ("http", "https") or not host:
        return None
    return href


class _DuckDuckGoPage(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._field: str | None = None
        self._tag = ""
        self._depth = 0
        self._ad = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        classes = set(a.get("class", "").split())
        if self._field is not None:
            if tag == self._tag:
                self._depth += 1
            return
        if tag == "div" and "result" in classes:
            self._ad = "result--ad" in classes
        elif tag == "a" and "result__a" in classes:
            self.rows.append({"title": "", "url": _result_url(a.get("href", "")), "snippet": "", "ad": self._ad})
            self._field, self._tag, self._depth = "title", tag, 1
        elif "result__snippet" in classes and self.rows:
            self._field, self._tag, self._depth = "snippet", tag, 1

    def handle_endtag(self, tag: str) -> None:
        if self._field is not None and tag == self._tag:
            self._depth -= 1
            if self._depth <= 0:
                self._field = None

    def handle_data(self, data: str) -> None:
        if self._field is not None and self.rows:
            self.rows[-1][self._field] += data


def parse_duckduckgo(page: str, limit: int = MAX_RESULTS) -> list[WebResult]:
    parser = _DuckDuckGoPage()
    try:
        parser.feed(page)
        parser.close()
    except (AssertionError, ValueError):            # malformed HTML: keep whatever was read
        pass
    out, seen = [], set()
    for row in parser.rows:
        title, url, snippet = _plain(row["title"], 120), row["url"], _plain(row["snippet"])
        if row["ad"] or not url or not title or url in seen:
            continue
        seen.add(url)
        out.append(WebResult(title, url, snippet, "DuckDuckGo"))
        if len(out) >= limit:
            break
    return out


def parse_wikipedia_search(data: dict[str, Any]) -> str | None:
    hits = ((data or {}).get("query") or {}).get("search") or []
    title = hits[0].get("title") if hits and isinstance(hits[0], dict) else None
    return str(title) if title else None


def parse_wikipedia_summary(data: dict[str, Any]) -> WebResult | None:
    if not isinstance(data, dict) or data.get("type") not in ("standard", None) or not data.get("extract"):
        return None                                  # disambiguation pages and missing pages say nothing useful
    url = (((data.get("content_urls") or {}).get("desktop") or {}).get("page") or "")
    if not url.startswith("https://en.wikipedia.org/"):
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(str(data.get("title", "")).replace(" ", "_"))
    return WebResult(str(data.get("title") or "Wikipedia"), url, _plain(str(data["extract"]), 420), "Wikipedia")


# ---------------------------------------------------------------- the searcher

class WebSearch:
    """DuckDuckGo (and Wikipedia for "who/what is" questions), both at once, with a small cache."""

    def __init__(self, fetch: Fetch = fetch, clock: Callable[[], float] = time.monotonic) -> None:
        self._fetch, self._clock = fetch, clock
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], tuple[float, SearchOutcome]] = {}

    def duckduckgo(self, query: str, limit: int = MAX_RESULTS) -> list[WebResult]:
        page = self._fetch(DDG_URL + urllib.parse.quote_plus(query)).decode("utf-8", "replace")
        results = parse_duckduckgo(page, limit)
        if not results and ("anomaly" in page.lower() or "captcha" in page.lower()):
            raise SearchError("is limiting automated searches right now")
        return results

    def wikipedia(self, subject: str) -> WebResult | None:
        found = json.loads(self._fetch(WIKI_SEARCH + urllib.parse.quote_plus(subject)).decode("utf-8", "replace"))
        title = parse_wikipedia_search(found)
        if not title:
            return None
        page = json.loads(self._fetch(WIKI_SUMMARY + urllib.parse.quote(title.replace(" ", "_"), safe="")
                                      + "?redirect=true").decode("utf-8", "replace"))
        return parse_wikipedia_summary(page)

    def search(self, query: str, *, wiki: str | None = None, limit: int = MAX_RESULTS) -> SearchOutcome:
        key = (query.lower(), (wiki or "").lower())
        now = self._clock()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] <= CACHE_TTL_S:
                return SearchOutcome(hit[1].query, list(hit[1].results), [], 0.0, True)
        outcome = SearchOutcome(query)

        def ddg() -> list[WebResult]:
            try:
                return self.duckduckgo(query, limit)
            except (SearchError, ValueError) as exc:
                outcome.errors.append(f"DuckDuckGo {exc}" if isinstance(exc, SearchError) else "DuckDuckGo sent a page APVIS could not read")
                return []

        def wp() -> list[WebResult]:
            if not wiki:
                return []
            try:
                found = self.wikipedia(wiki)
                return [found] if found else []
            except (SearchError, ValueError) as exc:
                outcome.errors.append(f"Wikipedia {exc}" if isinstance(exc, SearchError) else "Wikipedia sent data APVIS could not read")
                return []

        with ThreadPoolExecutor(max_workers=2) as pool:
            wiki_job, ddg_job = pool.submit(wp), pool.submit(ddg)
            merged = wiki_job.result() + ddg_job.result()
        seen: set[str] = set()
        for result in merged:
            if result.url not in seen:
                seen.add(result.url)
                outcome.results.append(result)
        outcome.results = outcome.results[:limit]
        outcome.seconds = round(self._clock() - now, 3)
        if outcome.results:
            with self._lock:
                self._cache[key] = (now, outcome)
                if len(self._cache) > CACHE_LIMIT:
                    for old in sorted(self._cache, key=lambda k: self._cache[k][0])[: len(self._cache) - CACHE_LIMIT]:
                        del self._cache[old]
        return outcome


WEB = WebSearch()                   # shared, so the cache outlives each question's AskService


# ---------------------------------------------------------------- when to search, and what to send

_LEAD = re.compile(r"(?i)^\s*(?:(?:hey|ok|okay)\s+)?(?:apvis[,:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?")
_EXPLICIT = (
    re.compile(r"(?i)^(?:search|google|duckduckgo|bing)\s+(?:(?:the\s+)?(?:web|internet|online)\s+)?(?:for\s+|about\s+)?(?P<q>.+?)"
               r"(?:\s+(?:online|on\s+the\s+(?:web|internet)))?\s*[.!?]*$"),
    re.compile(r"(?i)^look\s+up\s+(?P<q>.+?)(?:\s+(?:online|on\s+the\s+(?:web|internet)))?\s*[.!?]*$"),
    re.compile(r"(?i)^look\s+(?P<q>.+?)\s+up(?:\s+(?:online|on\s+the\s+(?:web|internet)))?\s*[.!?]*$"),
    re.compile(r"(?i)^(?:find|check)\s+(?:online|on\s+the\s+(?:web|internet))\s+(?:for\s+)?(?P<q>.+?)\s*[.!?]*$"),
    re.compile(r"(?i)^(?:find\s+out|check)\s+(?P<q>.+?)\s+(?:online|on\s+the\s+(?:web|internet))\s*[.!?]*$"),
)
_TIMELY = re.compile(
    r"(?i)\b(?:latest|newest|most\s+recent|recently|right\s+now|nowadays|currently|today'?s?|tonight|yesterday|"
    r"this\s+(?:week|weekend|month|year|season)|last\s+(?:night|week|weekend|month)|breaking|news|headlines?|"
    r"price\s+of|prices?|stock\s+price|share\s+price|exchange\s+rate|market\s+cap|"
    r"scores?|fixtures?|standings|league\s+table|who\s+won|who\s+is\s+winning|winners?\s+of|results?\s+of|"
    r"elections?|polls?|release\s+date|coming\s+out|upcoming|"
    r"next\s+(?:match|game|race|election|launch|episode|season)|still\s+alive|how\s+old\s+is|net\s+worth|"
    r"current\s+(?:president|prime\s+minister|ceo|leader|champion|price|version|status|record|holder|king|queen|pope|"
    r"chancellor|governor|mayor|rate|population)|"
    r"(?<!first\s)(?<!former\s)(?:president|prime\s+minister|ceo|chancellor|pope)\s+of)\b")
_YEAR = re.compile(r"\b(19\d\d|20\d\d)\b")
_UNSURE = re.compile(
    r"(?i)\b(?:i\s+(?:do\s+not|don'?t)\s+know|i'?m\s+not\s+(?:sure|certain|aware|familiar)|i\s+am\s+not\s+(?:sure|certain|aware|familiar)|"
    r"i\s+(?:do\s+not|don'?t)\s+have\s+(?:any\s+)?(?:real[- ]time|current|up[- ]to[- ]date|live|recent|the\s+latest|access|"
    r"information|specific|enough|reliable)|(?:as\s+of|since)\s+my\s+(?:last\s+)?(?:knowledge|training)|"
    r"my\s+(?:knowledge|training)\s+(?:cut-?off|only\s+goes|is\s+limited|ends|data)|knowledge\s+cut-?off|"
    r"i\s+(?:can'?t|cannot|am\s+unable\s+to|'m\s+unable\s+to)\s+(?:browse|access\s+(?:the\s+)?(?:internet|web)|"
    r"look\s+(?:it|that|this|things)\s+up|search|check|provide\s+(?:real[- ]time|current|live|up[- ]to[- ]date)|verify|confirm)|"
    r"i\s+couldn'?t\s+find|no\s+(?:reliable\s+)?information\s+(?:about|on)|not\s+familiar\s+with|"
    r"i\s+have\s+no\s+(?:information|data|knowledge)|unable\s+to\s+(?:browse|access\s+the))")
# The owner's own things are on this computer, not on the web.
_PRIVATE = re.compile(
    r"(?i)\b(?:my|our|mine)\s+(?:own\s+)?(?:notes?|vault|files?|folders?|documents?|computer|pc|laptop|machine|screen|"
    r"passwords?|accounts?|e-?mails?|inbox|messages?|reminders?|tasks?|calendar|photos?|pictures?|downloads|desktop|"
    r"bank|cards?|address|phone|ip|router|network|settings|wi-?fi|chats?|history|missions?)\b"
    r"|\b(?:this|the)\s+(?:computer|pc|machine|laptop)\b|\bon\s+my\s+screen\b|\bin\s+my\s+(?:vault|notes)\b")
_SECRETISH = re.compile(
    r"(?i)[\w.+-]+@[\w-]+\.[\w.]+|\b(?:\d[\s-]?){9,}\b|\b\d{1,3}(?:\.\d{1,3}){3}\b|\b(?:password|passcode|passwd|pin\s+code|"
    r"api[\s_-]?key|ssh\s+key|private\s+key)\b|[A-Za-z0-9_\-]{28,}|(?:~/|/home/|/var/|/etc/|[a-z]:\\)")
_FILLER = set("a an the of to in on for is are was were be it this that with at by from as and or what what's whats "
              "who who's whom which when where why how do does did can could would should will shall tell me "
              "please about i you your my we us our is there any some".split())
_CONTEXTUAL = re.compile(r"(?i)\b(?:it|its|that|this|those|these|they|them|their|he|him|his|she|her|there|the\s+other|"
                         r"the\s+(?:first|second|third|last)\s+one|same)\b")
_WIKI = re.compile(r"(?i)^(?:who|what)\s+(?:is|are|was|were)\s+(?:a\s+|an\s+|the\s+)?(?P<s>.+?)\s*[?.!]*$"
                   r"|^(?:tell\s+me\s+about|what\s+do\s+you\s+know\s+about|define)\s+(?:a\s+|an\s+|the\s+)?(?P<t>.+?)\s*[?.!]*$")


def _core(question: str) -> str:
    return " ".join(_LEAD.sub("", question or "").split())


def explicit_query(question: str) -> str | None:
    """The words to search for when the owner asks for a search ("search for X", "look up X", "google X")."""
    core = _core(question)
    for pattern in _EXPLICIT:
        m = pattern.match(core)
        if m:
            words = " ".join(m.group("q").strip(" \"'“”").split()[:MAX_QUERY_WORDS])
            return words if words and not _secret(words) and not _PRIVATE.search(words) else None
    return None


def _secret(text: str) -> bool:
    return redact_sensitive(text) != text or bool(_SECRETISH.search(text))


def is_time_sensitive(question: str, now: datetime | None = None) -> bool:
    """Questions about now: the local model's knowledge is months old, so the web answers them."""
    text = question or ""
    years = [int(y) for y in _YEAR.findall(text)]
    this_year = (now or datetime.now()).year
    if years and max(years) < this_year - 1:
        return False                                 # "who won the 2010 world cup" is history
    return bool(_TIMELY.search(text)) or any(y >= this_year - 1 for y in years)


def sounds_unsure(answer: str) -> bool:
    """The local model's answer says it doesn't know (checked near the start, where models say so)."""
    return bool(_UNSURE.search((answer or "")[:400]))


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9'+#.-]*", (text or "").lower()) if w not in _FILLER]


def search_words(question: str, *, follow_up: bool = False) -> str | None:
    """What may be sent to a search engine for this question, or None when it must stay on this computer
    (the owner's own things, credentials, addresses, pasted text) or makes no sense on its own."""
    core = _core(question).rstrip(" ?.!")
    if not core or len(core) > 300 or _secret(core) or _PRIVATE.search(core):
        return None
    words = content_words(core)
    if not words or (follow_up and _CONTEXTUAL.search(core) and len(words) < 3):
        return None                                  # "and who won it?" means nothing without the chat before it
    return " ".join(core.split()[:MAX_QUERY_WORDS])


def wiki_subject(question: str) -> str | None:
    """The subject of a "who/what is X" style question, for Wikipedia."""
    m = _WIKI.match(_core(question))
    if not m:
        return None
    subject = (m.group("s") or m.group("t") or "").strip()
    return subject if 1 <= len(subject.split()) <= 8 and not _PRIVATE.search(subject) else None


# ---------------------------------------------------------------- answering from results

def answer_prompt(question: str, results: list[WebResult], now: datetime | None = None) -> str:
    now = now or datetime.now()
    lines = [f"[{i}] {r.title} ({r.site}): {r.snippet}" for i, r in enumerate(results, 1)]
    return (f"Web results, searched just now (today is {now.strftime('%A')} {now.day} {now.strftime('%B %Y')}):\n"
            + "\n".join(lines)
            + "\n\nAnswer from these results only, in one to three sentences. If they don't answer it, say so."
            + "\nQuestion: " + question.strip())


def sources_text(results: list[WebResult]) -> str:
    return SOURCES_HEADER + "\n".join(f"• {r.title} — {r.url}" for r in results)


def results_text(outcome: SearchOutcome) -> str:
    """The results themselves, when no model can write the answer."""
    lines = [f"• {r.title}: {r.snippet}\n  {r.url}" if r.snippet else f"• {r.title}\n  {r.url}" for r in outcome.results]
    return f"Here's what the web says ({', '.join(outcome.sources)}):\n" + "\n".join(lines)


def without_sources(answer: str) -> str:
    return (answer or "").split(SOURCES_HEADER, 1)[0]
