"""The proposal demo's own pieces, without its hub or its members."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

import hearth
from hearth import testing

DEMO = Path(__file__).resolve().parents[1] / "demo" / "proposal.py"
PLUGINS = DEMO.parent / "plugins"


@pytest.fixture(scope="module")
def demo():
    spec = importlib.util.spec_from_file_location("proposal", DEMO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_cue_sits_on_a_line_of_the_script_and_names_only_the_demo_s_members(demo):
    lines = demo.SCRIPT.splitlines()
    members = {"showstopper", "carlos", "joe", "leo", "metronome", "rack"}

    for number, _name, _layer, line, block in demo.CUES:
        assert [text for text in lines if text.startswith(line)], f"cue {number}: {line!r}"
        assert set(block) <= members, f"cue {number} names {set(block) - members}"
        assert demo.NOTES[number], f"cue {number} has no note for people"


# --- ShowRunner as itself ---------------------------------------------------------


def shims(path: Path, plugin: bool) -> list[str]:
    """What in a file would shim ShowRunner, by line.

    A plugin is loaded by ShowRunner and may import it, as every plugin does; the
    demo's script may not, by name or otherwise. Neither adds to ``sys.path``,
    sets or deletes anything on a module it imported, or calls what does so by
    name (``setattr``, ``import_module``, ``exec``).
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
        if isinstance(node, ast.Attribute) and node.attr == "path" \
                and isinstance(node.value, ast.Name) and node.value.id == "sys":
            found.append(f"{node.lineno}: sys.path")
        if isinstance(node, ast.Call):
            called = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if called in {"setattr", "delattr", "import_module", "__import__", "exec", "eval"}:
                found.append(f"{node.lineno}: {called}()")
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
    """The hub is ShowRunner's own process: the script reaches it over HTTP only, and
    what runs inside it, the demo's plugins and hearth's host, patches nothing.

    Mutations: ``import showrunner``, ``importlib.import_module("showrunner...")``,
    ``from sys import path``, ``setattr`` on a module, or a module attribute set,
    in the script or a plugin -- each red here.
    """
    inside = [*sorted(PLUGINS.rglob("*.py")), Path(hearth.__file__).parent / "showrunner.py"]

    assert shims(DEMO, plugin=False) == []
    for path in inside:
        assert shims(path, plugin=True) == [], path.name


def test_the_panel_says_whether_the_hub_s_coordinator_is_still_the_template(demo, tmp_path):
    """Mutation: the verdict and the finding swapped, as a panel once showed them -- red here."""
    from hearth import copies

    copy = tmp_path / "ShowRunner" / demo.COPY
    copy.parent.mkdir(parents=True)
    assert copies.fork(copy).status == 0

    kept = demo.copy_row(tmp_path)
    copy.write_text(copy.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    changed = demo.copy_row(tmp_path)
    copy.unlink()
    gone = demo.copy_row(tmp_path)

    assert (kept["status"], kept["failed"]) == (0, "")
    assert kept["verdict"].startswith("is the template at")
    assert (changed["status"], changed["verdict"]) == (1, "is not the template")
    assert changed["failed"].startswith("differs from the template")
    assert (gone["status"], gone["verdict"]) == (1, "is not the template")


def test_the_hub_is_showrunner_s_own_command_with_its_plugins_installed_beside_it(demo,
                                                                                  tmp_path):
    dev = tmp_path / "dev"
    spec = demo.hub(dev, tmp_path / "work", 18700)

    command = spec.command
    start = command.index("-m")
    assert command[start:start + 4] == ["-m", "showrunner.cli", "start", "--config"]
    beside = [command[i + 1] for i, word in enumerate(command) if word == "--with-editable"]
    assert beside == [str(demo.HEARTH), str(PLUGINS), str(dev / "ShowStopper")]
    assert command[command.index("--project") + 1] == str(dev / "ShowRunner")


def test_the_hub_s_show_toml_sets_up_its_plugins_as_show_toml_does(demo, tmp_path):
    """ShowRunner reads it as it reads any show.toml: no table here is the demo's own."""
    tomllib = pytest.importorskip("tomllib")
    said = tomllib.loads(demo.show_toml(tmp_path, 18700))

    assert said["server"] == {"host": "127.0.0.1", "port": 18700}
    assert said["plugins"]["disabled"] == ["showstopper"]  # the clock runs beside the hub
    assert said["plugins"]["family"]["pull"] == ["leo"]
    assert said["plugins"]["family"]["members"] == {
        "showstopper": "http://127.0.0.1:18710", "carlos": "http://127.0.0.1:18720",
        "joe": "http://127.0.0.1:18731"}
    assert said["plugins"]["metronome"] == {"device": (tmp_path / "beat-box.device").as_posix()}


def test_the_demo_s_plugins_are_found_through_showrunner_s_entry_points():
    tomllib = pytest.importorskip("tomllib")
    declared = tomllib.loads((PLUGINS / "pyproject.toml").read_text(encoding="utf-8"))
    points = declared["project"]["entry-points"]["showrunner"]
    assert points == {"metronome": "hearth_demo.hosted:metronome",
                      "rack": "hearth_demo.hosted:rack"}

    sys.modules.pop("hearth_demo.hosted", None)
    with testing.showrunner_hub():
        from hearth_demo import hosted

        for name, value in points.items():
            plugin = getattr(hosted, value.split(":")[1])
            assert plugin.__name__ == name  # what ShowRunner's [plugins] disabled matches
    sys.modules.pop("hearth_demo.hosted", None)


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


def test_the_panel_has_a_port_of_its_own_beside_the_hub_s(demo):
    at = demo.ports(18700)
    assert (at["hub"], at["panel"]) == (18700, 18701)
    assert len(set(at.values())) == len(at)
