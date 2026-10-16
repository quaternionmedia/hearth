"""The walkthrough is run by the ordinary test command, and each page says what it needs."""

from pathlib import Path

WALKTHROUGH = Path(__file__).resolve().parent.parent / "walkthrough"


def pages():
    return sorted(WALKTHROUGH.glob("[0-9][0-9]-*.md"))


def test_there_is_a_walkthrough():
    assert pages()


def test_every_page_says_what_it_needs_to_run():
    for page in pages():
        opening = " ".join(page.read_text(encoding="utf-8").splitlines()[:4])
        assert "Runtime" in opening, f"{page.name} does not declare its runtime"


def test_every_page_runs_something():
    for page in pages():
        assert ">>> " in page.read_text(encoding="utf-8"), f"{page.name} runs nothing"
