"""Is an exemplar's coordinator hearth's template? ``hearth fork`` and ``hearth check --copy``.

An exemplar copies ``template/coordinator.py`` whole. The copy's ``Copied from:``
line names the hearth revision it was taken at and the template's text there,
by the first sixteen hex digits of its sha256, and every other line is the
template at that revision. An exemplar's own tests, with nothing of hearth,
can say that the copy still agrees with its line, which catches a change made
by hand or by a formatter. Whether the text is one hearth's template has had,
hearth says: ``KNOWN`` lists every digest the template has had, so a release
of hearth judges a copy without the history. Whether the template has changed
since is a fact hearth's history states:

* ``hearth check --copy PATH`` says which a copy is: the template at its
  revision and the template now; the template at its revision, with the commits
  that changed the template since; or changed from the template, with the lines
  that differ when hearth's history is there to show them. Without the history,
  or without the revision the copy names (hearth installed from a release, a
  shallow clone, a stale one), it says from the digest whether the copy is a
  text the template has had, and cannot say for a digest it does not know.
* ``hearth fork PATH`` writes the template as committed at hearth's ``HEAD`` to
  PATH, when PATH does not exist yet or is the template at a revision ``HEAD``
  descends from. It refuses a copy its owner has changed, since writing over it
  would lose that, and a copy taken at a revision ``HEAD`` does not descend
  from, since writing over it could take it back to an older template. It
  takes a copy whose line is in its earlier form, with no digest, into the
  form it has now. Both say when no remote of hearth off this machine holds
  the revision, since only this machine can then read what the copy names.

The digest is not a signature: whoever can change the copy can change its
line, and only ``KNOWN`` or the history says the text is the template's.

Exit 0: the copy is the template's text, at the revision its line names when
the history can say so, whether or not the template has changed since. 1: it is
not, it is not a copy, or ``fork`` would not write. 3: it cannot be said here:
a digest this hearth does not know, or no checkout with history to fork from.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CANNOT_SAY = 3
TEMPLATE = "template/coordinator.py"
ORIGIN = "Copied from: this is the template."
LINE = "Copied from: hearth {revision}, sha256 {digest}."
NAMED = re.compile(r"^Copied from: hearth ([0-9a-f]{7,40}), sha256 ([0-9a-f]{16})\.$",
                   re.MULTILINE)
EARLIER = re.compile(r"^Copied from: hearth ([0-9a-f]{7,40})\.$", re.MULTILINE)  # no digest
# A remote off this machine: one a copy's maintainer can read the revision from.
OFF_MACHINE = re.compile(r"^(https?|ssh|git)://|^[\w.-]+@[\w.-]+:")
# Every text the template has had since a copy's line named it by digest, oldest
# first. A commit that changes the template adds its digest here, and a test is
# red until it does, so a release of hearth knows every template up to its own.
KNOWN = ("daa4d36d4c5344f1",)


@dataclass
class Copy:
    path: Path
    status: int
    said: str
    revision: str | None = None
    current: bool = False  # the template at its revision, and the template now
    outside: bool = False  # its revision is not in the history of hearth's HEAD
    published: bool = True  # a remote of hearth off this machine holds its revision
    since: list[str] = field(default_factory=list)  # the template's commits after the copy's
    changed: list[str] = field(default_factory=list)  # the copy against the template it names


def digest(template: str) -> str:
    """The template's text, as the copy's line names it: its sha256's first sixteen hex digits."""
    return hashlib.sha256(template.encode("utf-8")).hexdigest()[:16]


def checkout() -> Path | None:
    """hearth's own checkout, when this package is running from one."""
    root = Path(__file__).resolve().parents[2]
    return root if (root / TEMPLATE).is_file() and (root / ".git").exists() else None


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True,
                              text=True, encoding="utf-8")
    except OSError:  # no git to run
        return None
    return done.stdout if done.returncode == 0 else None


def _history(root: Path | None) -> Path | None:
    """``root`` when it is a checkout of hearth with all of its history, else None."""
    if root is None:
        return None
    shallow = _git(root, "rev-parse", "--is-shallow-repository")
    return root if shallow is not None and shallow.strip() == "false" else None


def _published(root: Path, revision: str) -> bool:
    """Whether a remote of hearth off this machine holds ``revision``."""
    for remote in (_git(root, "remote") or "").split():
        url = (_git(root, "remote", "get-url", remote) or "").strip()
        if OFF_MACHINE.match(url) and _git(root, "for-each-ref", "--contains", revision,
                                           f"refs/remotes/{remote}"):
            return True
    return False


def _unpublished(revision: str) -> str:
    return f"; no remote of hearth off this machine holds {revision}, so only here can it be read"


def _lines(text: str) -> list[str]:
    """The text's lines, with git's mark when no newline ends the last, so a diff shows it."""
    lines = text.split("\n")
    last = lines.pop()
    return lines + [last, "\\ No newline at end of file"] if last else lines


def check(path: str | Path, root: Path | None = None,
          known: tuple[str, ...] | None = None) -> Copy:
    """Whether the file at ``path`` is hearth's template at the revision it names."""
    path = Path(path)
    known = KNOWN if known is None else known
    try:
        text = path.read_text(encoding="utf-8")  # a checkout's CRLF is read as LF
    except (OSError, UnicodeDecodeError) as exc:
        return Copy(path, 1, f"is no text file to read ({type(exc).__name__})")
    named = NAMED.search(text) or EARLIER.search(text)
    if named is None:
        said = ("is the template itself" if ORIGIN in text else "names no hearth revision: "
                f"it has no {LINE.format(revision='<revision>', digest='<digest>')!r} line")
        return Copy(path, 1, said)
    revision, digested = named.group(1), (named.groups() + (None,))[1]
    template = text.replace(named.group(0), ORIGIN, 1)
    root = _history(checkout() if root is None else root)
    full = (_git(root, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}") or ""
            ).strip() if root else ""
    then = _git(root, "show", f"{full}:{TEMPLATE}") if root and full.startswith(revision) \
        else None
    if then is None:
        # Nothing here holds the revision: the digest is all there is to go by.
        where = (f"this checkout of hearth does not hold {revision}: fetch it to say more"
                 if root else "with no checkout of hearth's history here, the revision is "
                 "not read")
        if digested is None:
            return Copy(path, CANNOT_SAY, f"names hearth {revision} in the line's earlier form, "
                                          f"with no digest, and {where}", revision)
        if digest(template) != digested:
            return Copy(path, 1, f"is not the template at {revision}: its text has changed "
                                 "since it was copied", revision)
        if digested not in known:
            return Copy(path, CANNOT_SAY, "names a digest this hearth does not know, a newer "
                                          f"hearth's template or none; {where}", revision)
        return Copy(path, 0, f"is a text hearth's template has had, by its digest; {where}",
                    revision)
    if template != then:
        changed = list(difflib.unified_diff(_lines(then), _lines(template),
                                            f"the template at {revision}", str(path),
                                            lineterm="", n=1))
        out = sum(1 for line in changed if line[:1] == "-" and not line.startswith("---"))
        put = sum(1 for line in changed if line[:1] == "+" and not line.startswith("+++"))
        return Copy(path, 1, f"differs from the template at {revision}: {out} of its lines "
                             f"taken out, {put} put in", revision, changed=changed)
    published = _published(root, full)
    late = "" if published else _unpublished(revision)
    if digested is None:
        return Copy(path, 0, f"is the template at {revision}, its line in the earlier form with "
                             f"no digest: hearth fork writes the line as it is now{late}",
                    revision, published=published)
    if digest(then) != digested:
        return Copy(path, 1, f"is the template at {revision}, but its line names another "
                             "text's digest", revision)
    if _git(root, "show", f"HEAD:{TEMPLATE}") == then:
        return Copy(path, 0, f"is the template at {revision}, which is the template now{late}",
                    revision, current=True, published=published)
    if _git(root, "merge-base", "--is-ancestor", full, "HEAD") is None:
        return Copy(path, 0, f"is the template at {revision}, which hearth's HEAD does not "
                             f"descend from{late}", revision, outside=True, published=published)
    since = (_git(root, "log", "--format=%h %s", f"{full}..HEAD", "--", TEMPLATE)
             or "").splitlines()
    return Copy(path, 0, f"is the template at {revision}; the template has changed since{late}",
                revision, since=since, published=published)


def fork(path: str | Path, root: Path | None = None) -> Copy:
    """Write the template at hearth's ``HEAD`` to ``path``, unless that loses or undoes a change."""
    path = Path(path)
    root = _history(checkout() if root is None else root)
    if root is None:
        return Copy(path, CANNOT_SAY, "no checkout of hearth, with its history, to take the "
                                      "template from; nothing written")
    head = (_git(root, "rev-parse", "--short=12", "HEAD") or "").strip()
    now = _git(root, "show", f"HEAD:{TEMPLATE}") or ""
    if not head or ORIGIN not in now:
        return Copy(path, CANNOT_SAY, f"hearth's HEAD has no template with a {ORIGIN!r} line; "
                                      "nothing written")
    if path.is_dir() or not path.parent.is_dir():
        return Copy(path, 1, "is a directory, or in none that exists; nothing written")
    if path.exists():
        found = check(path, root)
        if found.status != 0 or found.current or found.outside:
            found.said += "; nothing written"
            return found
    path.write_bytes(now.replace(ORIGIN, LINE.format(revision=head, digest=digest(now)), 1)
                     .encode("utf-8"))
    published = _published(root, "HEAD")
    said = f"is the template at {head}, written" + ("" if published else _unpublished(head))
    return Copy(path, 0, said, head, current=True, published=published)
