"""A member's answer to a cue, decided once for every member."""

from __future__ import annotations

from conftest import Clock

CUE = {"number": "3", "name": "Second tune", "fired_at": "2026-10-15T21:00:00+00:00"}


def test_an_understood_cue_is_acted_on_recorded_and_answered_200(clock):
    status, answer = clock.receive({"cue": CUE, "action": {"clock": "start"}})

    assert (status, answer) == (200, {"ok": True, "state": {"running": True, "laps": 0}})
    assert clock.snapshot() == {"member": "clock", "cue": CUE,
                                "state": {"running": True, "laps": 0}}


def test_a_refused_cue_changes_nothing_not_even_the_record(clock):
    clock.receive({"cue": CUE, "action": {"clock": "start"}})
    before = clock.snapshot()

    for body, error in [
        ({"cue": {**CUE, "number": "4"}, "action": {"clock": "dance"}},
         "the clock can start, stop, reset, lap; it cannot 'dance'"),
        ({"cue": {**CUE, "number": "4"}, "action": {"tempo": 120}},
         "clock does not take 'tempo' (clock)"),
        ({"cue": {**CUE, "number": "4"}, "action": {}},
         "clock takes an action object (clock), not {}"),
        ({"cue": "4", "action": {"clock": "lap"}}, "cue must be an object: {number, name, fired_at}"),
        (["not", "an", "object"], "the body must be a JSON object with a cue and an action"),
    ]:
        assert clock.receive(body) == (422, {"ok": False, "error": error})
    assert clock.snapshot() == before


def test_work_that_finishes_later_is_answered_202(clock):
    class Later(Clock):
        later = True

    assert Later().receive({"cue": CUE, "action": {"clock": "lap"}})[0] == 202


def test_every_follower_is_told_each_change_and_a_broken_one_stops_nobody(clock):
    told, also = [], []

    def broken(_):
        raise RuntimeError("gone")

    clock.follow(broken)
    unfollow = clock.follow(told.append)
    clock.follow(also.append)

    clock.receive({"cue": CUE, "action": {"clock": "lap"}})
    unfollow()
    clock.receive({"cue": CUE, "action": {"clock": "lap"}})

    assert [s["state"]["laps"] for s in told] == [1]
    assert [s["state"]["laps"] for s in also] == [1, 2]


def test_identity_names_the_member_its_family_and_this_instance():
    one, other = Clock(), Clock()
    said = one.identity()

    assert {k: said[k] for k in ("member", "family", "version", "contract", "verbs")} == \
        {"member": "clock", "family": "show-control", "version": "test",
         "contract": "family/1", "verbs": ["clock"]}
    assert said["instance"] != other.identity()["instance"]
