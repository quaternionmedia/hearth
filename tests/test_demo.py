"""Loopback, the demo's show: its script and cues, the show.toml it runs on, and its plugins.

None of these runs ShowRunner or a member: what they make is checked here, and
the show itself runs from ``demo/loopback.py``.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI

import hearth
from hearth import conformance, copies, testing

# The show runs where ShowRunner does, on Python 3.11 or later, which reads TOML.
tomllib = pytest.importorskip("tomllib")

DEMO = Path(__file__).resolve().parents[1] / "demo" / "loopback.py"
PLUGINS = DEMO.parent / "plugins"
SHOW = DEMO.parent / "show"


@pytest.fixture(scope="module")
def demo():
    spec = importlib.util.spec_from_file_location("loopback", DEMO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the show ------------------------------------------------------------------------


def test_every_cue_sits_on_a_line_of_the_script_and_names_only_the_show_s_members():
    from hearth_demo import backstage

    lines = (SHOW / "loopback.fountain").read_text(encoding="utf-8").splitlines()
    members = {"showstopper", "carlos", "joe", "leo", "metronome", "rack", "stagehand"}
    cues = backstage.cues(SHOW / "cues.toml")

    assert [cue["number"] for cue in cues] == list(range(1, len(cues) + 1))
    for cue in cues:
        on = [text for text in lines if text.startswith(cue["line"])]
        assert len(on) == 1, f"cue {cue['number']} sits on {len(on)} lines: {cue['line']!r}"
        assert set(cue["family"]) <= members, f"cue {cue['number']} names {set(cue['family'])}"
        assert cue["notes"] and cue["layer"] in {"Clock", "Sound", "Stage"}


def test_the_show_does_every_act_on_a_cue():
    """What Loopback shows, each a GO: a refusal, a device plugged in, a member knocked
    over and back, and the checks."""
    from hearth_demo import backstage

    acts = [cue["family"] for cue in backstage.cues(SHOW / "cues.toml")]
    stagehand = [block["stagehand"] for block in acts if "stagehand" in block]

    assert stagehand == [{"plug": "metronome"}, {"crash": "carlos"}, {"check": "the family"}]
    assert any("rack" in block for block in acts) and any("metronome" in block for block in acts)
    crashed = next(i for i, block in enumerate(acts) if "stagehand" in block
                   and "crash" in block["stagehand"])
    assert "carlos" in acts[crashed + 1], "the cue after carlos falls names it again"


def test_the_demo_s_page_lists_the_show_s_cues_as_cues_toml_holds_them():
    """``docs/demo.md``'s table of the show, row by row: a cue renamed, moved, added or taken
    out is red here until the page says so."""
    from hearth_demo import backstage

    page = (DEMO.parents[1] / "docs" / "demo.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\d+) (.+?) \| (.+?) \|", page, re.MULTILINE)

    assert [(int(number), name, line) for number, name, line in rows] == [
        (cue["number"], cue["name"], cue["line"]) for cue in backstage.cues(SHOW / "cues.toml")]


def test_the_show_is_made_through_the_hub_s_routes_once_and_not_again():
    from hearth_demo import backstage

    made: list[tuple[str, dict]] = []
    shows: list[dict] = []
    api = FastAPI()

    @api.get("/db/shows")
    def listed():
        return shows

    @api.post("/db/shows")
    def show(name: str):
        shows.append({"id": 1, "name": name})
        return {"id": 1}

    @api.post("/db/shows/{show}/scripts")
    def script(show: int, body: dict):
        made.append(("script", body))
        return {"id": 1}

    @api.post("/db/shows/{show}/cue-lists")
    def cue_list(show: int, body: dict):
        return {"id": 2}

    @api.post("/db/cue-lists/{cue_list}/cues")
    def cue(cue_list: int, body: dict):
        made.append(("cue", body))
        return {"id": len(made)}

    with testing.serving(api) as hub:
        first = backstage.make_show(hub, SHOW / "loopback.fountain", SHOW / "cues.toml",
                                    say=lambda text: None)
        again = backstage.make_show(hub, SHOW / "loopback.fountain", SHOW / "cues.toml",
                                    say=lambda text: None)

    cues = [body for kind, body in made if kind == "cue"]
    lines = (SHOW / "loopback.fountain").read_text(encoding="utf-8").splitlines()
    assert (first, again) == (1, None)
    assert made[0] == ("script", {"title": backstage.NAME, "format": "fountain",
                                  "content": (SHOW / "loopback.fountain").read_text(
                                      encoding="utf-8")})
    assert len(cues) == len(backstage.cues(SHOW / "cues.toml"))
    for body in cues:
        assert set(body["actions"]) == {"family"}
        assert lines[body["script_line"] - 1].startswith(
            next(c["line"] for c in backstage.cues(SHOW / "cues.toml")
                 if c["number"] == body["number"]))


# --- ShowRunner as itself ---------------------------------------------------------


def shims(path: Path, plugin: bool) -> list[str]:
    """What in a file would shim ShowRunner, by line.

    A plugin is loaded by ShowRunner and may import it, as every plugin does; the
    demo's script may not, by name or otherwise, and imports no ``importlib``.
    Neither adds to ``sys.path``, sets or deletes anything on a module it
    imported or on a name bound to one, or calls what does so by name
    (``setattr``, ``import_module``, ``exec``, ``vars``).

    A tripwire for the plain forms, not a proof: a method that changes what it
    is called on (``.clear()``, ``.update()``) passes it, as does a change made
    to a hook's arguments. The script holds no ShowRunner object to call one
    on, since all it does is start ShowRunner by its own command.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found, modules = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            modules |= {(alias.asname or alias.name).split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
            modules |= {alias.asname or alias.name for alias in node.names}
            if node.module == "sys" and any(alias.name == "path" for alias in node.names):
                found.append(f"{node.lineno}: sys.path imported")
        else:
            names = []
        if not plugin and any(name.split(".")[0] == "showrunner" for name in names):
            found.append(f"{node.lineno}: imports ShowRunner")
        if not plugin and any(name.split(".")[0] == "importlib" for name in names):
            found.append(f"{node.lineno}: imports importlib")
        if isinstance(node, ast.Attribute) and node.attr == "path" \
                and isinstance(node.value, ast.Name) and node.value.id == "sys":
            found.append(f"{node.lineno}: sys.path")
        if isinstance(node, ast.Call):
            called = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if called in {"setattr", "delattr", "import_module", "__import__", "exec", "eval",
                          "vars", "globals"}:
                found.append(f"{node.lineno}: {called}()")
    bound = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
             and isinstance(node.value, ast.Name)]
    for _ in bound:  # a name bound to a module is the module: ``alias = family``
        modules |= {target.id for node in bound if node.value.id in modules
                    for target in node.targets if isinstance(target, ast.Name)}
    for node in ast.walk(tree):
        targets = (node.targets if isinstance(node, (ast.Assign, ast.Delete))
                   else [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else [])
        for target in targets:
            root = target
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            if target is not root and isinstance(root, ast.Name) and root.id in modules:
                found.append(f"{node.lineno}: sets {ast.unparse(target)}")
    return found


def test_the_demo_runs_showrunner_and_neither_imports_nor_patches_it():
    """ShowRunner is the one app: the script only starts it, and what runs inside it, the
    demo's plugins and hearth's host, patches nothing.

    Mutations: ``import showrunner``, ``importlib.import_module("showrunner...")``
    under any name, ``from sys import path``, ``setattr`` or ``vars()`` on a
    module, or a module attribute set, through an alias or not, in the script or
    a plugin -- each red here.
    """
    inside = [*sorted(PLUGINS.rglob("*.py")), Path(hearth.__file__).parent / "showrunner.py"]

    assert shims(DEMO, plugin=False) == []
    for path in inside:
        assert shims(path, plugin=True) == [], path.name


def test_the_demo_runs_nothing_of_its_own_beside_the_show(demo):
    """No page, no supervisor, no server of the demo's: the script waits on ShowRunner."""
    tree = ast.parse(DEMO.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom)}

    assert not imported & {"fastapi", "uvicorn", "httpx", "hearth", "threading"}


def test_the_hub_is_showrunner_s_own_command_with_the_show_s_plugins_beside_it(demo, tmp_path):
    dev = tmp_path / "dev"
    command = demo.hub(dev, tmp_path / "work", 18700)

    start = command.index("-m")
    assert command[start:start + 4] == ["-m", "showrunner.cli", "start", "--config"]
    beside = [command[i + 1] for i, word in enumerate(command) if word == "--with-editable"]
    assert beside == [str(demo.HEARTH), str(PLUGINS), str(dev / "ShowStopper")]
    assert command[command.index("--project") + 1] == str(dev / "ShowRunner")
    # Installed afresh: a cached build keeps the entry points it was built with.
    assert command[command.index("--reinstall-package") + 1] == "hearth-demo-plugins"
    assert Path(command[command.index("--config") + 1]).is_file()


def test_the_hub_s_show_toml_sets_up_the_show_as_show_toml_does(demo, tmp_path):
    """ShowRunner reads it as it reads any show.toml: each plugin's table is its own."""
    dev, work = tmp_path / "dev", tmp_path / "work"
    said = tomllib.loads(demo.show_toml(dev, work, 18700))
    plugins = said["plugins"]

    assert said["server"] == {"host": "127.0.0.1", "port": 18700}
    assert plugins["disabled"] == ["showstopper"]  # the clock runs beside the hub
    assert plugins["family"]["pull"] == ["leo"]
    assert plugins["family"]["members"] == {
        "showstopper": "http://127.0.0.1:18710", "carlos": "http://127.0.0.1:18720",
        "joe": "http://127.0.0.1:18731"}
    device = (work / "beat-box.device").as_posix()
    assert plugins["metronome"] == {"device": device}
    assert plugins["stagehand"] == {"devices": {"metronome": device}}
    loopback = plugins["loopback"]
    assert loopback["hub"] == "http://127.0.0.1:18700"
    assert Path(loopback["script"]).is_file() and Path(loopback["cues"]).is_file()
    assert loopback["copy"] == (dev / "ShowRunner" / demo.COPY).as_posix()
    assert [m["name"] for m in loopback["members"]] == ["showstopper", "carlos", "joe", "leo"]
    # What cue 8 sends each to time it; leo is a page, with no routes of its own to check.
    assert [m.get("check") for m in loopback["members"]] == [
        {"clock": "lap"}, {"turn": "front"}, {}, None]
    assert loopback["members"] == demo.members(dev, work, 18700)


def test_the_show_keeps_running_each_member_its_table_names(demo, tmp_path):
    from hearth_demo import backstage

    rows = demo.members(tmp_path / "dev", tmp_path / "work", 18700)
    specs = backstage.specs(rows)

    assert [spec.name for spec in specs] == ["showstopper", "carlos", "joe", "leo"]
    assert all(spec.env == backstage.CLEAN for spec in specs)
    assert [spec.ready for spec in specs] == ["/family/identity"] * 3 + ["/"]
    assert specs[2].url == "http://127.0.0.1:18731"  # joe answers the hub on its API
    assert [spec.command[:6] for spec in specs][1] == [
        "uv", "run", "--no-sync", "--project", str(tmp_path / "dev" / "carlos"), "carlos"]


def test_the_demo_s_plugins_are_found_through_showrunner_s_entry_points():
    declared = tomllib.loads((PLUGINS / "pyproject.toml").read_text(encoding="utf-8"))
    points = declared["project"]["entry-points"]["showrunner"]
    assert points == {"loopback": "hearth_demo.show:Loopback",
                      "metronome": "hearth_demo.hosted:metronome",
                      "rack": "hearth_demo.hosted:rack",
                      "stagehand": "hearth_demo.hosted:stagehand"}

    for module in ("hearth_demo.hosted", "hearth_demo.show"):
        sys.modules.pop(module, None)
    with testing.showrunner_hub():
        from hearth_demo import hosted, show

        assert show.Loopback.__name__.lower() == "loopback"  # what [plugins] disabled matches
        for name, value in points.items():
            if value.startswith("hearth_demo.hosted"):
                assert getattr(hosted, value.split(":")[1]).__name__ == name
    for module in ("hearth_demo.hosted", "hearth_demo.show"):
        sys.modules.pop(module, None)


# --- the hosted members ------------------------------------------------------------


def test_the_metronome_is_not_ready_until_its_device_is_there(tmp_path):
    from hearth_demo.members import Metronome

    device = tmp_path / "beat-box.device"
    metronome = Metronome(device)

    with pytest.raises(OSError, match="no MIDI clock device"):
        metronome.start()
    device.write_text("plugged in", encoding="utf-8")
    metronome.start()
    assert metronome.receive({"cue": {"number": "2"}, "action": {"beat": 120}})[0] == 200
    assert metronome.receive({"cue": {"number": "3"}, "action": {"beat": 9}}) == \
        (422, {"ok": False, "error": "a beat is 20 to 300 bpm, not 9"})
    assert metronome.state() == {"bpm": 120, "beats": 1}


def test_the_rack_is_of_another_family_than_the_hub():
    from hearth_demo.members import Metronome, Rack

    assert Rack.family == "instruments" != Metronome.family
    assert isinstance(Rack(), hearth.Member)


class Backstage:
    def __init__(self):
        self.knocked: list[str] = []

    def running(self):
        return ["carlos", "joe"]

    def knock_over(self, name):
        self.knocked.append(name)

    def check(self):
        return [{"what": "carlos, served alone", "verdict": "conforms", "failed": ""}]


def test_the_stagehand_does_one_act_a_cue_and_says_each(tmp_path):
    from hearth_demo.members import Stagehand

    device, backstage, said = tmp_path / "beat-box.device", Backstage(), []
    hand = Stagehand({"metronome": device}, backstage, say=said.append)
    cue = {"number": "4"}

    assert hand.receive({"cue": cue, "action": {"plug": "metronome"}})[0] == 200
    assert hand.receive({"cue": cue, "action": {"crash": "carlos"}})[0] == 200
    status, answer = hand.receive({"cue": cue, "action": {"check": "the family"}})

    assert device.read_text(encoding="utf-8") == "plugged in"
    assert backstage.knocked == ["carlos"]
    assert status == 200 and answer["state"]["checked"][0]["verdict"] == "conforms"
    assert said == ["stagehand: metronome's device is plugged in",
                    "stagehand: carlos knocked over; its supervisor brings it back",
                    "hearth check carlos, served alone: conforms"]


@pytest.mark.parametrize("action, error", [
    ({"plug": "rack"}, "there is no device of 'rack' to plug in"),
    ({"crash": "leo"}, "'leo' is not a member the show keeps running"),
    ({"plug": "metronome", "crash": "carlos"}, "the stagehand does one thing a cue, not 2"),
    ({"sweep": "stage"}, "stagehand does not take 'sweep'"),
])
def test_the_stagehand_refuses_what_it_cannot_reach(tmp_path, action, error):
    from hearth_demo.members import Stagehand

    backstage = Backstage()
    hand = Stagehand({"metronome": tmp_path / "beat-box.device"}, backstage, say=lambda t: None)

    status, answer = hand.receive({"cue": {"number": "6"}, "action": action})

    assert status == 422 and error in answer["error"]
    assert backstage.knocked == [] and not (tmp_path / "beat-box.device").exists()


def test_a_member_the_show_keeps_running_is_knocked_over_and_brought_back(tmp_path):
    from hearth_demo import backstage

    show = backstage.Show({"hub": "http://127.0.0.1:9", "members": [
        {"name": "sleeper", "command": [sys.executable, "-c", "import time; time.sleep(60)"],
         "url": "http://127.0.0.1:9"}]}, say=lambda text: None)
    show.supervisor.backoff = lambda restarts: 0.1
    show.start()
    try:
        watched = show.supervisor.watched["sleeper"]
        first = until(lambda: watched.process)

        show.knock_over("sleeper")

        assert first.poll() is not None
        assert until(lambda: watched.process if watched.process is not first else None)
        assert watched.exits and show.running() == ["sleeper"]
    finally:
        show.stop()


def until(found, within: float = 15.0):
    """What ``found`` returns once it returns something, within ``within`` seconds."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        value = found()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"not within {within:g}s")


SLEEPER = {"name": "sleeper", "command": [sys.executable, "-c", "import time; time.sleep(60)"],
           "url": "http://127.0.0.1:9"}


@pytest.fixture()
def plugins():
    """The demo's plugin modules, imported against a stand-in hub, and forgotten after."""
    modules = ("hearth_demo.show", "hearth_demo.hosted")
    for module in modules:
        sys.modules.pop(module, None)
    with testing.showrunner_hub() as hub:
        from hearth_demo import hosted, show

        yield hub, show, hosted
        show.running = None
    for module in modules:
        sys.modules.pop(module, None)


def test_the_show_s_plugin_keeps_its_members_from_the_hub_s_startup_to_its_shutdown(plugins):
    """Mutation: the members left running at the hub's shutdown -- red here."""
    hub, show, _ = plugins
    hub.register(show.Loopback(), name="loopback")
    app = testing.hub_app(hub, {"loopback": {"hub": "http://127.0.0.1:9",
                                             "members": [SLEEPER]}})

    hub.hook.showrunner_startup(app=app)
    try:
        assert show.running is not None and show.running.running() == ["sleeper"]
        process = until(lambda: show.running.supervisor.watched["sleeper"].process)
    finally:
        hub.hook.showrunner_shutdown(app=app)

    assert show.running is None and process.poll() is not None


def test_a_hub_with_no_loopback_table_starts_a_show_of_nothing(plugins):
    hub, show, _ = plugins
    hub.register(show.Loopback(), name="loopback")
    app = testing.hub_app(hub)

    hub.hook.showrunner_startup(app=app)
    try:
        assert show.running.running() == []
    finally:
        hub.hook.showrunner_shutdown(app=app)


def test_the_stagehand_is_hosted_in_the_hub_and_reaches_the_show_that_is_running(plugins,
                                                                                tmp_path):
    """The hosted plugin as ShowRunner loads it: its devices from its table, and the show it
    knocks members over in found when it acts, whichever plugin started first."""
    hub, show, hosted = plugins
    hub.register(hosted.stagehand, name="stagehand")
    device = tmp_path / "beat-box.device"
    app = testing.hub_app(hub, {"stagehand": {"devices": {"metronome": str(device)}}})
    hub.hook.showrunner_startup(app=app)
    receive = {name: call for answer in hub.hook.showrunner_family_members()
               for name, call in answer.items()}["stagehand"]
    cue = {"number": "4"}
    try:
        assert receive({"cue": cue, "action": {"plug": "metronome"}})[0] == 200
        assert device.read_text(encoding="utf-8") == "plugged in"
        assert receive({"cue": cue, "action": {"crash": "carlos"}})[0] == 422  # no show yet

        show.running = Backstage()
        assert receive({"cue": cue, "action": {"crash": "carlos"}})[0] == 200
        assert show.running.knocked == ["carlos"]
    finally:
        hub.hook.showrunner_shutdown(app=app)


def test_the_checks_say_whether_the_hub_s_coordinator_is_still_the_template(tmp_path):
    """Mutation: the verdict and the finding swapped, as a page of the demo's once showed them
    -- red here."""
    from hearth_demo import backstage

    copy = tmp_path / "coordinator.py"
    hearth_root = DEMO.parents[1]
    template = (hearth_root / copies.TEMPLATE).read_text(encoding="utf-8")
    head = (copies._git(hearth_root, "rev-parse", "--short=12", "HEAD") or "").strip()
    copy.write_text(template.replace(copies.ORIGIN, copies.LINE.format(
        revision=head, digest=copies.digest(template))), encoding="utf-8")

    kept = backstage.copy_row(copy)
    copy.write_text(copy.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    changed = backstage.copy_row(copy)
    copy.unlink()
    gone = backstage.copy_row(copy)

    assert (kept["status"], kept["failed"]) == (0, ""), kept
    assert kept["verdict"].startswith(("is the template at", "is a text hearth's template"))
    assert (changed["status"], changed["verdict"]) == (1, "is not the template")
    assert changed["failed"].startswith(("differs from the template", "is not the template at"))
    assert (gone["status"], gone["verdict"]) == (1, "is not the template")


def test_the_checks_judge_the_members_the_hub_and_its_copy(tmp_path, monkeypatch):
    """The hub is checked without --pull, so the checks take no delivery from leo's page."""
    from hearth_demo import backstage

    asked = []
    report = conformance.Report("x")
    monkeypatch.setattr(backstage.conformance, "check",
                        lambda url, action: asked.append(("check", url, action)) or report)
    monkeypatch.setattr(backstage.conformance, "check_hub",
                        lambda url, *rest, **kw: asked.append(("hub", url, rest, kw)) or report)
    show = backstage.Show({"hub": "http://hub", "copy": str(tmp_path / "coordinator.py"),
                           "members": [
        {"name": "carlos", "url": "http://carlos", "command": ["x"], "check": {"turn": "front"}},
        {"name": "joe", "url": "http://joe", "command": ["x"], "check": {}},
        {"name": "leo", "url": "http://leo", "command": ["x"]}]}, say=lambda text: None)

    rows = show.check()

    assert asked == [("check", "http://carlos", {"turn": "front"}),
                     ("check", "http://joe", None), ("hub", "http://hub", (), {})]
    assert [row["what"] for row in rows] == ["carlos, served alone", "joe, served alone",
                                             "the hub", "the hub's coordinator"]
    assert rows[-1]["verdict"] == "is not the template"  # there is no copy at that path


# --- a run ---------------------------------------------------------------------------


def test_a_run_begins_from_nothing_and_never_empties_a_directory_it_did_not_make(demo,
                                                                                  tmp_path):
    work = tmp_path / "run"
    assert demo.fresh(work) == work.resolve()
    (work / "hub").mkdir()
    assert sorted(p.name for p in demo.fresh(work).iterdir()) == [demo.MARK]

    theirs = tmp_path / "theirs"
    theirs.mkdir()
    (theirs / "notes.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(SystemExit, match="did not make"):
        demo.fresh(theirs)
    assert (theirs / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_a_port_already_listened_on_is_named_before_anything_is_emptied(demo):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        port = held.getsockname()[1]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as spare:
            spare.bind(("127.0.0.1", 0))
            free = spare.getsockname()[1]
        assert demo.taken([port, free]) == [port]


def test_every_port_a_run_binds_is_its_own(demo):
    at = demo.ports(18700)
    assert at["hub"] == 18700 and len(set(at.values())) == len(at)


def test_a_toml_value_reads_back_as_written(demo):
    value = {"command": ["uv", "run", "C:\\x y"], "check": {"turn": "front"}, "n": 5,
             "on": True, "t": 0.5}
    text = "".join(f"{key} = {demo.toml(item)}\n" for key, item in value.items())

    assert tomllib.loads(text) == value
