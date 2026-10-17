"""A member inside ShowRunner's process: the same member, hosted as a ShowRunner plugin.

``plugin(make, name=..., family=...)`` is a pluggy plugin. Register it under
ShowRunner's ``showrunner`` entry-point group, and the hub:

* asks the hub what it is (``showrunner_hub_identity``) and hosts the member
  only if the hub declares what hosting needs and is of the member's family;
* makes the member at startup from its ``[plugins.<name>]`` table in show.toml
  (``make(settings)``), and stops it at shutdown;
* serves its contract routes under ``/<name>/family/*`` -- so the member is
  reachable over HTTP inside the hub exactly as it is alone, and the
  conformance check passes against ``<hub>/<name>`` as against its own port;
* serves the member's own pages under ``/<name>``: ``pages(get)`` returns
  routers that find the member with ``get()``, since it is made after they mount;
* hands ShowFamily the member's ``receive`` through ``showrunner_family_members``,
  so a cue that names it is delivered by a call in the hub's process rather
  than a request, and is audited at ``GET /family/`` as ``via: "local"``.

**Only a member of the hub's own family is hosted this way.** A family's
border is what its members drive, and two families meet across a protocol,
never an import: a member of another family is served alone and named in
``[plugins.family.members]`` by its URL. The hub says which family it is in;
kin does not assume it.

**A member that cannot start is not ready, and the hub runs on.** Its routes
answer 503 saying why, the hub audits cues to it as errors, and the start is
tried again after 1, 2, 4… seconds, up to ``RETRY_CAP``, until it succeeds or
the hub stops -- a device plugged in late is picked up without a restart. A
hub that cannot host the member at all (it predates the hooks, or it is of
another family) is said so once, and the member is never started.

ShowRunner is imported here and nowhere else in kin, and only when a hub loads
the plugin.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable

from fastapi import APIRouter

from .member import Member
from .web import router

RETRY_FIRST = 1.0  # seconds before the first retry of a start that failed
RETRY_CAP = 30.0  # the longest wait between two tries
NEEDS = ("showrunner_hub_identity", "showrunner_family_members")


def _declared(pm, hook: str) -> bool:
    caller = getattr(pm.hook, hook, None) if pm is not None else None
    return caller is not None and caller.spec is not None


def plugin(make: Callable[[dict], Member], *, name: str, family: str,
           description: str = "", version: str = "0",
           pages: Callable[[Callable[[], Member | None]], Iterable[APIRouter]] | None = None,
           log: Callable[[str], None] | None = None) -> object:
    """A ShowRunner plugin hosting the member ``make`` returns."""
    import showrunner

    say = log or logging.getLogger("kin").warning
    note = log or logging.getLogger("kin").info  # good news is not a warning

    class Hosted:
        """{name}, a member of {family}, hosted in the hub's process."""

        def __init__(self) -> None:
            self.member: Member | None = None
            self.why = f"{name} has not started"
            self.tries = 0
            self._settings: dict = {}
            self._retry: threading.Timer | None = None
            self._lock = threading.Lock()
            self._stopped = False

        # --- the hub, as kin finds it ---------------------------------------

        @showrunner.hookimpl
        def showrunner_register(self):
            return {"name": name, "description": description, "version": version}

        @showrunner.hookimpl
        def showrunner_startup(self, app):
            pm = getattr(app, "pm", None)
            missing = [hook for hook in NEEDS if not _declared(pm, hook)]
            if missing:
                self.why = (f"{name} is not hosted: this hub does not declare "
                            f"{', '.join(missing)}, so it cannot host a member")
                say(self.why)
                return
            hub = pm.hook.showrunner_hub_identity() or {}
            if hub.get("family") != family:
                self.why = (f"{name} is not hosted: it is in {family}, the hub in "
                            f"{hub.get('family')!r}; two families meet across a protocol, "
                            "so serve it alone and name its URL in [plugins.family.members]")
                say(self.why)
                return
            config = getattr(app, "config", None)
            self._settings = (config.plugins.settings.get(name, {}) if config is not None
                              else {}) or {}
            self._stopped = False
            self._try()

        def _try(self) -> None:
            with self._lock:
                if self._stopped or self.member is not None:
                    return
                self.tries += 1
                try:
                    member = make(self._settings)
                    member.start()
                except Exception as exc:  # noqa: BLE001 -- not ready, never the hub's failure
                    wait = min(RETRY_FIRST * 2 ** (self.tries - 1), RETRY_CAP)
                    reason = f"{name} is not ready: {type(exc).__name__}: {exc}"
                    if not self.why.startswith(reason):  # said once, until the reason changes
                        say(f"{reason}; trying again, at most every {RETRY_CAP:g}s")
                    self.why = f"{reason} (try {self.tries}; next in {wait:g}s)"
                    self._retry = threading.Timer(wait, self._try)
                    self._retry.daemon = True
                    self._retry.start()
                    return
                self.member = member
                if self.tries > 1:
                    note(f"{name} is ready, at try {self.tries}")
                self.why = ""

        @showrunner.hookimpl
        def showrunner_shutdown(self, app):
            with self._lock:
                self._stopped = True
                if self._retry is not None:
                    self._retry.cancel()
                member, self.member = self.member, None
            if member is not None:
                member.stop()

        @showrunner.hookimpl
        def showrunner_get_routes(self):
            # Mounted before startup makes the member: the routes find it per request.
            outer = APIRouter(prefix=f"/{name}")
            outer.include_router(router(lambda: self.member, why=lambda: self.why))
            for page in (pages(lambda: self.member) if pages else ()):
                outer.include_router(page)
            return outer

        @showrunner.hookimpl
        def showrunner_family_members(self):
            # Found at each call, so the hub may ask before this plugin's startup
            # has made the member, and a cue that comes first is answered 503.
            return {name: self.receive}

        def receive(self, body):
            member = self.member
            if member is None:
                return 503, {"ok": False, "error": self.why}
            return member.receive(body)

        @showrunner.hookimpl
        def showrunner_get_nav(self):
            return None

    Hosted.__name__ = f"{name.capitalize()}Hosted"
    Hosted.__doc__ = Hosted.__doc__.format(name=name, family=family)
    hosted = Hosted()
    # ShowRunner disables an external plugin by this name, so it is the member's.
    hosted.__name__ = name
    return hosted
