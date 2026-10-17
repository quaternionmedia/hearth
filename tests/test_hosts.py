"""One member, every host, the same contract: each judged by ``kin check`` over a socket."""

from __future__ import annotations

import threading
import time

import httpx
from conftest import Clock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kin import conformance, testing, web


def test_alone_it_conforms_and_a_cue_reaches_a_follower(serve, clock):
    url = serve(web.app(clock))

    report = conformance.check(url, action={"clock": "lap"})

    assert report.status == 0, "\n".join(map(str, report.findings))
    assert clock.started == 1
    assert {"first event ms", "cue answered ms", "cue to event ms"} <= set(report.timings)


def test_its_lifecycle_rides_the_asgi_lifespan(clock):
    with testing.serving(web.app(clock)):
        assert (clock.started, clock.stopped) == (1, 0)

    assert (clock.started, clock.stopped) == (1, 1)


def test_a_body_that_is_not_json_is_answered_in_the_contract_s_words(clock):
    with TestClient(web.app(clock)) as client:
        said = client.post("/family/cue", content=b"{nope")

    assert (said.status_code, said.json()) == (422, {"ok": False, "error": "the body is not JSON"})


def test_before_the_host_makes_the_member_the_routes_say_so():
    api = FastAPI()
    api.include_router(web.router(lambda: None))
    client = TestClient(api)

    for said in (client.get("/family/state"), client.get("/family/identity"),
                 client.get("/family/events"), client.post("/family/cue", json={})):
        assert said.status_code == 503
        assert said.json()["error"] == "the member has not started"


def test_nothing_answering_is_could_not_say_not_fail():
    report = conformance.check("http://127.0.0.1:9", timeout=1)

    assert report.status == conformance.CANNOT_SAY


def test_a_member_that_breaks_the_contract_does_not_conform(serve):
    """Mutation of a member: it records a refused cue -- red here."""

    class Careless(Clock):
        def receive(self, body):
            if isinstance(body, dict) and isinstance(body.get("cue"), dict):
                self.cue = body["cue"]
            return super().receive(body)

    report = conformance.check(serve(web.app(Careless())))

    assert report.status == 1
    assert [f.what for f in report.findings if not f.ok] == \
        ["a refused cue changes nothing, the record of the last cue included"]


# --- beside an aiohttp page ----------------------------------------------------


def test_beside_an_aiohttp_page_it_conforms_the_same(aio_serve, clock):
    from aiohttp import web as aioweb

    from kin import aio

    application = aioweb.Application()
    aio.attach(application, clock)

    report = conformance.check(aio_serve(application), action={"clock": "start"})

    assert report.status == 0, "\n".join(map(str, report.findings))
    assert clock.started == 1


def test_an_open_stream_does_not_hold_the_page_s_shutdown(clock):
    """Mutation: attach no longer closes streams at shutdown -- red here (aiohttp waits)."""
    from aiohttp import web as aioweb

    from kin import aio

    application = aioweb.Application()
    aio.attach(application, clock)
    opened = threading.Event()

    def follow(url: str) -> None:
        try:
            with httpx.stream("GET", f"{url}/family/events", timeout=30) as stream:
                for _ in stream.iter_lines():
                    opened.set()
        except httpx.HTTPError:
            pass

    with testing.serving_aiohttp(application) as url:
        threading.Thread(target=follow, args=(url,), daemon=True).start()
        assert opened.wait(5)
        began = time.monotonic()
    took = time.monotonic() - began

    assert took < 5, f"shutting down with a follower took {took:.1f}s"
    assert clock.stopped == 1


# --- inside ShowRunner ---------------------------------------------------------


def hosted_clock(showrunner_hub, made=None, family="show-control", clock=Clock):
    from kin import showrunner as hosting

    def make(settings):
        if made is not None:
            made.append(settings)
        return clock()

    hosted = hosting.plugin(make, name="clock", family=family, log=lambda text: None)
    showrunner_hub.register(hosted)
    api = FastAPI()
    for routes in showrunner_hub.hook.showrunner_get_routes():
        api.include_router(routes)
    return hosted, api


def test_inside_the_hub_it_conforms_at_the_hub_s_address(showrunner_hub, serve):
    made = []
    _, api = hosted_clock(showrunner_hub, made)
    showrunner_hub.hook.showrunner_startup(
        app=testing.hub_app(showrunner_hub, {"clock": {"x": 1}}))
    url = serve(api)

    report = conformance.check(f"{url}/clock", action={"clock": "lap"})

    assert report.status == 0, "\n".join(map(str, report.findings))
    assert made == [{"x": 1}]
    [members] = [m for m in showrunner_hub.hook.showrunner_family_members() if m]
    assert members["clock"]({"cue": {"number": "9"}, "action": {"clock": "lap"}})[0] == 200
    assert httpx.get(f"{url}/clock/family/state").json()["cue"] == {"number": "9"}


def test_the_hub_may_ask_for_its_members_before_their_startup(showrunner_hub):
    """The hub's own startup may run first: the member is found at each call, not at asking."""
    hosted_clock(showrunner_hub)
    [members] = [m for m in showrunner_hub.hook.showrunner_family_members() if m]
    body = {"cue": {"number": "1"}, "action": {"clock": "lap"}}

    assert members["clock"](body) == (503, {"ok": False, "error": "clock has not started"})
    showrunner_hub.hook.showrunner_startup(app=testing.hub_app(showrunner_hub))
    assert members["clock"](body)[0] == 200


def test_the_hosted_plugin_answers_to_the_member_s_name(showrunner_hub):
    """ShowRunner disables an external plugin by ``__name__``, lowercased."""
    hosted, _ = hosted_clock(showrunner_hub)

    assert hosted.__name__ == "clock"


def test_a_member_of_another_family_than_the_hub_says_it_is_is_not_hosted(showrunner_hub):
    """The hub's family comes from the hub's own identity, not from kin."""
    made = []
    hosted, api = hosted_clock(showrunner_hub, made, family="instruments")
    showrunner_hub.hook.showrunner_startup(app=testing.hub_app(showrunner_hub))

    assert made == []
    assert "two families meet across a protocol" in hosted.why
    with TestClient(api) as client:
        said = client.get("/clock/family/state")
    assert said.status_code == 503 and "the hub in 'show-control'" in said.json()["error"]


def test_a_hub_that_predates_hosting_is_told_so_not_silently_ignored():
    """A hub whose hooks lack showrunner_hub_identity and _family_members hosts nothing.

    Mutation: the adapter no longer checks what the hub declares -- red here (it starts).
    """
    with testing.showrunner_hub(hosts_members=False) as old:
        made = []
        hosted, _ = hosted_clock(old, made)
        old.hook.showrunner_startup(app=testing.hub_app(old))

    assert made == []
    assert "does not declare showrunner_hub_identity, showrunner_family_members" in hosted.why


def test_a_member_that_cannot_start_is_not_ready_and_is_tried_again(showrunner_hub,
                                                                     monkeypatch):
    """Its device appears on the third try: the hub never stopped, and then it is ready."""
    from kin import showrunner as hosting

    monkeypatch.setattr(hosting, "RETRY_FIRST", 0.05)
    tries = []

    class Late(Clock):
        def start(self):
            tries.append(1)
            if len(tries) < 3:
                raise OSError("no MIDI device called 'Launchkey'")

    hosted, _ = hosted_clock(showrunner_hub, clock=Late)
    showrunner_hub.hook.showrunner_startup(app=testing.hub_app(showrunner_hub))
    [members] = [m for m in showrunner_hub.hook.showrunner_family_members() if m]
    body = {"cue": {"number": "1"}, "action": {"clock": "lap"}}

    status, answer = members["clock"](body)
    assert status == 503 and "is not ready: OSError: no MIDI device" in answer["error"]
    deadline = time.monotonic() + 5
    while hosted.member is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(tries) == 3
    assert members["clock"](body)[0] == 200
    showrunner_hub.hook.showrunner_shutdown(app=None)


def test_a_probe_may_ask_the_read_routes_with_head(clock):
    with TestClient(web.app(clock)) as client:
        assert [client.head(f"/family/{route}").status_code
                for route in ("state", "identity")] == [200, 200]
