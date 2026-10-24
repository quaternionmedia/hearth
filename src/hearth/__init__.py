"""hearth: the coordinator of a qm family, and the contract its members keep.

A coordinator delivers each fire's family block to the members it names and
keeps every outcome. hearth holds it as a template, ``template/coordinator.py``
outside this package, which an exemplar copies and owns: what fires, and where
it runs, are the exemplar's, and ShowRunner is the first.

A member says what an action changes and what its state is (``Member``). Every
host serves it the same four routes: alone on its own port (``hearth.web.app``),
beside an aiohttp page (``hearth.aio.routes``), or inside ShowRunner when it is
of the hub's own family (``hearth.showrunner.plugin``). ``hearth check URL``
judges any of them, and ``hearth check --hub URL`` a coordinator, in any
language, by the routes alone.
"""

from .member import CONTRACT, Member, Refused, shown

__all__ = ["CONTRACT", "Member", "Refused", "shown"]
