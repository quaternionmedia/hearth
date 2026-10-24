"""A member's answer to a cue, decided once for every member."""

from __future__ import annotations

from conftest import Clock

CUE = {"number": "3", "name": "Second tune", "fired_at": "2026-10-15T21:00:00+00:00"}


def test_an_understood_cue_is_acted_on_recorded_and_answered_200(clock):
    status, answer = clock.receive({"cue": CUE, "action": {"clock": "start"}})

    assert (status, answer) == (200, {"ok": True, "state": {"running": True, "laps": 0},
                                      "instance": clock.instance})
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
        ({"cue": "4", "action": {"clock": "lap"}},
         "cue must be an object: {number, name, fired_at}"),
        (["not", "an", "object"], "the body must be a JSON object with a cue and an action"),
    ]:
        assert clock.receive(body) == (422, {"ok": False, "error": error})
    assert clock.snapshot() == before


def test_work_that_finishes_later_is_answered_202(clock):
    class Later(Clock):
        later = True

    assert Later().receive({"cue": CUE, "action": {"clock": "lap"}})[0] == 202


def test_a_change_sees_its_own_cue(clock):
    """Mutation: the cue recorded after the change -- red here (the change sees the last one)."""
    seen = []

    class Named(Clock):
        def understand(self, action):
            return lambda: seen.append(self.cue)

    named = Named()
    named.receive({"cue": CUE, "action": {"clock": "lap"}})
    named.receive({"cue": {**CUE, "number": "4"}, "action": {"clock": "lap"}})

    assert [cue["number"] for cue in seen] == ["3", "4"]


def test_a_change_that_fails_is_answered_500_and_records_nothing(clock):
    class Broken(Clock):
        def understand(self, action):
            if action["clock"] == "lap":
                return super().understand(action)

            def change():
                raise OSError("the disk is full")

            return change

    broken = Broken()
    broken.receive({"cue": CUE, "action": {"clock": "lap"}})
    status, answer = broken.receive({"cue": {**CUE, "number": "4"}, "action": {"clock": "x"}})

    assert (status, answer) == (500, {"ok": False, "error": "clock failed acting on the cue: "
                                                            "OSError: the disk is full"})
    assert broken.snapshot()["cue"] == CUE


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


def test_a_running_member_may_name_its_own_version_and_instance():
    named = Clock.__new__(Clock)
    Clock.__bases__[0].__init__(named, version="1.2.3", instance="pid-42")

    assert (named.identity()["version"], named.identity()["instance"]) == ("1.2.3", "pid-42")
    assert Clock().identity()["version"] == "test"
