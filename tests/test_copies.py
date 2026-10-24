"""An exemplar's copy of the template: made by ``hearth fork``, judged by ``hearth check --copy``.

Each test has a hearth of its own, a git repository holding a template with
the template's ``Copied from:`` line, so its history is the test's to write.
The last test forks hearth's real template and checks the copy.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hearth import conformance, copies

TEMPLATE = '"""A coordinator.\n\nCopied from: this is the template.\n"""\n\nTIMEOUT = 5.0\n'


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def commit(repo: Path, text: str, subject: str) -> str:
    (repo / "template").mkdir(exist_ok=True)
    (repo / copies.TEMPLATE).write_bytes(text.encode("utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", subject)
    return _git(repo, "rev-parse", "--short=12", "HEAD")


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


def test_a_fork_is_the_template_naming_the_revision_it_was_taken_at(hearth, tmp_path):
    """Mutation: fork writes the working tree's template, or leaves the line -- red here."""
    (hearth / copies.TEMPLATE).write_text("uncommitted\n", encoding="utf-8")
    head = _git(hearth, "rev-parse", "--short=12", "HEAD")
    copy = tmp_path / "coordinator.py"

    made = copies.fork(copy, hearth)

    assert made.status == 0 and made.revision == head
    assert copy.read_text(encoding="utf-8") == TEMPLATE.replace(
        copies.ORIGIN, f"Copied from: hearth {head}.")
    found = copies.check(copy, hearth)
    assert found.status == 0 and found.current, found.said


def test_a_copy_behind_the_template_is_still_the_template_and_says_what_changed_since(
        hearth, tmp_path):
    copy = tmp_path / "coordinator.py"
    copies.fork(copy, hearth)
    commit(hearth, TEMPLATE.replace("5.0", "4.0"), "a shorter timeout")

    found = copies.check(copy, hearth)

    assert found.status == 0 and not found.current
    assert "changed since" in found.said
    assert [line.split(" ", 1)[1] for line in found.since] == ["a shorter timeout"]


def test_fork_takes_the_newer_template_into_a_copy_its_owner_has_not_changed(hearth, tmp_path):
    copy = tmp_path / "coordinator.py"
    copies.fork(copy, hearth)
    newer = commit(hearth, TEMPLATE.replace("5.0", "4.0"), "a shorter timeout")

    taken = copies.fork(copy, hearth)

    assert taken.status == 0 and taken.revision == newer
    assert "TIMEOUT = 4.0" in copy.read_text(encoding="utf-8")
    assert copies.check(copy, hearth).current


def test_a_copy_its_owner_changed_is_not_the_template_and_fork_will_not_write_over_it(
        hearth, tmp_path):
    """Mutation: compare only the lines the template has, or let fork write anyway -- red here."""
    copy = tmp_path / "coordinator.py"
    copies.fork(copy, hearth)
    changed = copy.read_text(encoding="utf-8").replace("5.0", "9.0")
    copy.write_text(changed, encoding="utf-8")
    commit(hearth, TEMPLATE.replace("5.0", "4.0"), "a shorter timeout")

    found = copies.check(copy, hearth)
    refused = copies.fork(copy, hearth)

    assert found.status == 1 and "differs from the template" in found.said
    assert "-TIMEOUT = 5.0" in found.changed and "+TIMEOUT = 9.0" in found.changed
    assert refused.status == 1 and refused.said.endswith("nothing written")
    assert copy.read_text(encoding="utf-8") == changed


def test_a_copy_checked_out_with_crlf_line_endings_is_still_the_template(hearth, tmp_path):
    copy = tmp_path / "coordinator.py"
    copies.fork(copy, hearth)
    copy.write_bytes(copy.read_bytes().replace(b"\n", b"\r\n"))

    assert copies.check(copy, hearth).current


@pytest.mark.parametrize("text, said", [
    (TEMPLATE, "is the template itself"),
    (TEMPLATE.replace(copies.ORIGIN, ""), "names no hearth revision"),
    (TEMPLATE.replace(copies.ORIGIN, "Copied from: hearth 0123456789ab."),
     "names hearth 0123456789ab, where hearth's checkout has no template"),
])
def test_a_file_that_names_no_revision_of_hearth_is_not_a_copy(hearth, tmp_path, text, said):
    copy = tmp_path / "coordinator.py"
    copy.write_text(text, encoding="utf-8")

    found = copies.check(copy, hearth)

    assert found.status == 1 and found.said.startswith(said)


def test_with_no_checkout_of_hearth_neither_can_say(tmp_path, monkeypatch):
    monkeypatch.setattr(copies, "checkout", lambda: None)
    copy = tmp_path / "coordinator.py"

    assert copies.fork(copy).status == copies.CANNOT_SAY
    assert not copy.exists()


def test_hearth_forks_its_own_template_and_judges_the_copy(tmp_path, capsys):
    """The commands an exemplar runs, against hearth's own checkout."""
    if copies.checkout() is None:
        pytest.fail("these tests run from hearth's checkout, where the template's history is")
    copy = tmp_path / "coordinator.py"

    assert conformance.main(["fork", str(copy)]) == 0
    assert conformance.main(["check", "--copy", str(copy)]) == 0
    assert "which is the template now" in capsys.readouterr().out
