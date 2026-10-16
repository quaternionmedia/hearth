"""A member inside ShowRunner's process: the same member, hosted as a ShowRunner plugin.

``plugin(make, name=...)`` is a pluggy plugin. Register it under ShowRunner's
``showrunner`` entry-point group, and the hub:

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
``[plugins.family.members]`` by its URL. ``plugin`` refuses a member whose
``family`` differs from ``hub_family``.

ShowRunner is imported here and nowhere else in kin, and only when a hub loads
the plugin.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import APIRouter

from .member import Member
from .web import router

HUB_FAMILY = "show-control"


def plugin(make: Callable[[dict], Member], *, name: str, family: str,
           description: str = "", version: str = "0",
           pages: Callable[[Callable[[], Member | None]], Iterable[APIRouter]] | None = None,
           hub_family: str = HUB_FAMILY) -> object:
    """A ShowRunner plugin hosting the member ``make`` returns."""
    if family != hub_family:
        raise ValueError(f"{name} is in {family}, not the hub's {hub_family}: two families "
                         "meet across a protocol, so serve it alone and name its URL in "
                         "[plugins.family.members]")
    import showrunner

    class Hosted:
        """{name}, a member of {family}, hosted in the hub's process."""

        def __init__(self) -> None:
            self.member: Member | None = None

        @showrunner.hookimpl
        def showrunner_register(self):
            return {"name": name, "description": description, "version": version}

        @showrunner.hookimpl
        def showrunner_startup(self, app):
            config = getattr(app, "config", None)
            settings = config.plugins.settings.get(name, {}) if config is not None else {}
            member = make(settings or {})
            member.start()
            self.member = member

        @showrunner.hookimpl
        def showrunner_shutdown(self, app):
            if self.member is not None:
                self.member.stop()
            self.member = None

        @showrunner.hookimpl
        def showrunner_get_routes(self):
            # Mounted before startup makes the member: the routes find it per request.
            outer = APIRouter(prefix=f"/{name}")
            outer.include_router(router(lambda: self.member))
            for page in (pages(lambda: self.member) if pages else ()):
                outer.include_router(page)
            return outer

        @showrunner.hookimpl
        def showrunner_family_members(self):
            if self.member is None:
                return None
            return {name: self.member.receive}

        @showrunner.hookimpl
        def showrunner_get_nav(self):
            return None

    Hosted.__name__ = f"{name.capitalize()}Hosted"
    Hosted.__doc__ = Hosted.__doc__.format(name=name, family=family)
    return Hosted()
