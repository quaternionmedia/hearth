# 02 — Three hosts, one contract

> **Runtime: loopback ports.** Each host is served on a free port on
> 127.0.0.1 in this process and stopped before the page ends. No browser, and
> nothing outside this machine.

The member from the previous page, served three ways, and held to the
contract by the same check each time. `kin check` asks the routes and nothing
else, so it judges a member in any language under any host, and with an
action it sends one real cue and waits for the event that carries it to a
follower.

```python
>>> import kin
>>> from kin import conformance, testing
>>> class Clock(kin.Member):
...     name, family, verbs = "clock", "show-control", ("clock",)
...     def __init__(self):
...         super().__init__()
...         self.laps = 0
...     def understand(self, action):
...         if action["clock"] != "lap":
...             raise kin.Refused(f"the clock cannot {kin.shown(action['clock'])}")
...         return self._lap
...     def _lap(self): self.laps += 1
...     def state(self): return {"laps": self.laps}
>>> def failed(report):
...     return [finding.what for finding in report.findings if not finding.ok]

```

## Alone

Any ASGI server, with the member's `start` and `stop` on the server's own
lifespan:

```python
>>> from kin import web
>>> alone = Clock()
>>> with testing.serving(web.app(alone)) as url:
...     report = conformance.check(url, action={"clock": "lap"})
>>> report.status, failed(report), alone.laps
(0, [], 1)

```

## Beside an aiohttp page

A page already served by aiohttp, as ShowStopper's is by textual-serve, takes
the routes, the lifecycle, and its streams closed at shutdown, from one call:

```python
>>> from aiohttp import web as aioweb
>>> from kin import aio
>>> beside = Clock()
>>> page = aioweb.Application()
>>> aio.attach(page, beside)
>>> with testing.serving_aiohttp(page) as url:
...     report = conformance.check(url, action={"clock": "lap"})
>>> report.status, failed(report), beside.laps
(0, [], 1)

```

## Inside the hub

ShowRunner is a pluggy host. `kin.showrunner.plugin` hosts the member in the
hub's process: its routes under `<hub>/<name>`, and a hook that hands the hub
the member's `receive`, so a cue reaches it by a call rather than a request.
`testing.showrunner_hub()` stands in for ShowRunner's hook marker and hooks,
so this page does not need ShowRunner installed:

```python
>>> from fastapi import FastAPI
>>> import types
>>> with testing.showrunner_hub() as hub:
...     from kin import showrunner as hosting
...     _ = hub.register(hosting.plugin(lambda settings: Clock(), name="clock",
...                                 family="show-control"))
...     api = FastAPI()
...     for routes in hub.hook.showrunner_get_routes():
...         api.include_router(routes)
...     _ = hub.hook.showrunner_startup(app=testing.hub_app(hub))
...     with testing.serving(api) as url:
...         report = conformance.check(f"{url}/clock", action={"clock": "lap"})
...     [members] = [m for m in hub.hook.showrunner_family_members() if m]
...     called = members["clock"]({"cue": {"number": "9"}, "action": {"clock": "lap"}})
...     _ = hub.hook.showrunner_shutdown(app=None)
>>> report.status, failed(report), called[0]
(0, [], 200)

```

The same check, at the hub's address, passes the same way.

## Only the hub's own family

Two families meet across a protocol, never an import. A member of another
family is served alone and named to the hub by its URL. The hub says which
family it is in, and the hosted plugin reads it from the hub at startup; a
member of another family is never made, and its routes say why:

```python
>>> with testing.showrunner_hub(family="show-control") as hub:
...     carlos = hosting.plugin(lambda settings: Clock(), name="carlos",
...                             family="instruments", log=lambda text: None)
...     _ = hub.register(carlos)
...     _ = hub.hook.showrunner_startup(app=testing.hub_app(hub))
>>> carlos.member is None
True
>>> print(carlos.why)
carlos is not hosted: it is in instruments, the hub in 'show-control'; two families meet across a protocol, so serve it alone and name its URL in [plugins.family.members]

```

## A member that breaks the contract

The check is evidence only because it fails. A member that records a cue it
refused does not conform:

```python
>>> class Careless(Clock):
...     def receive(self, body):
...         if isinstance(body, dict) and isinstance(body.get("cue"), dict):
...             self.cue = body["cue"]
...         return super().receive(body)
>>> with testing.serving(web.app(Careless())) as url:
...     report = conformance.check(url)
>>> report.status, failed(report)
(1, ['a refused cue changes nothing, the record of the last cue included'])

```

And nothing answering is not a failure but an absence:

```python
>>> conformance.check("http://127.0.0.1:9", timeout=1).status
3

```
