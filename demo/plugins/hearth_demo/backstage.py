"""Loopback, the demo's show, backstage: its members kept running, the show made, the checks run.

``[plugins.loopback]`` in the hub's show.toml says what the show is::

    [plugins.loopback]
    hub = "http://127.0.0.1:18700"
    script = "demo/show/loopback.fountain"
    cues = "demo/show/cues.toml"
    copy = "<ShowRunner>/src/showrunner/plugins/family/coordinator.py"
    logs = "<work>/logs"

    [[plugins.loopback.members]]
    name = "carlos"
    command = ["uv", "run", "--project", "<carlos>", "carlos", "serve", "..."]
    cwd = "<carlos>"
    url = "http://127.0.0.1:18720"
    page = "http://127.0.0.1:18720/rack"
    check = { turn = "front" }   # hearth check sends it this; {} checks its routes only

Each member named there runs in its own process, kept running by
``hearth.supervise``; ``ready = "/"`` marks a page with no routes of its own.
The show is made through the hub's own routes once the hub answers, unless the
hub already holds a show of its name. This module imports nothing of
ShowRunner: ``show`` is the plugin that runs it.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import tomllib

from hearth import conformance, copies
from hearth.supervise import Spec, Supervisor, kill_tree

NAME = "Loopback"  # the show's name in the hub
# What a member's process is started without: the hub's own environment, which
# would point uv at ShowRunner's project rather than the member's.
CLEAN = {"VIRTUAL_ENV": None, "PYTHONPATH": None, "UV_PROJECT_ENVIRONMENT": None}


def cues(path: Path) -> list[dict]:
    """The cues in ``cues.toml``, in their order."""
    return tomllib.loads(path.read_text(encoding="utf-8"))["cue"]


def specs(members: list[dict]) -> list[Spec]:
    """What the supervisor keeps running, from ``[[plugins.loopback.members]]``."""
    return [Spec(m["name"], [str(word) for word in m["command"]], m["url"], cwd=m.get("cwd"),
                 env=CLEAN, ready=m.get("ready", "/family/identity")) for m in members]


def make_show(hub: str, script: Path, cue_file: Path, *, wait: float = 120.0,
              say: Callable[[str], None] = print) -> int | None:
    """The show, made through the hub's own routes once it answers: its id, or None when
    the hub already holds one of its name or never answered."""
    deadline = time.monotonic() + wait
    with httpx.Client(base_url=hub, timeout=10) as api:
        while True:
            try:
                shows = api.get("/db/shows")
                if shows.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                say(f"loopback: the hub did not answer at {hub} within {wait:g}s; no show made")
                return None
            time.sleep(0.25)
        if any(show.get("name") == NAME for show in shows.json()):
            say(f"loopback: the hub already holds {NAME!r}")
            return None

        def made(method: str, path: str, **kwargs) -> dict:
            answer = api.request(method, path, **kwargs)
            answer.raise_for_status()
            return answer.json()

        text = script.read_text(encoding="utf-8")
        show = made("POST", "/db/shows", params={"name": NAME})["id"]
        made("POST", f"/db/shows/{show}/scripts",
             json={"title": NAME, "format": "fountain", "content": text})
        cue_list = made("POST", f"/db/shows/{show}/cue-lists", json={"name": "Main"})["id"]
        lines = text.splitlines()
        for cue in cues(cue_file):
            made("POST", f"/db/cue-lists/{cue_list}/cues",
                 json={"number": cue["number"], "name": cue["name"], "layer": cue["layer"],
                       "notes": cue["notes"], "actions": {"family": cue["family"]},
                       "script_line": next(i for i, line in enumerate(lines, 1)
                                           if line.startswith(cue["line"])),
                       "script_char": 0})
        say(f"loopback: {NAME!r} is made: its script at {hub}/script, GO at {hub}/programmer")
        return show


def copy_row(path: Path) -> dict:
    """Whether the hub's coordinator is still hearth's template, as a check's row."""
    copy = copies.check(path)
    return {"what": "the hub's coordinator", "url": str(path), "status": copy.status,
            "verdict": copy.said if copy.status == 0 else "is not the template",
            "failed": "" if copy.status == 0 else copy.said}


def report_row(what: str, url: str, report: conformance.Report) -> dict:
    return {"what": what, "url": url, "status": report.status,
            "verdict": "conforms" if report.status == 0 else "does not conform",
            "failed": "; ".join(f.what for f in report.findings if not f.ok)}


class Show:
    """The show's members, kept running, and what the stagehand reaches backstage."""

    def __init__(self, settings: dict, say: Callable[[str], None] = print) -> None:
        self.settings, self.say = settings, say
        logs = settings.get("logs")
        self.supervisor = Supervisor(specs(settings.get("members", [])),
                                     logs=Path(logs) if logs else None, log=say)

    def start(self) -> None:
        self.supervisor.start()
        if self.settings.get("script") and self.settings.get("cues"):
            threading.Thread(target=make_show, name="loopback-show", daemon=True,
                             args=(self.settings["hub"], Path(self.settings["script"]),
                                   Path(self.settings["cues"])),
                             kwargs={"say": self.say}).start()

    def stop(self) -> None:
        self.supervisor.stop()

    # --- what the stagehand reaches -------------------------------------------

    def running(self) -> list[str]:
        return list(self.supervisor.watched)

    def knock_over(self, name: str) -> None:
        process = self.supervisor.watched[name].process
        if process is not None:
            kill_tree(process)

    def check(self) -> list[dict]:
        """hearth's checks of every member served alone, of the hub, and of its coordinator.

        The hub is checked without ``--pull``: a read of a pull member's route
        is a delivery, and would take one from the page that follows it.
        """
        rows = [report_row(f"{m['name']}, served alone", m["url"],
                           conformance.check(m["url"], m["check"] or None))
                for m in self.settings.get("members", []) if "check" in m]
        hub = self.settings["hub"]
        rows.append(report_row("the hub", hub, conformance.check_hub(hub)))
        if self.settings.get("copy"):
            rows.append(copy_row(Path(self.settings["copy"])))
        return rows


class Waiting:
    """The show the stagehand reaches, found when it acts: the plugins start in either order."""

    def __init__(self, find: Callable[[], Show | None]) -> None:
        self.find = find

    def running(self) -> list[str]:
        show = self.find()
        return show.running() if show is not None else []

    def knock_over(self, name: str) -> None:
        self.find().knock_over(name)

    def check(self) -> list[dict]:
        return self.find().check()
