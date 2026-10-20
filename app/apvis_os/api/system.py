"""System endpoints: this computer's real measurements (read-only)."""

from __future__ import annotations

import threading
import time

from .. import hostinfo
from ..home_status import quick_status
from ..telemetry import Telemetry
from .server import ApiError, Request, route

_TELEMETRY = Telemetry()
_PRIMED = threading.Event()        # CPU use per program needs two readings; the first call takes both


@route("GET", "/v1/system", "CPU, memory, disk, network and uptime, measured now")
def system(request: Request) -> None:
    quick = quick_status()
    quick.pop("net", None)
    request.send(200, {"status": quick, "host": {k: v for k, v in hostinfo.host_info().items() if isinstance(v, (str, int, float))}})


@route("GET", "/v1/system/processes", "The busiest programs right now (?limit=10)")
def processes(request: Request) -> None:
    try:
        limit = max(1, min(50, int(request.query.get("limit", "10"))))
    except ValueError:
        raise ApiError(400, "bad_limit", "limit is a number from 1 to 50") from None
    if not _PRIMED.is_set():
        _TELEMETRY.sample(detail=True)
        time.sleep(0.6)
        _PRIMED.set()
    sample = _TELEMETRY.sample(detail=True)
    if not sample.get("available"):
        raise ApiError(503, "unavailable", "measurements aren't available on this computer")
    request.send(200, {"processes": (sample.get("processes") or [])[:limit]})
