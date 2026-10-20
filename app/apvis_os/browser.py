"""APVIS Browser: the web in APVIS style, private by default, with APVIS one key away.

    python3 -m apvis_os.browser [URL or search words]

- Search goes to DuckDuckGo; typing an address goes straight there.
- Requests from a site to well-known advertising/tracking domains are blocked (the count
  shows in the address bar); third-party cookies are refused.
- The profile (history, cookies, cache) lives in ~/.local/share/apvis-os/browser.
- "Ask APVIS" (Ctrl+Shift+A) answers questions about the open page with the same brain as
  Home's Ask: this computer's models, or the owner's gaming PC when it is on. The page text
  is used only for that answer.
Needs Qt WebEngine (python3-pyside6.qtwebenginequick), which ships from image dev.26.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlsplit

QML_BROWSER = Path(__file__).resolve().parent.parent.parent.parent.parent / "share/apvis-os/qml/browser/Browser.qml"
if not QML_BROWSER.is_file():            # an installed update keeps qml/ next to its python/ folder
    QML_BROWSER = Path(__file__).resolve().parent.parent.parent / "share/qml/browser/Browser.qml"
SEARCH = "https://duckduckgo.com/?q="
DATA = Path.home() / ".local/share/apvis-os/browser"
PAGE_TEXT_LOCAL = 4500          # characters of page text the OptiPlex's small context can hold with room to answer
PAGE_TEXT_BOOST = 14000         # the gaming PC's larger context

# Well-known advertising and tracking hosts (blocked only when another site loads them).
TRACKERS = frozenset("""
doubleclick.net googlesyndication.com googleadservices.com google-analytics.com googletagmanager.com googletagservices.com
adservice.google.com analytics.google.com pagead2.googlesyndication.com stats.g.doubleclick.net
facebook.net connect.facebook.net pixel.facebook.com an.facebook.com
ads-twitter.com analytics.twitter.com static.ads-twitter.com ads.linkedin.com px.ads.linkedin.com snap.licdn.com
bat.bing.com clarity.ms c.clarity.ms adnxs.com adsrvr.org criteo.com criteo.net taboola.com outbrain.com
scorecardresearch.com quantserve.com quantcount.com hotjar.com hotjar.io mouseflow.com fullstory.com
segment.io segment.com cdn.segment.com mixpanel.com amplitude.com api.amplitude.com heap.io heapanalytics.com
branch.io app-measurement.com crashlytics.com appsflyer.com adjust.com kochava.com
moatads.com amazon-adsystem.com aax.amazon-adsystem.com rubiconproject.com pubmatic.com openx.net casalemedia.com
indexww.com smartadserver.com yieldmo.com teads.tv sharethrough.com media.net 33across.com lijit.com
tiqcdn.com tealiumiq.com demdex.net omtrdc.net everesttech.net krxd.net bluekai.com exelator.com
tapad.com rlcdn.com agkn.com mathtag.com bidswitch.net contextweb.com districtm.io gumgum.com
newrelic.com nr-data.net optimizely.com cdn.optimizely.com chartbeat.com chartbeat.net parsely.com
zemanta.com revcontent.com mgid.com propellerads.com popads.net adcash.com exoclick.com
adsafeprotected.com doubleverify.com moatpixel.com flashtalking.com serving-sys.com sizmek.com innovid.com springserve.com
spotxchange.com permutive.com permutive.app id5-sync.com liadm.com crwdcntrl.net eyeota.net zeotap.com adform.net
3lift.com triplelift.com sonobi.com seedtag.com ogury.io onetag-sys.com richaudience.com 360yield.com lngtd.com
adlightning.com confiant-integrations.net sascdn.com cxense.com imrworldwide.com bounceexchange.com wunderkind.co
addthis.com sharethis.com ad.gt dotomi.com analytics.yahoo.com ads.yahoo.com analytics.tiktok.com ads.tiktok.com
events.redditmedia.com ct.pinterest.com q.quora.com adroll.com perfectaudience.com quantcast.com gemius.pl
yieldlab.net improvedigital.com smartclip.net adition.com emxdgt.com rhythmone.com unrulymedia.com 1rx.io
""".split())


def normalize(text: str) -> str:
    """What the owner typed in the address bar -> the URL to open (an address, or a DuckDuckGo search)."""
    t = (text or "").strip()
    if not t:
        return ""
    if re.match(r"(?i)^(https?|file|about|view-source):", t):
        return t
    if " " not in t:
        host = t.split("/", 1)[0].split(":", 1)[0]
        try:
            ipaddress.ip_address(host)
            return "http://" + t
        except ValueError:
            pass
        if host == "localhost" or host.endswith((".local", ".lan", ".home", ".internal")):
            return "http://" + t
        if re.fullmatch(r"(?i)[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,24}", host):
            return "https://" + t
    return SEARCH + quote_plus(t)


def site(host: str) -> str:
    """The registrable part of a host name, roughly ("news.bbc.co.uk" -> "bbc.co.uk")."""
    parts = (host or "").lower().strip(".").split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {"co", "com", "org", "net", "ac", "gov", "edu"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_tracker(host: str, first_party: str = "") -> bool:
    """A request to a known tracker, made by a different site than the one being viewed."""
    host = (host or "").lower()
    if not host or (first_party and site(host) == site(first_party)):
        return False
    labels = host.split(".")
    return any(".".join(labels[i:]) in TRACKERS for i in range(len(labels) - 1))


class History:
    """Pages the owner visited (bounded, owner-only file) for the start page."""

    def __init__(self, path: Path | None = None, limit: int = 500) -> None:
        self.path, self.limit = path or DATA / "history.json", limit
        self._lock = threading.Lock()

    def _load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def add(self, url: str, title: str) -> None:
        if not url.startswith(("http://", "https://")) or url.startswith(SEARCH):
            return
        with self._lock:
            items = [i for i in self._load() if i.get("url") != url]
            items.insert(0, {"url": url, "title": (title or url)[:200], "at": time.time(),
                             "visits": 1 + next((i.get("visits", 0) for i in self._load() if i.get("url") == url), 0)})
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_name(self.path.name + ".tmp")
                tmp.write_text(json.dumps(items[: self.limit]), encoding="utf-8")
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
            except OSError:
                pass

    def recent(self, limit: int = 8) -> list[dict[str, Any]]:
        with self._lock:
            return [{"url": i["url"], "title": i.get("title", i["url"]), "host": urlsplit(i["url"]).hostname or ""}
                    for i in self._load()[:limit]]

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except OSError:
                pass


def page_prompt(title: str, url: str, text: str, limit: int) -> list[dict[str, str]]:
    """The page as earlier chat turns, so the question itself stays short and the page is context."""
    body = re.sub(r"\n{3,}", "\n\n", (text or "").strip())[:limit]
    return [{"role": "user", "content": f"I'm reading this web page.\nTitle: {title}\nAddress: {url}\n\n{body}"},
            {"role": "assistant", "content": "I've read the page. What would you like to know about it?"}]


def available() -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec("PySide6.QtWebEngineQuick") is not None
    except (ImportError, ValueError):
        return False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if not available():
        print("APVIS Browser needs Qt WebEngine (comes with the APVIS OS dev.26 image).", file=sys.stderr)
        return 2
    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineQuick import QQuickWebEngineProfile, QtWebEngineQuick

    QtWebEngineQuick.initialize()
    if sys.platform == "win32":        # development previews: the native Windows style ignores custom controls
        from PySide6.QtQuickControls2 import QQuickStyle
        QQuickStyle.setStyle("Fusion")
    app = QGuiApplication(argv)
    app.setApplicationName("APVIS Browser")
    app.setDesktopFileName("apvis-browser")
    app.setWindowIcon(QIcon.fromTheme("web-browser"))
    history = History()

    class Blocker(QWebEngineUrlRequestInterceptor):
        def __init__(self, bridge: "BrowserBridge") -> None:
            super().__init__()
            self.bridge = bridge

        def interceptRequest(self, info) -> None:  # noqa: N802 - Qt API
            host = info.requestUrl().host()
            first = info.firstPartyUrl().host()
            if is_tracker(host, first):
                info.block(True)
                self.bridge.count_block(first)

    class BrowserBridge(QObject):
        blockedChanged = Signal()
        historyChanged = Signal()
        answerChanged = Signal()
        _answerUpdate = Signal("QVariantMap")

        def __init__(self) -> None:
            super().__init__()
            self._blocked: dict[str, int] = {}
            self._answer: dict[str, Any] = {"state": "idle"}
            self._generation = 0
            self._answerUpdate.connect(self._apply_answer)

        def count_block(self, first_party: str) -> None:
            key = site(first_party)
            self._blocked[key] = self._blocked.get(key, 0) + 1
            self.blockedChanged.emit()

        @Property(int, notify=blockedChanged)
        def blockedTotal(self) -> int:
            return sum(self._blocked.values())

        @Slot(str, result=int)
        def blockedOn(self, host: str) -> int:
            return self._blocked.get(site(host), 0)

        @Slot(str, result=str)
        def normalize(self, text: str) -> str:
            return normalize(text)

        @Property(str, constant=True)
        def dataPath(self) -> str:
            return str(DATA)

        @Property(str, constant=True)
        def downloadPath(self) -> str:
            return str(Path.home() / "Downloads")

        @Property("QVariantList", notify=historyChanged)
        def recent(self) -> list[dict[str, Any]]:
            return history.recent(8)

        @Slot(str, str)
        def visited(self, url: str, title: str) -> None:
            history.add(url, title)
            self.historyChanged.emit()

        @Slot()
        def clearHistory(self) -> None:
            history.clear()
            self.historyChanged.emit()

        # ---- Ask APVIS about this page
        @Property("QVariantMap", notify=answerChanged)
        def answer(self) -> dict[str, Any]:
            return self._answer

        @Slot("QVariantMap")
        def _apply_answer(self, update: dict[str, Any]) -> None:
            if update.get("generation") != self._generation:
                return
            self._answer = {**self._answer, **update}
            self.answerChanged.emit()

        @Slot(str, str, str, str)
        def ask(self, question: str, title: str, url: str, text: str) -> None:
            question = (question or "").strip() or "Summarise this page in a few short points."
            self._generation += 1
            generation = self._generation
            self._answer = {"state": "thinking", "question": question, "text": "", "meta": "", "generation": generation}
            self.answerChanged.emit()

            def work() -> None:
                from .ask import AskService
                last = [0.0]

                def on_text(t: str) -> None:
                    now = time.perf_counter()
                    if now - last[0] > 0.08:
                        last[0] = now
                        self._answerUpdate.emit({"generation": generation, "state": "streaming", "text": t})

                try:
                    service = AskService()
                    limit = PAGE_TEXT_BOOST if service.boost_client("general") else PAGE_TEXT_LOCAL
                    result = service.ask(question, history=page_prompt(title, url, text, limit), on_text=on_text,
                                         cancelled=lambda: generation != self._generation)
                except (OSError, ValueError) as exc:
                    self._answerUpdate.emit({"generation": generation, "state": "error", "text": f"Ask unavailable: {exc}"})
                    return
                if result.status == "completed":
                    where = {"gaming-pc": "gaming PC", "instant": "instant"}.get(result.source, "this computer")
                    self._answerUpdate.emit({"generation": generation, "state": "done", "text": result.answer,
                                             "meta": f"{result.model} · {where} · {result.total_s:.1f} s"})
                elif result.status != "cancelled":
                    self._answerUpdate.emit({"generation": generation, "state": "error",
                                             "text": f"{result.error}. Check that Ollama is running."})

            threading.Thread(target=work, name="apvis-browser-ask", daemon=True).start()

        @Slot(QObject)
        def attachProfile(self, profile: QObject) -> None:
            """QML hands over its WebEngineProfile: add the tracker blocker and refuse third-party cookies."""
            if not isinstance(profile, QQuickWebEngineProfile):
                return
            profile.setUrlRequestInterceptor(blocker)
            try:
                profile.cookieStore().setCookieFilter(lambda request: not request.thirdParty)
            except (AttributeError, TypeError):
                pass       # older Qt: cookies follow the profile policy only
            self._profile = profile

        @Slot()
        def closeAnswer(self) -> None:
            self._generation += 1
            self._answer = {"state": "idle"}
            self.answerChanged.emit()

    bridge = BrowserBridge()
    blocker = Blocker(bridge)
    engine = QQmlApplicationEngine()
    start = normalize(" ".join(argv[1:])) if len(argv) > 1 else ""
    engine.rootContext().setContextProperty("browser", bridge)
    engine.rootContext().setContextProperty("startUrl", start)
    engine.load(QUrl.fromLocalFile(str(QML_BROWSER)))
    if not engine.rootObjects():
        return 1
    app._apvis_keep = (bridge, blocker, engine)      # noqa: SLF001 - keep Python owners alive
    smoke = os.environ.get("APVIS_BROWSER_SMOKE")   # development: save a screenshot after N ms, then quit
    if smoke:
        from PySide6.QtCore import QTimer
        path, _, delay = smoke.partition("@")
        window = engine.rootObjects()[0]
        steps = [s for s in os.environ.get("APVIS_BROWSER_SMOKE_JS", "").split("||") if s]
        for i, step in enumerate(steps):
            QTimer.singleShot(int(delay or 6000) * (i + 1) // (len(steps) + 2), lambda step=step: window.setProperty("smokeStep", step))
        QTimer.singleShot(int(delay or 6000), lambda: (window.grabWindow().save(path), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
