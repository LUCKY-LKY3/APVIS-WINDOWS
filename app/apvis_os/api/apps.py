"""Apps endpoints: what is installed, and opening one (installing stays in Home, behind the password)."""

from __future__ import annotations

from .. import appstore
from .server import ApiError, Request, route


@route("GET", "/v1/apps", "Installed apps, the catalog (with installed flags) and APVIS's own apps")
def apps(request: Request) -> None:
    request.send(200, appstore.state())


@route("POST", "/v1/apps/open", "Open an installed app by its desktop id (from GET /v1/apps)", body='{"id": "vlc"}')
def open_app(request: Request) -> None:
    app_id = request.text("id", limit=200)
    try:
        name = appstore.launch(app_id)
    except ValueError as exc:
        raise ApiError(404, "not_installed", str(exc)) from None
    request.send(200, {"ok": True, "opened": name})
