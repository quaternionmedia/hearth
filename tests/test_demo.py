"""The proposal demo's own pieces, without its hub or its members."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import kin

DEMO = Path(__file__).resolve().parents[1] / "demo" / "proposal.py"


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


def test_the_metronome_is_not_ready_until_its_device_is_there(demo, tmp_path):
    device = tmp_path / "beat-box.device"
    metronome = demo.Metronome(device)

    with pytest.raises(OSError, match="no MIDI clock device"):
        metronome.start()
    device.write_text("plugged in", encoding="utf-8")
    metronome.start()
    assert metronome.receive({"cue": {"number": "2"}, "action": {"beat": 120}})[0] == 200
    assert metronome.receive({"cue": {"number": "3"}, "action": {"beat": 9}}) == \
        (422, {"ok": False, "error": "a beat is 20 to 300 bpm, not 9"})
    assert metronome.state() == {"bpm": 120, "beats": 1}


def test_the_rack_is_of_another_family_than_the_hub(demo):
    assert demo.Rack.family == "instruments" != demo.Metronome.family
    assert isinstance(demo.Rack(), kin.Member)


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
