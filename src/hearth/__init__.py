"""hearth: a qm family's contract, the members' side of it, and the coordinator template.

A coordinator delivers each fire's family block to the members it names and
keeps every outcome. hearth holds it as one text, ``hearth.coordinator``, which
an exemplar imports at a version or copies whole, and runs beside its own
code: what fires, and where it runs, are the exemplar's. ``hearth fork`` makes
and updates a copy, and ``hearth check --copy`` says whether it is still the
template.

A member says what an action changes and what its state is (``Member``). Every
host serves it the same four routes: alone on its own port (``hearth.web.app``),
beside an aiohttp page (``hearth.aio.routes``), or inside ShowRunner when it is
of the hub's own family (``hearth.showrunner.plugin``). ``hearth check URL``
judges any of them, and ``hearth check --hub URL`` a coordinator, in any
language, by the routes alone.
"""

from .member import CONFORMANCE, CONTRACT, Member, Refused, shown

__all__ = ["CONFORMANCE", "CONTRACT", "Member", "Refused", "shown"]
