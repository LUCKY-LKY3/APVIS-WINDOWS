"""Guest mode (V4 login screen): the "guest" account may look around, nothing is saved.

The login screen (apvis_os.greeter) offers two accounts: APVIS (the owner, administrator) and Guest.
Guest is an ordinary local account with no password and no admin rights. The system enforces the limits
(no sudo, polkit gives guest nothing: etc/polkit-1/rules.d/49-apvis-guest.rules, no SSH, the home folder
is emptied at every boot and every guest login); Home only stops offering what Guest can't do and
refuses those calls (shell_app), so nothing a guest does is kept.
"""
from __future__ import annotations

import functools
import getpass
import os
from typing import Any, Callable

GUEST_USER = "guest"
# Power actions a guest may take from Home: only ending their own session. Restart and shut down are
# at the login screen, which anyone at the computer can use.
GUEST_POWER = frozenset({"logout"})
MESSAGE = "Guest can look around, but can't change this. Sign in as APVIS to do that."


def session_user() -> str:
    """The account this Home runs as ("" when it can't be told)."""
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return os.environ.get("USER", "")


def is_guest(user: str | None = None) -> bool:
    return (session_user() if user is None else user) == GUEST_USER


@functools.lru_cache(maxsize=1)
def this_session_is_guest() -> bool:
    """The account never changes while Home runs, so it is looked up once."""
    return is_guest()


def power_allowed(action: str, guest: bool) -> bool:
    """Guest may only log out; the owner may use every power action Home has."""
    return action in GUEST_POWER if guest else True


def refusal(what: str = "") -> str:
    """The plain-words answer when Guest asks for something only the owner may do."""
    return f"{what}: {MESSAGE}" if what else MESSAGE


def owner_only(what: str, guest: Callable[[], bool] | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """For Home bridge slots that change something: for Guest, say why (the bridge's _error) and do nothing.
    Goes directly above the def, under @Slot, so Qt still sees the slot's own signature."""
    def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def slot(self: Any, *args: Any, **kwargs: Any) -> Any:
            if (guest or this_session_is_guest)():
                report = getattr(self, "_error", None)
                if callable(report):
                    report(refusal(what))
                return None
            return fn(self, *args, **kwargs)
        return slot
    return wrap
