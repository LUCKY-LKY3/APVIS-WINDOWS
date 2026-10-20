"""The APVIS API: one local endpoint for every app and script on this computer.

    http://127.0.0.1:8765        (this computer only; never the network)   GET /v1 lists everything

Organised by area, one module each:
    server.py   plumbing: route table, safety checks, errors, stats   (/v1, /v1/stats)
    ai.py       Ask, OpenAI-compatible chat, embeddings, models, health
    home.py     steer the running Home (open a page, ask on screen)
    system.py   measurements and busiest programs (read-only)
    apps.py     installed apps and opening them
    notes.py    search the vault; propose memories (the owner accepts them)
    memory.py   V3: list and search memory, the local model queue (read-only)
Run on its own:  python3 -m apvis_os.api            (serve)
Terminal client: python3 -m apvis_os.api query "question"
"""

from __future__ import annotations

from . import ai, apps, home, memory, notes, system  # noqa: F401  (each module registers its routes)
from .home import HOME_HOOKS, HOME_PAGES, home_command
from .server import HOST, PORT, ROUTES, STATS, serve, start_background

__all__ = ["HOME_HOOKS", "HOME_PAGES", "HOST", "PORT", "ROUTES", "STATS", "home_command", "serve", "start_background"]
