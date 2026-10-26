"""An exemplar's copy of the template: made by ``hearth fork``, judged by ``hearth check --copy``.

Each test has a hearth of its own, a git repository holding a template with
the template's ``Copied from:`` line, so its history is the test's to write.
The last test forks hearth's real template and checks the copy.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from hearth import conformance, copies

TEMPLATE = '"""A coordinator.\n\nCopied from: this is the template.\n"""\n\nTIMEOUT = 5.0\n'


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def commit(repo: Path, text: str, subject: str, path: str = copies.TEMPLATE) -> str:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_bytes(text.encode("utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", subject)
    return _git(repo, "rev-parse", "--short=12", "HEAD")


def line(revision: str, text: str = TEMPLATE) -> str:
    return copies.LINE.format(revision=revision, digest=copies.digest(text))


@pytest.fixture()
def hearth(tmp_path):
    repo = tmp_path / "hearth"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    _git(repo, "config", "commit.gpgsign", "false")
    commit(repo, TEMPLATE, "the template")
    return repo


@pytest.fixture()
def copy(hearth, tmp_path):
    """A copy forked from the fixture's hearth at its first revision."""
    made = tmp_path / "coordinator.py"
    assert copies.fork(made, hearth).status == 0
    return made


def untouched(path: Path):
    """The file's bytes and times, to show that nothing wrote it."""
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    return path.read_bytes(), path.stat().st_mtime_ns


# --- what fork writes ----------------------------------------------------------

def test_a_fork_is_the_template_naming_the_revision_and_the_text_it_was_taken_at(
        hearth, tmp_path):
    """Mutation: fork writes the working tree's template, or leaves the line -- red here."""
    (hearth / copies.TEMPLATE).write_text("uncommitted\n", encoding="utf-8")
    head = _git(hearth, "rev-parse", "--short=12", "HEAD")
    made = tmp_path / "coordinator.py"

    forked = copies.fork(made, hearth)

    assert forked.status == 0 and forked.revision == head
    assert made.read_text(encoding="utf-8") == TEMPLATE.replace(copies.ORIGIN, line(head))
    found = copies.check(made, hearth)
    assert found.status == 0 and found.current, found.said


def test_the_copy_shows_by_itself_that_it_is_the_template_its_line_names(copy):
    """What an exemplar's own test does, with nothing of hearth: put the template's line back."""
    text = copy.read_text(encoding="utf-8")
    named = copies.NAMED.search(text)

    assert copies.digest(text.replace(named.group(0), copies.ORIGIN)) == named.group(2)


def test_fork_and_check_say_when_no_remote_off_this_machine_holds_the_revision(
        hearth, tmp_path):
    """A remote on this machine, a clone's own origin say, is no place to read it from.

    Mutation: any remote-tracking ref taken as published -- red here.
    """
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(hearth, "remote", "add", "near", str(remote))
    _git(hearth, "push", "-q", "near", "main")
    alone = copies.fork(tmp_path / "alone.py", hearth)
    checked = copies.check(tmp_path / "alone.py", hearth)
    _git(hearth, "remote", "add", "forge", "https://forge.invalid/hearth.git")
    _git(hearth, "update-ref", "refs/remotes/forge/main", "HEAD")  # as a fetch leaves it

    published = copies.fork(tmp_path / "published.py", hearth)

    assert not alone.published and "no remote of hearth off this machine holds" in alone.said
    assert not checked.published and "no remote of hearth off this machine" in checked.said
    assert published.published and "remote" not in published.said
    assert copies.check(tmp_path / "published.py", hearth).published


def test_fork_takes_the_newer_template_into_a_copy_its_owner_has_not_changed(hearth, copy):
    newer = commit(hearth, TEMPLATE.replace("5.0", "4.0"), "a shorter timeout")

    taken = copies.fork(copy, hearth)

    assert taken.status == 0 and taken.revision == newer
    assert "TIMEOUT = 4.0" in copy.read_text(encoding="utf-8")
    assert copies.check(copy, hearth).current


def test_fork_leaves_a_copy_that_is_already_the_template_now_as_it_is(hearth, copy):
    """Mutation: fork writes a current copy again -- red here (its time moves)."""
    before = untouched(copy)

    again = copies.fork(copy, hearth)

    assert again.status == 0 and again.said.endswith("nothing written")
    assert (copy.read_bytes(), copy.stat().st_mtime_ns) == before


def test_fork_will_not_take_a_copy_back_to_an_older_template(hearth, tmp_path):
    """A checkout of hearth behind the copy: on another branch, or a stale clone.

    Mutation: no ancestry check, so fork writes HEAD's older template -- red here.
    """
    _git(hearth, "switch", "-q", "-c", "newer")
    commit(hearth, TEMPLATE.replace("5.0", "3.0"), "a shorter timeout")
    made = tmp_path / "coordinator.py"
    copies.fork(made, hearth)
    _git(hearth, "switch", "-q", "main")
    before = untouched(made)

    found = copies.check(made, hearth)
    refused = copies.fork(made, hearth)

    assert found.status == 0 and found.outside and not found.since, found.said
    assert "does not descend from" in found.said
    assert refused.said.endswith("nothing written")
    assert (made.read_bytes(), made.stat().st_mtime_ns) == before


def test_fork_writes_nothing_where_there_is_no_file_to_write(hearth, tmp_path):
    assert copies.fork(tmp_path / "missing" / "coordinator.py", hearth).status == 1
    assert copies.fork(tmp_path, hearth).status == 1
    assert not (tmp_path / "missing").exists()


# --- what check says --------------------------------------------------------------

def test_a_copy_behind_the_template_is_still_the_template_and_says_what_changed_it_since(
        hearth, copy):
    """Mutation: since lists every commit, not the template's -- red here."""
    commit(hearth, "notes\n", "a note beside the template", path="NOTES.md")
    commit(hearth, TEMPLATE.replace("5.0", "4.0"), "a shorter timeout")

    found = copies.check(copy, hearth)

    assert found.status == 0 and not found.current and not found.outside
    assert "changed since" in found.said
    assert [entry.split(" ", 1)[1] for entry in found.since] == ["a shorter timeout"]


@pytest.mark.parametrize("change", [
    pytest.param(lambda text: text.replace("5.0", "9.0"), id="a value"),
    pytest.param(lambda text: text + "TIMEOUT = 0.1\n", id="a line appended"),
    pytest.param(lambda text: text.replace("TIMEOUT = 5.0", "TIMEOUT  =  5.0"), id="spacing"),
    pytest.param(lambda text: text.rstrip("\n"), id="no newline at the end"),
    pytest.param(lambda text: "\ufeff" + text, id="a byte-order mark"),
])
def test_a_copy_its_owner_changed_is_not_the_template_and_fork_will_not_write_over_it(
        hearth, copy, change):
    """Mutations: compare by position, ignore spacing or the last newline, or let fork write
    anyway -- each red here."""
    copy.write_bytes(change(copy.read_text(encoding="utf-8")).encode("utf-8"))
    commit(hearth, TEMPLATE.replace("5.0", "4.0"), "a shorter timeout")
    before = untouched(copy)

    found = copies.check(copy, hearth)
    refused = copies.fork(copy, hearth)

    assert found.status == 1 and "differs from the template" in found.said, found.said
    assert found.changed and "0 of its lines taken out, 0 put in" not in found.said
    assert refused.status == 1 and refused.said.endswith("nothing written")
    assert (copy.read_bytes(), copy.stat().st_mtime_ns) == before


def test_a_changed_line_is_counted_once_on_each_side(hearth, copy):
    copy.write_text(copy.read_text(encoding="utf-8").replace("5.0", "9.0"), encoding="utf-8")

    found = copies.check(copy, hearth)

    assert found.said.endswith("1 of its lines taken out, 1 put in")
    assert "-TIMEOUT = 5.0" in found.changed and "+TIMEOUT = 9.0" in found.changed


def test_a_copy_checked_out_with_crlf_line_endings_is_still_the_template(hearth, copy):
    copy.write_bytes(copy.read_bytes().replace(b"\n", b"\r\n"))

    assert copies.check(copy, hearth).current


def test_a_copy_whose_line_names_another_text_is_not_the_template(hearth, copy):
    text = copy.read_text(encoding="utf-8")
    named = copies.NAMED.search(text)
    copy.write_text(text.replace(named.group(2), "0" * 16), encoding="utf-8")

    assert copies.check(copy, hearth).status == 1


@pytest.mark.parametrize("text, said", [
    (TEMPLATE, "is the template itself"),
    (TEMPLATE.replace(copies.ORIGIN, ""), "names no hearth revision"),
    (TEMPLATE.replace(copies.ORIGIN, line("0123ab")), "names no hearth revision"),
    (TEMPLATE.replace(copies.ORIGIN, line("0123456789ab")[:-2] + "."),
     "names no hearth revision"),
    (TEMPLATE.replace(copies.ORIGIN, line("0123456789ab")[:-1] + "0."),
     "names no hearth revision"),
])
def test_a_file_that_names_no_revision_of_hearth_is_not_a_copy(hearth, tmp_path, text, said):
    """Mutations: a revision of fewer than seven digits, or a digest of other than sixteen,
    taken for a line -- each red here."""
    named = tmp_path / "coordinator.py"
    named.write_text(text, encoding="utf-8")

    found = copies.check(named, hearth)

    assert found.status == 1 and found.said.startswith(said), found.said


@pytest.mark.parametrize("revision", ["0123456789ab", "deadbeef"])
def test_a_revision_hearth_s_checkout_does_not_hold_is_judged_by_the_digest_alone(
        hearth, tmp_path, revision):
    """A stale clone, or a name that resolves to some other commit: ``deadbeef`` is a branch
    here. The text is the template's when hearth knows its digest, and cannot be said when
    hearth does not."""
    _git(hearth, "branch", "deadbeef")
    named = tmp_path / "coordinator.py"
    named.write_text(TEMPLATE.replace(copies.ORIGIN, line(revision)), encoding="utf-8")

    unknown = copies.check(named, hearth, known=())
    known = copies.check(named, hearth, known=(copies.digest(TEMPLATE),))

    assert unknown.status == copies.CANNOT_SAY, unknown.said
    assert f"does not hold {revision}" in unknown.said
    assert known.status == 0 and not known.current, known.said
    assert known.said.startswith("is a text hearth's template has had")


@pytest.mark.parametrize("make", [
    pytest.param(lambda path: None, id="no file"),
    pytest.param(lambda path: path.mkdir(), id="a directory"),
    pytest.param(lambda path: path.write_bytes(b"\xff\xfe not utf-8"), id="not utf-8"),
])
def test_what_is_no_text_file_is_said_to_be_none(hearth, tmp_path, make):
    path = tmp_path / "coordinator.py"
    make(path)

    found = copies.check(path, hearth)

    assert found.status == 1 and found.said.startswith("is no text file"), found.said


# --- without hearth's history -------------------------------------------------------

@pytest.mark.parametrize("without", ["no checkout", "a shallow clone", "no git"])
def test_without_hearth_s_history_the_copy_s_digest_still_says_whether_it_changed(
        hearth, copy, tmp_path, monkeypatch, without):
    """Hearth installed from a release, a CI clone at depth 1, or no git on the path."""
    root = None
    monkeypatch.setattr(copies, "checkout", lambda: None)
    if without == "a shallow clone":
        commit(hearth, TEMPLATE.replace("5.0", "4.0"), "a shorter timeout")
        root = tmp_path / "shallow"
        _git(tmp_path, "clone", "-q", "--depth", "1", hearth.as_uri(), str(root))
    if without == "no git":
        def no_git(*args, **kwargs):
            raise FileNotFoundError("git")
        monkeypatch.setattr(copies.subprocess, "run", no_git)
        root = hearth

    known = (copies.digest(TEMPLATE),)
    found = copies.check(copy, root, known)
    unknown = copies.check(copy, root, known=())
    copy.write_text(copy.read_text(encoding="utf-8").replace("5.0", "9.0"), encoding="utf-8")
    changed = copies.check(copy, root, known)

    assert found.status == 0 and "by its digest" in found.said, found.said
    assert not found.current
    assert unknown.status == copies.CANNOT_SAY and "does not know" in unknown.said
    assert changed.status == 1 and "has changed since it was copied" in changed.said
    assert copies.fork(tmp_path / "other.py", root).status == copies.CANNOT_SAY
    assert not (tmp_path / "other.py").exists()


def test_a_text_made_up_to_agree_with_its_own_line_is_not_the_template(tmp_path, monkeypatch):
    """The copy's digest ties it to itself; only ``KNOWN`` ties it to hearth.

    Mutation: a digest that agrees with its own copy taken as the template's -- red here.
    """
    monkeypatch.setattr(copies, "checkout", lambda: None)
    made_up = TEMPLATE + 'import os\nos.system("anything")\n'
    named = tmp_path / "coordinator.py"
    named.write_text(made_up.replace(copies.ORIGIN, line("0000000000aa", made_up)),
                     encoding="utf-8")

    assert copies.check(named).status == copies.CANNOT_SAY


def test_hearth_knows_the_digest_of_its_template_as_it_stands():
    """A change to the template adds its digest to ``KNOWN``, so a release knows every text."""
    root = copies.checkout()
    if root is None:
        pytest.fail("this test runs from hearth's checkout, where the template is")
    now = copies.digest((root / copies.TEMPLATE).read_text(encoding="utf-8"))

    assert copies.KNOWN[-1] == now, f"add {now!r} to copies.KNOWN"


def test_a_copy_whose_line_has_no_digest_yet_is_taken_into_the_line_as_it_is_now(
        hearth, tmp_path, monkeypatch):
    """Mutation: the earlier line refused, so a copy made before the digest is stranded."""
    earlier = tmp_path / "coordinator.py"
    head = _git(hearth, "rev-parse", "--short=12", "HEAD")
    earlier.write_text(TEMPLATE.replace(copies.ORIGIN, f"Copied from: hearth {head}."),
                       encoding="utf-8")
    found = copies.check(earlier, hearth)

    taken = copies.fork(earlier, hearth)

    assert found.status == 0 and not found.current and "earlier form" in found.said
    assert taken.status == 0 and copies.check(earlier, hearth).current
    monkeypatch.setattr(copies, "checkout", lambda: None)
    earlier.write_text(TEMPLATE.replace(copies.ORIGIN, f"Copied from: hearth {head}."),
                       encoding="utf-8")
    assert copies.check(earlier).status == copies.CANNOT_SAY


def test_hearth_s_checkout_is_found_only_where_its_history_is(tmp_path, monkeypatch):
    """Mutation: checkout() ignores .git -- red here."""
    package = tmp_path / "src" / "hearth"
    package.mkdir(parents=True)
    (tmp_path / "template").mkdir()
    (tmp_path / copies.TEMPLATE).write_text(TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(copies, "__file__", str(package / "copies.py"))
    assert copies.checkout() is None

    (tmp_path / ".git").mkdir()
    assert copies.checkout() == tmp_path.resolve()


# --- the commands ---------------------------------------------------------------

def test_check_copy_never_writes_and_says_what_it_found(hearth, copy, monkeypatch, capsys):
    """Mutations: check dispatched to fork, its exit always 0, or the since and changed lines
    left unprinted -- each red here."""
    monkeypatch.setattr(copies, "checkout", lambda: hearth)
    commit(hearth, TEMPLATE.replace("5.0", "4.0"), "a shorter timeout")
    before = untouched(copy)

    assert conformance.main(["check", "--copy", str(copy)]) == 0
    behind = capsys.readouterr().out
    assert (copy.read_bytes(), copy.stat().st_mtime_ns) == before
    copy.write_text(copy.read_text(encoding="utf-8").replace("5.0", "9.0"), encoding="utf-8")
    assert conformance.main(["check", "--copy", str(copy)]) == 1
    changed = capsys.readouterr().out

    assert "since:" in behind and "a shorter timeout" in behind
    assert "-TIMEOUT = 5.0" in changed and "+TIMEOUT = 9.0" in changed


def test_fork_exits_1_when_it_will_not_write_and_says_what_to_do(hearth, tmp_path, monkeypatch,
                                                                capsys):
    """Mutations: a refused fork exiting 0, or a copy outside HEAD's history given no
    advice -- each red here."""
    monkeypatch.setattr(copies, "checkout", lambda: hearth)
    _git(hearth, "switch", "-q", "-c", "newer")
    commit(hearth, TEMPLATE.replace("5.0", "3.0"), "a shorter timeout")
    made = tmp_path / "coordinator.py"
    copies.fork(made, hearth)
    _git(hearth, "switch", "-q", "main")

    assert conformance.main(["check", "--copy", str(made)]) == 0
    assert "fork it again from a checkout of hearth whose HEAD holds" in capsys.readouterr().out
    made.write_text(made.read_text(encoding="utf-8") + "# mine\n", encoding="utf-8")
    assert conformance.main(["fork", str(made)]) == 1
    assert "nothing written" in capsys.readouterr().out


def test_check_takes_a_hub_or_a_copy_never_both(capsys):
    with pytest.raises(SystemExit):
        conformance.main(["check", "--copy", "--hub", "http://127.0.0.1:1"])
    assert "not allowed with" in capsys.readouterr().err


def test_hearth_forks_its_own_template_and_judges_the_copy(tmp_path, capsys):
    """The commands an exemplar runs, against hearth's own checkout."""
    if copies._history(copies.checkout()) is None:
        pytest.fail("fork needs hearth's checkout with all of its history: clone without "
                    "--depth, or check out with fetch-depth 0")
    made = tmp_path / "coordinator.py"

    assert conformance.main(["fork", str(made)]) == 0
    assert conformance.main(["check", "--copy", str(made)]) == 0
    assert "which is the template now" in capsys.readouterr().out
