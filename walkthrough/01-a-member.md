# 01 — A member

> **Runtime: hermetic.** No port, no browser: the member is called in this
> process.

A member says two things: what an action changes, and what its state is.
Everything else is the same for every member, and hearth does it once. This
page builds the smallest member worth having, a show clock.

```python
>>> import hearth
>>> class Clock(hearth.Member):
...     name, family, verbs = "clock", "show-control", ("clock",)
...
...     def __init__(self):
...         super().__init__()
...         self.running, self.laps = False, 0
...
...     def understand(self, action):
...         verb = action["clock"]
...         if verb not in ("start", "stop", "lap"):
...             raise hearth.Refused(f"the clock cannot {hearth.shown(verb)}")
...         return {"start": self._start, "stop": self._stop, "lap": self._lap}[verb]
...
...     def _start(self): self.running = True
...     def _stop(self): self.running = False
...     def _lap(self): self.laps += 1
...
...     def state(self):
...         return {"running": self.running, "laps": self.laps}
>>> clock = Clock()

```

`understand` returns the change unmade, or refuses. hearth makes the change
only once nothing is left to refuse, so a cue is acted on whole or not at all.

## A cue

The hub delivers each member its part of a cue's `family` block as the body of
`POST /family/cue`. `receive` is that route without the route. Its answer
names the instance that took the cue, so a hub credits the delivery to it even
after a restart:

```python
>>> cue = {"number": "3", "name": "Second tune", "fired_at": None}
>>> status, answer = clock.receive({"cue": cue, "action": {"clock": "start"}})
>>> status, answer["state"], answer["instance"] == clock.instance
(200, {'running': True, 'laps': 0}, True)
>>> clock.snapshot()
{'member': 'clock', 'cue': {'number': '3', 'name': 'Second tune', 'fired_at': None}, 'state': {'running': True, 'laps': 0}}

```

## A refusal changes nothing

Not the state, and not the record of the last cue:

```python
>>> later = {"number": "4", "name": "Bridge", "fired_at": None}
>>> clock.receive({"cue": later, "action": {"clock": "rewind"}})
(422, {'ok': False, 'error': "the clock cannot 'rewind'"})
>>> clock.receive({"cue": later, "action": {"tempo": 120}})
(422, {'ok': False, 'error': "clock does not take 'tempo' (clock)"})
>>> clock.receive("not a cue")
(422, {'ok': False, 'error': 'the body must be a JSON object with a cue and an action'})
>>> clock.snapshot()["cue"]["number"]
'3'

```

The first refusal is the clock's own words; the other two are hearth's, which
every member answers the same way.

## Followers

`GET /family/events` tells every follower the state at each change. Under
the route, a follower is a callable:

```python
>>> told = []
>>> stop = clock.follow(told.append)
>>> _ = clock.receive({"cue": later, "action": {"clock": "lap"}})
>>> stop()
>>> _ = clock.receive({"cue": later, "action": {"clock": "lap"}})
>>> [snapshot["state"]["laps"] for snapshot in told]
[1]

```

A member whose state moves on its own, such as a take that finishes on a
worker, calls `changed()` when it does.

## What it is

Before attributing a measurement to whatever answers a port, ask it:

```python
>>> said = clock.identity()
>>> {k: said[k] for k in ("member", "family", "contract", "verbs")}
{'member': 'clock', 'family': 'show-control', 'contract': 'family/1', 'verbs': ['clock']}

```

`instance` and `pid` name this running member. The next page serves it.
