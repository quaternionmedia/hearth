"""The coordinator: a family block, delivered to the members it names, and every outcome.

The push members here are fakes on real ports (``tests/fakes.py``), so every
delivery is a real HTTP request. The coordinator's routes are mounted as an
exemplar mounts them, on an app of the test's own, and one test mounts them in
an exemplar that fires on a beat rather than a cue.
"""

from __future__ import annotations

import json
import threading

import httpx
import pytest
from fakes import FakeMember, dead_url
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hearth import conformance, coordinator, testing

CUE = {"number": "3", "name": "Second tune", "fired_at": "2026-10-10T21:00:00.000001+00:00"}
TABLE = "[plugins.family]"  # the table these tests' exemplar names its members in


class Hub:
    """An exemplar at its smallest: one running coordinator, remade from a table, and
    the coordinator's routes on an app of its own."""

    def __init__(self) -> None:
        self.now: coordinator.Coordinator | None = None
        self.app = FastAPI()
        self.app.include_router(coordinator.router(
            lambda: self.now, lambda: coordinator.identity("test-hub", "test", "1"),
            table=TABLE))
        self.client = TestClient(self.app)

    def make(self, settings: dict | None = None, local=None) -> coordinator.Coordinator:
        if self.now is not None:
            self.now.close()
        self.now = coordinator.from_table(settings, local, table=TABLE)
        return self.now

    def close(self) -> None:
        if self.now is not None:
            self.now.close()
        self.now = None


@pytest.fixture()
def hub():
    made = Hub()
    yield made
    made.close()


@pytest.fixture()
def fake_member():
    """Start fake members on demand; all are stopped after the test."""
    started: list[FakeMember] = []

    def start(name: str = "showstopper", **kwargs) -> FakeMember:
        member = FakeMember(name, **kwargs)
        started.append(member)
        return member

    yield start
    for member in started:
        member.close()


def sse_actions(stream):
    """Each ``action`` event's data from a server-sent event stream, as it arrives."""
    name, data = None, []
    for line in stream.iter_lines():
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
        elif line == "" and data:
            if name == "action":
                yield json.loads("\n".join(data))
            name, data = None, []


def outcome(found: dict, member: str) -> dict:
    return next(o for o in found["last"] if o["member"] == member)


# --- push --------------------------------------------------------------------

def test_a_push_member_is_sent_the_cue_and_its_action(fake_member, hub):
    clock = fake_member("showstopper")
    running = hub.make({"members": {"showstopper": clock.url}})

    running.fire(CUE, {"showstopper": {"clock": "start"}})

    assert running.wait(10)
    assert clock.received == [{"cue": CUE, "action": {"clock": "start"}}]
    said = outcome(hub.client.get("/family/").json(), "showstopper")
    assert (said["cue"], said["via"], said["status"], said["done"], said["error"]) == \
        (CUE, "push", 200, True, None)
    assert isinstance(said["ms"], int) and said["ms"] >= 0
    assert said["answer"] == {"ok": True, "state": {"seen": 1}, "instance": "showstopper-1"}


def test_a_push_member_s_cues_share_one_client(fake_member, hub, monkeypatch):
    """Made with the coordinator, before any cue, and every post goes through it.

    Mutations: _push back to httpx.post (no post on it), or the client made at
    the member's first cue (none made yet) -- each red here.
    """
    made, posts = [], []

    class Counted(coordinator.httpx.Client):
        def __init__(self, *args, **kwargs):
            made.append(self)
            super().__init__(*args, **kwargs)

        def post(self, *args, **kwargs):
            posts.append(self)
            return super().post(*args, **kwargs)

    monkeypatch.setattr(coordinator.httpx, "Client", Counted)
    clock = fake_member("showstopper")
    running = hub.make({"members": {"showstopper": clock.url}})
    assert len(made) == 1

    for number in ("1", "2", "3"):
        running.fire({**CUE, "number": number}, {"showstopper": {"clock": "lap"}})

    assert running.wait(10)
    assert [body["cue"]["number"] for body in clock.received] == ["1", "2", "3"]
    assert len(made) == 1
    assert posts == made * 3


def test_202_for_work_that_finishes_later_is_a_delivery(fake_member, hub):
    joe = fake_member("joe", understands=("take",), status=202)
    running = hub.make({"members": {"joe": joe.url}})

    running.fire(CUE, {"joe": {"take": {"notes": ["C4"], "seconds_per_note": 0.5}}})

    assert running.wait(10)
    assert outcome(running.snapshot(), "joe")["status"] == 202


def test_a_member_that_is_down_is_recorded_and_the_others_still_get_theirs(fake_member, hub):
    """Mutation: the broad except in _push narrowed to TimeoutException -- red here."""
    down_at = dead_url()
    carlos = fake_member("carlos", understands=("patch",))
    running = hub.make({"members": {"showstopper": down_at, "carlos": carlos.url},
                        "timeout": 3})

    running.fire(CUE, {"showstopper": {"clock": "start"}, "carlos": {"patch": "Moog DFAM"}})

    assert running.wait(15)
    down = outcome(running.snapshot(), "showstopper")
    assert (down["status"], down["done"]) == (None, True)
    assert down["error"]
    assert outcome(running.snapshot(), "carlos")["status"] == 200
    assert carlos.received[0]["action"] == {"patch": "Moog DFAM"}


def test_a_422_is_passed_through_with_the_member_s_own_error(fake_member, hub):
    clock = fake_member("showstopper")
    running = hub.make({"members": {"showstopper": clock.url}})

    running.fire(CUE, {"showstopper": {"dance": "now"}})

    assert running.wait(10)
    said = outcome(running.snapshot(), "showstopper")
    assert (said["status"], said["error"]) == (422, "no action {'dance': 'now'}")
    assert said["answer"] == {"ok": False, "error": "no action {'dance': 'now'}"}


def test_a_slow_member_times_out_and_firing_never_waits_for_it(fake_member, hub):
    """Mutation: the push run inline in fire() instead of on its lane -- red here."""
    slow = fake_member("showstopper", delay=2.0)
    running = hub.make({"members": {"showstopper": slow.url}, "timeout": 0.5})

    # Fired from a thread of its own, so a fire() that blocks -- or deadlocks --
    # fails here rather than hanging the suite.
    returned = threading.Event()
    threading.Thread(target=lambda: (running.fire(CUE, {"showstopper": {"clock": "start"}}),
                                     returned.set()), daemon=True).start()
    assert returned.wait(0.25), "fire() waited for the member"

    assert running.wait(10)
    said = outcome(running.snapshot(), "showstopper")
    assert said["status"] is None
    assert said["error"].startswith("no answer within 0.5s")


def test_one_member_s_cues_arrive_in_the_order_they_fired(fake_member, hub):
    """Mutation: eight worker threads per member instead of one -- red here."""
    clock = fake_member("showstopper", delay=0.05)
    running = hub.make({"members": {"showstopper": clock.url}})

    for number in range(1, 7):
        running.fire({**CUE, "number": str(number)}, {"showstopper": {"clock": "lap"}})

    assert running.wait(15)
    assert [body["cue"]["number"] for body in clock.received] == [str(n) for n in range(1, 7)]


# --- pull --------------------------------------------------------------------

def test_a_pull_member_reads_its_action_and_the_read_is_its_delivery(hub):
    running = hub.make({"pull": ["leo"]})
    before = hub.client.get("/family/members/leo")
    assert before.json() == {"cue": None, "action": None}
    assert before.headers["access-control-allow-origin"] == "*"

    running.fire(CUE, {"leo": {"song": "Blue Bossa"}})
    waiting = outcome(hub.client.get("/family/").json(), "leo")
    assert (waiting["via"], waiting["status"], waiting["done"]) == ("pull", None, False)

    assert hub.client.get("/family/members/leo").json() == {"cue": CUE,
                                                             "action": {"song": "Blue Bossa"}}
    read = outcome(hub.client.get("/family/").json(), "leo")
    assert (read["status"], read["done"]) == (200, True) and read["ms"] >= 0
    # Read again, the action is the same and the delivery is not counted twice.
    assert hub.client.get("/family/members/leo").json()["action"] == {"song": "Blue Bossa"}
    assert [o["member"] for o in hub.client.get("/family/").json()["last"]] == ["leo"]


def test_a_pull_action_never_read_is_said_to_be_overtaken(hub):
    running = hub.make({"pull": ["leo"]})
    running.fire(CUE, {"leo": {"song": "Blue Bossa"}})
    running.fire({**CUE, "number": "4"}, {"leo": {"song": "Take The A Train"}})

    first, _ = running.snapshot()["last"]
    assert (first["status"], first["done"]) == (None, True)
    assert first["error"] == "cue 4 fired before leo read this one"
    assert running.read("leo")["action"] == {"song": "Take The A Train"}


def test_only_a_pull_member_has_a_members_route(fake_member, hub):
    clock = fake_member("showstopper")
    hub.make({"members": {"showstopper": clock.url}, "pull": ["leo"]})
    for name in ("showstopper", "nobody"):
        missing = hub.client.get(f"/family/members/{name}")
        assert missing.status_code == 404
        assert missing.headers["access-control-allow-origin"] == "*"
        assert missing.json()["detail"] == f"{name} is not a pull member in {TABLE}"
    assert hub.client.get("/family/").json()["members"] == {
        "showstopper": {"via": "push", "url": clock.url, "identity": None}, "leo": {"via": "pull"}}


def test_a_name_the_table_does_not_hold_is_recorded_not_sent(hub):
    running = hub.make({"pull": ["leo"]})
    running.fire(CUE, {"wolf": {"play": True}})
    said = outcome(running.snapshot(), "wolf")
    assert (said["via"], said["status"], said["done"]) == (None, None, True)
    assert said["error"] == f"wolf is not a member in {TABLE}"


def test_a_pull_member_s_stream_opens_with_its_action_and_carries_each_cue(hub):
    """The stream is the members route, pushed: a read at once, and one per cue that lands.

    Mutation: fire no longer tells the stream's readers -- red here (no second event).
    """
    running = hub.make({"pull": ["leo"]})
    with testing.serving(hub.app) as url, httpx.Client(timeout=10) as reader, \
            reader.stream("GET", f"{url}/family/members/leo/events") as stream:
        assert stream.headers["access-control-allow-origin"] == "*"
        events = sse_actions(stream)
        assert next(events) == {"cue": None, "action": None}
        running.fire(CUE, {"leo": {"song": "Blue Bossa"}})
        assert next(events) == {"cue": CUE, "action": {"song": "Blue Bossa"}}

    said = outcome(running.snapshot(), "leo")
    assert (said["via"], said["status"], said["done"]) == ("pull", 200, True)
    assert said["ms"] < 1000


def test_a_stream_for_a_name_that_is_not_a_pull_member_is_404(hub):
    hub.make({"pull": ["leo"]})
    missing = hub.client.get("/family/members/nobody/events")
    assert (missing.status_code, missing.headers["access-control-allow-origin"]) == (404, "*")


# --- local -------------------------------------------------------------------

def test_a_local_member_is_handed_the_cue_by_a_call_and_audited_as_local(hub):
    calls = []

    def receive(body):
        calls.append(body)
        if body["action"] == {"clock": "dance"}:
            return 422, {"ok": False, "error": "the clock cannot dance"}
        return 200, {"ok": True, "state": {"laps": len(calls)}, "instance": "clock-1"}

    running = hub.make({"pull": ["clock"]}, local={"clock": receive})
    running.fire(CUE, {"clock": {"clock": "lap"}})
    running.fire({**CUE, "number": "4"}, {"clock": {"clock": "dance"}})

    assert running.wait(10)
    assert calls == [{"cue": CUE, "action": {"clock": "lap"}},
                     {"cue": {**CUE, "number": "4"}, "action": {"clock": "dance"}}]
    first, second = running.snapshot()["last"]
    assert (first["via"], first["status"], first["error"], first["instance"]) == \
        ("local", 200, None, "clock-1")
    assert (second["status"], second["error"], second["instance"]) == \
        (422, "the clock cannot dance", None)
    assert running.snapshot()["members"] == {"clock": {"via": "local"}}
    assert running.pull == []


def test_a_url_in_the_table_wins_over_a_local_member_of_the_same_name(fake_member, hub):
    clock = fake_member("clock")
    running = hub.make({"members": {"clock": clock.url}},
                       local={"clock": lambda body: (200, {"ok": True})})
    running.fire(CUE, {"clock": {"clock": "lap"}})

    assert running.wait(10)
    assert outcome(running.snapshot(), "clock")["via"] == "push"
    assert len(clock.received) == 1


def test_before_there_is_a_coordinator_the_routes_answer_empty(hub):
    assert hub.client.get("/family/").json() == {"members": {}, "last": []}
    assert hub.client.get("/family/members/leo").status_code == 404


# --- the table -----------------------------------------------------------------

@pytest.mark.parametrize("settings, members, pull, timeout", [
    ({}, {}, [], coordinator.DEFAULT_TIMEOUT),
    ({"members": {"a": "http://h:1/", "b": "ftp://h", "c": 5}}, {"a": "http://h:1"}, [], 5.0),
    ({"members": ["a"], "pull": "leo"}, {}, [], 5.0),
    ({"members": {"leo": "http://h:1"}, "pull": ["leo", "x"]}, {"leo": "http://h:1"}, ["x"], 5.0),
    ({"timeout": 0}, {}, [], coordinator.DEFAULT_TIMEOUT),
    ({"timeout": True}, {}, [], coordinator.DEFAULT_TIMEOUT),
    ({"timeout": 1.5}, {}, [], 1.5),
])
def test_a_malformed_table_entry_is_skipped_not_fatal(settings, members, pull, timeout):
    said = []
    built = coordinator.from_table(settings, table=TABLE, log=said.append)
    try:
        assert (built.members, built.pull, built.timeout) == (members, pull, timeout)
    finally:
        built.close()


def test_a_malformed_entry_is_said_in_the_exemplar_s_words():
    said = []
    coordinator.from_table({"members": {"b": "ftp://h"}, "timeout": 0},
                           table=TABLE, log=said.append).close()
    assert said == ["[plugins.family.members] b = 'ftp://h' is not an http URL; ignored",
                    (f"[plugins.family] timeout must be a positive number; "
                     f"{coordinator.DEFAULT_TIMEOUT} used")]


# --- what the coordinator is, and what each member says it is -----------------

def test_the_coordinator_says_what_it_is_and_keeps_its_instance_when_remade(hub):
    said = hub.client.get("/family/identity")

    assert said.headers["access-control-allow-origin"] == "*"
    assert {k: said.json()[k] for k in ("hub", "family", "contract")} == \
        {"hub": "test-hub", "family": "test", "contract": "family/1"}
    hub.make({"pull": ["leo"]})
    hub.make({"pull": ["leo", "joe"]})
    assert hub.client.get("/family/identity").json()["instance"] == said.json()["instance"]


def test_each_delivery_names_the_member_instance_that_answered_it(fake_member, hub):
    """Asked before the first push and again after a failed one, since a member may restart.

    Mutation: the identity not asked again after a failure -- red here (the old instance).
    """
    clock = fake_member("showstopper")
    running = hub.make({"members": {"showstopper": clock.url}})

    running.fire(CUE, {"showstopper": {"clock": "start"}})
    assert running.wait(10)
    clock.status, clock.instance = 503, "showstopper-2"  # it went down and came back
    running.fire({**CUE, "number": "4"}, {"showstopper": {"clock": "stop"}})
    assert running.wait(10)
    clock.status = 200
    running.fire({**CUE, "number": "5"}, {"showstopper": {"clock": "lap"}})
    assert running.wait(10)

    first, failed, after = running.snapshot()["last"]
    assert (first["instance"], first["status"]) == ("showstopper-1", 200)
    assert failed["status"] == 503
    assert (after["instance"], after["status"]) == ("showstopper-2", 200)
    assert running.snapshot()["members"]["showstopper"]["identity"]["instance"] == "showstopper-2"


def test_a_member_that_restarted_between_two_cues_is_credited_as_the_new_instance(
        fake_member, hub):
    """No delivery failed, so only the answer itself can say: the stress of the demo found it.

    Mutation: the outcome's instance taken from the coordinator's cached identity -- red here.
    """
    clock = fake_member("showstopper")
    running = hub.make({"members": {"showstopper": clock.url}})
    running.fire(CUE, {"showstopper": {"clock": "start"}})
    assert running.wait(10)

    clock.instance = "showstopper-2"  # restarted between the cues, answering all along
    running.fire({**CUE, "number": "4"}, {"showstopper": {"clock": "lap"}})
    assert running.wait(10)
    running.fire({**CUE, "number": "5"}, {"showstopper": {"clock": "lap"}})
    assert running.wait(10)

    assert [o["instance"] for o in running.snapshot()["last"]] == \
        ["showstopper-1", "showstopper-2", "showstopper-2"]
    assert running.snapshot()["members"]["showstopper"]["identity"]["instance"] == "showstopper-2"


# --- another exemplar ----------------------------------------------------------

def test_an_exemplar_that_fires_on_a_beat_keeps_the_same_contract(fake_member, serve):
    """Nothing in the coordinator is a cue list's: a looper's beat fires it as well, and
    ``hearth check --hub`` passes against what the looper serves."""
    metronome = fake_member("metronome", understands=("bar",))
    running = coordinator.from_table({"members": {"metronome": metronome.url},
                                      "pull": ["lights"]},
                                     table="[looper.family]")
    looper = FastAPI()
    looper.include_router(coordinator.router(
        lambda: running, lambda: coordinator.identity("looper", "instruments"),
        table="[looper.family]"))
    bars = iter(range(1, 100))

    @looper.post("/beat")
    def beat():  # the looper's own trigger: the downbeat of each bar
        bar = next(bars)
        return running.fire({"number": f"bar {bar}", "name": "downbeat", "fired_at": None},
                            {"metronome": {"bar": bar}, "lights": {"flash": bar}})

    try:
        url = serve(looper)
        assert httpx.post(f"{url}/beat").json() == ["metronome", "lights"]
        assert running.wait(10)
        assert metronome.received == [{"cue": {"number": "bar 1", "name": "downbeat",
                                               "fired_at": None}, "action": {"bar": 1}}]
        assert conformance.check_hub(url, pull="lights").status == 0
    finally:
        running.close()
