"""hearth: one contract for the performing family's members, served alone or inside a hub.

A member says what an action changes and what its state is (``Member``). Every
host serves it the same four routes: alone on its own port (``hearth.web.app``),
beside an aiohttp page (``hearth.aio.routes``), or inside ShowRunner when it is
of the hub's own family (``hearth.showrunner.plugin``). ``hearth check URL`` judges
any of them, in any language, by the routes alone.
"""

from .member import CONTRACT, Member, Refused, shown

__all__ = ["CONTRACT", "Member", "Refused", "shown"]
