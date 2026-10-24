"""Is an exemplar's coordinator still hearth's template? ``hearth fork`` and ``hearth check --copy``.

An exemplar copies ``template/coordinator.py`` whole. The copy's
``Copied from:`` line names the hearth revision it was taken at, and every
other line is the template at that revision, so whether a copy is still the
template, and whether the template has changed since, are facts git states:

* ``hearth check --copy PATH`` says which a copy is: the template at its
  revision and the template now; the template at its revision, with the
  commits that changed the template since; or changed from the template, with
  the lines that differ.
* ``hearth fork PATH`` writes the template as committed at hearth's ``HEAD``
  to PATH, its line naming that revision, when PATH does not exist yet or is
  the template at its revision. It refuses a copy its owner has changed and
  says what changed, since writing over it would lose that.

Both read the template's history from hearth's own checkout: a copy is taken
from the repository at a revision, and the template is not in the package.

Exit 0: the copy is the template at its revision. 1: it is not, or names no
revision hearth's checkout has. 3: there is no checkout to read from.
"""

from __future__ import annotations

import difflib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CANNOT_SAY = 3
TEMPLATE = "template/coordinator.py"
ORIGIN = "Copied from: this is the template."
NAMED = re.compile(r"^Copied from: hearth ([0-9a-f]{7,40})\.$", re.MULTILINE)


@dataclass
class Copy:
    path: Path
    status: int
    said: str
    revision: str | None = None
    current: bool = False  # the template at its revision, and the template now
    since: list[str] = field(default_factory=list)  # the template's commits after the copy's
    changed: list[str] = field(default_factory=list)  # the copy against the template it names


def checkout() -> Path | None:
    """hearth's own checkout, when this package is running from one."""
    root = Path(__file__).resolve().parents[2]
    return root if (root / TEMPLATE).is_file() and (root / ".git").exists() else None


def _git(root: Path, *args: str) -> str | None:
    done = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True,
                          text=True, encoding="utf-8")
    return done.stdout if done.returncode == 0 else None


def check(path: str | Path, root: Path | None = None) -> Copy:
    """Whether the file at ``path`` is hearth's template at the revision it names."""
    path = Path(path)
    root = root or checkout()
    if root is None:
        return Copy(path, CANNOT_SAY, "no checkout of hearth to read the template's history from")
    text = path.read_text(encoding="utf-8")  # a checkout's CRLF is read as LF
    named = NAMED.search(text)
    if named is None:
        said = ("is the template itself" if ORIGIN in text
                else "names no hearth revision: it has no 'Copied from: hearth <revision>.' line")
        return Copy(path, 1, said)
    revision = named.group(1)
    then = _git(root, "show", f"{revision}:{TEMPLATE}")
    if then is None:
        return Copy(path, 1, f"names hearth {revision}, where hearth's checkout has no template",
                    revision)
    if text != then.replace(ORIGIN, named.group(0), 1):
        changed = list(difflib.unified_diff(
            then.replace(ORIGIN, named.group(0), 1).splitlines(), text.splitlines(),
            f"the template at {revision}", str(path), lineterm="", n=1))
        lines = sum(1 for line in changed
                    if line[:1] in "+-" and not line.startswith(("+++", "---")))
        return Copy(path, 1, f"differs from the template at {revision} in {lines} lines",
                    revision, changed=changed)
    if _git(root, "show", f"HEAD:{TEMPLATE}") == then:
        return Copy(path, 0, f"is the template at {revision}, which is the template now",
                    revision, current=True)
    since = (_git(root, "log", "--format=%h %s", f"{revision}..HEAD", "--", TEMPLATE)
             or "").splitlines()
    return Copy(path, 0, f"is the template at {revision}; the template has changed since",
                revision, since=since)


def fork(path: str | Path, root: Path | None = None) -> Copy:
    """Write the template at hearth's ``HEAD`` to ``path``, unless that would lose an owner's change."""
    path = Path(path)
    root = root or checkout()
    if root is None:
        return Copy(path, CANNOT_SAY, "no checkout of hearth to take the template from")
    head = (_git(root, "rev-parse", "--short=12", "HEAD") or "").strip()
    now = _git(root, "show", f"HEAD:{TEMPLATE}") or ""
    if not head or ORIGIN not in now:
        return Copy(path, CANNOT_SAY, f"hearth's HEAD has no template with a {ORIGIN!r} line")
    if path.exists():
        found = check(path, root)
        if found.status != 0 or found.current:
            found.said += "; nothing written"
            return found
    path.write_bytes(now.replace(ORIGIN, f"Copied from: hearth {head}.", 1).encode("utf-8"))
    return Copy(path, 0, f"is the template at {head}, written", head)
