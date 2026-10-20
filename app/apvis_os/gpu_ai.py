"""APVIS for Windows: local AI on the owner's gaming PC (GTX 1080 Ti 11 GB, Ryzen 5 5600).

Two things the OptiPlex never needed:

1. A desktop-GPU role profile. On Windows (or with APVIS_GPU_AI=1) the defaults prefer the bigger models the
   graphics card runs quickly, with the OptiPlex lists after them as fallbacks. APVIS_GPU_AI=0 turns it off.
   The OptiPlex (Linux) defaults in ask.DEFAULT_ROLES are untouched, and roles the owner set still win.
2. The gaming guard (owner, 2026-10-20: "use the 1080 Ti for AI but not when I need it"). While a game runs,
   Ask answers in light mode: the smallest installed model, on the CPU (num_gpu 0), unloaded soon after; and
   when a game starts, every model Ollama holds on the GPU is unloaded so the game gets all of its memory.

The decisions are small pure functions (decide, light_model, ai_status); GameGuard holds the one bit of state
the game thread sets, and unload_resident is the only part that talks to Ollama.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .ollama import InstalledModel, OllamaClient, OllamaError

# Tried first on the desktop GPU (11 GB): the first installed one per role answers; the OptiPlex lists follow.
DESKTOP_GPU_ROLES: dict[str, list[str]] = {
    "fast": ["llama3.2:3b"],
    "general": ["qwen3.5:9b", "qwen3:8b", "llama3.1:8b", "qwen2.5:7b"],
    "code": ["qwen2.5-coder:7b", "qwen3.5:9b", "qwen3:8b"],
    "deep": ["qwen3.5:9b", "qwen3:8b", "qwen3:14b", "deepseek-r1:8b"],
    "chat": ["llama3.2:3b"],
    "vision": ["qwen2.5vl:7b", "llava:7b"],
}
LIGHT_KEEP = "1m"                    # light-mode models leave RAM soon after the answer
LIGHT_NOTE = "light mode: a game is running"
_NOT_CHAT = ("embed", "minilm", "bge-", "mxbai")     # embedding models never answer questions


def desktop_gpu(platform: str | None = None, env: Mapping[str, str] | None = None) -> bool:
    """True on Windows, or wherever APVIS_GPU_AI=1; APVIS_GPU_AI=0 forces the OptiPlex profile."""
    flag = (os.environ if env is None else env).get("APVIS_GPU_AI", "").strip()
    if flag in ("0", "1"):
        return flag == "1"
    return (sys.platform if platform is None else platform) == "win32"


def default_roles(gpu: bool | None = None) -> dict[str, list[str]]:
    """The default role lists for this machine: the desktop-GPU picks first, then the OptiPlex lists."""
    from .ask import DEFAULT_ROLES
    if not (desktop_gpu() if gpu is None else gpu):
        return {role: list(models) for role, models in DEFAULT_ROLES.items()}
    out: dict[str, list[str]] = {}
    for role, models in DEFAULT_ROLES.items():
        merged: list[str] = []
        for name in (*DESKTOP_GPU_ROLES.get(role, []), *models):
            if name not in merged:
                merged.append(name)
        out[role] = merged
    return out


def is_builtin_default(role: str, models: list[str]) -> bool:
    """A saved list equal to either built-in default is not the owner's choice (save() writes every role), so
    the profile for this machine applies to it."""
    return models in (default_roles(False).get(role), default_roles(True).get(role))


# ---------------------------------------------------------------- the gaming guard
def _chat_capable(name: str) -> bool:
    return not any(mark in name.lower() for mark in _NOT_CHAT)


def light_model(installed: Iterable[InstalledModel], *, vision: Iterable[str] = (), role: str = "fast") -> str | None:
    """The smallest installed model that can answer (a vision model for picture questions); None if none."""
    wanted = set(vision)
    pool = [m for m in installed if _chat_capable(m.name) and ((m.name in wanted) == (role == "vision"))]
    if role == "vision" and not pool:
        return None
    return min(pool, key=lambda m: (m.size or float("inf"), m.name)).name if pool else None


@dataclass(frozen=True)
class Decision:
    mode: str                                   # gpu | cpu | light
    model: str | None
    options: dict[str, Any] = field(default_factory=dict)   # merged over brain.load_options()
    keep_alive: str | int | None = None         # None: the role's usual keep_alive
    note: str = ""                              # shown with the answer
    roomy: bool = False                         # a desktop-GPU pick: the gaming-PC answer budget (reasoning room)


def decide(role: str, chosen: str | None, installed: list[InstalledModel], *, game_active: bool, gpu_profile: bool,
           vision: Iterable[str] = (), pinned: bool = False) -> Decision:
    """How this computer answers `role`, given the model the role lists picked (`chosen`).

    No game: that model, as usual (on the graphics card with the desktop profile). A game running: the smallest
    installed model on the CPU (num_gpu 0, nothing goes to the graphics card), unloaded a minute later. A model
    the owner picked by name (`pinned`) is kept, but still runs on the CPU."""
    if not game_active:
        picks = {m for models in DESKTOP_GPU_ROLES.values() for m in models}
        return Decision("gpu" if gpu_profile else "cpu", chosen,
                        roomy=gpu_profile and (chosen or "").removesuffix(":latest") in picks)
    model = chosen if pinned or chosen is None else (light_model(installed, vision=vision, role=role) or chosen)
    return Decision("light", model, {"num_gpu": 0}, LIGHT_KEEP, LIGHT_NOTE)


class GameGuard:
    """Whether a game is running right now; set by Home's game thread (gamelink), read by Ask."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._name = ""

    def update(self, active: bool, name: str = "") -> str | None:
        """Record the latest game sample; "started" or "ended" when that changed, else None."""
        with self._lock:
            was, self._active, self._name = self._active, bool(active), (name if active else "")
        if self._active == was:
            return None
        return "started" if self._active else "ended"

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"active": self._active, "name": self._name}


GUARD = GameGuard()


def unload_resident(client: OllamaClient) -> list[str]:
    """Unload every model Ollama holds on the GPU (CPU-only ones may stay); returns the ones unloaded."""
    try:
        running = client.running()
    except OllamaError:
        return []
    gone: list[str] = []
    for item in running:
        name = str(item.get("name") or item.get("model") or "")
        if not name or int(item.get("size_vram", 1) or 0) <= 0:
            continue
        try:
            client.unload(name)
            gone.append(name)
        except OllamaError:
            pass
    return gone


def ai_status(route: Mapping[str, Any], *, game: Mapping[str, Any] | None = None, gpu_profile: bool | None = None,
              vision: Iterable[str] = ()) -> dict[str, Any]:
    """Home's AI line: {model, mode: gpu|cpu|light|off, reason, profile}, from the route check (home_status)
    and the game card; no Ollama call of its own."""
    gpu = desktop_gpu() if gpu_profile is None else gpu_profile
    profile = "desktop-gpu" if gpu else "optiplex"
    if route.get("checking"):
        return {"model": None, "mode": "off", "reason": "checking the local AI…", "profile": profile}
    if not route.get("reachable"):
        return {"model": None, "mode": "off", "reason": str(route.get("error") or "Ollama is not running"), "profile": profile}
    if not route.get("model"):
        return {"model": None, "mode": "off", "reason": "no Ollama model is installed", "profile": profile}
    game = game or {}
    if game.get("active"):
        installed = [InstalledModel(str(m.get("name")), int(m.get("size") or 0))
                     for m in route.get("installed") or [] if isinstance(m, Mapping) and m.get("name")]
        wanted = {v.removesuffix(":latest") for v in (vision or default_roles(gpu)["vision"])}
        seen = {m.name for m in installed if m.name.removesuffix(":latest") in wanted or m.name.split(":")[0] in wanted}
        model = light_model(installed, vision=seen) or route["model"]
        what = game.get("name") or "a game"
        return {"model": model, "mode": "light", "profile": profile,
                "reason": f"{what} is running, so Ask uses {model} on the CPU and leaves the graphics card to the game"}
    if gpu:
        return {"model": route["model"], "mode": "gpu", "profile": profile,
                "reason": "bigger models answer on the graphics card"}
    return {"model": route["model"], "mode": "cpu", "profile": profile, "reason": "answers on this computer's CPU"}
