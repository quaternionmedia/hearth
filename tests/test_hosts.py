"""One member, every host, the same contract: each judged by ``kin check`` over a socket."""

from __future__ import annotations

import sys
import types

import httpx
import pluggy
import pytest
from conftest import Clock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kin import conformance, web


def test_alone_it_conforms_and_a_cue_reaches_a_follower(serve, clock):
    served = serve(web.app(clock))

    report = conformance.check(served.url, action={"clock": "lap"})

    assert report.status == 0, "\n".join(map(str, report.findings))
    assert clock.started == 1
    assert {"first event ms", "cue answered ms", "cue to event ms"} <= set(report.timings)


def test_its_lifecycle_rides_the_asgi_lifespan(serve, clock):
    served = serve(web.app(clock))
    served.close()

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

    report = conformance.check(serve(web.app(Careless())).url)

    assert report.status == 1
    assert [f.what for f in report.findings if not f.ok] == \
        ["a refused cue changes nothing, the record of the last cue included"]


def test_beside_an_aiohttp_page_it_conforms_the_same(aio_serve, clock):
    from aiohttp import web as aioweb

    from kin import aio

    application = aioweb.Application()
    application.add_routes(aio.routes(clock))

    report = conformance.check(aio_serve(application).url, action={"clock": "start"})

    assert report.status == 0, "\n".join(map(str, report.findings))


# --- inside ShowRunner ---------------------------------------------------------


@pytest.fixture()
def showrunner_hub(monkeypatch):
    """ShowRunner's hook marker and the four hooks the adapter answers, without ShowRunner.

    The real hub is tested in ShowRunner; this holds the adapter to the hook
    names ShowRunner's hookspecs declare.
    """
    fake = types.ModuleType("showrunner")
    fake.hookimpl = pluggy.HookimplMarker("showrunner")
    monkeypatch.setitem(sys.modules, "showrunner", fake)
    spec = pluggy.HookspecMarker("showrunner")

    class Spec:
        @spec
        def showrunner_register(self): ...

        @spec
        def showrunner_startup(self, app): ...

        @spec
        def showrunner_shutdown(self, app): ...

        @spec
        def showrunner_get_routes(self): ...

        @spec
        def showrunner_family_members(self): ...

        @spec
        def showrunner_get_nav(self): ...

    pm = pluggy.PluginManager("showrunner")
    pm.add_hookspecs(Spec)
    return pm


def test_inside_the_hub_it_conforms_at_the_hub_s_address(showrunner_hub, serve):
    from kin import showrunner as hosting

    made = []

    def make(settings):
        made.append(settings)
        return Clock()

    hosted = hosting.plugin(make, name="clock", family="show-control")
    showrunner_hub.register(hosted)
    api = FastAPI()
    for routes in showrunner_hub.hook.showrunner_get_routes():
        api.include_router(routes)

    config = types.SimpleNamespace(plugins=types.SimpleNamespace(settings={"clock": {"x": 1}}))
    showrunner_hub.hook.showrunner_startup(app=types.SimpleNamespace(config=config))
    served = serve(api)

    report = conformance.check(f"{served.url}/clock", action={"clock": "lap"})

    assert report.status == 0, "\n".join(map(str, report.findings))
    assert made == [{"x": 1}]
    [members] = [m for m in showrunner_hub.hook.showrunner_family_members() if m]
    assert members["clock"]({"cue": {"number": "9"}, "action": {"clock": "lap"}})[0] == 200
    assert httpx.get(f"{served.url}/clock/family/state").json()["cue"] == {"number": "9"}


def test_a_member_of_another_family_is_not_hosted_in_the_hub(showrunner_hub):
    from kin import showrunner as hosting

    with pytest.raises(ValueError, match="two families meet across a protocol"):
        hosting.plugin(lambda settings: Clock(), name="carlos", family="instruments")
