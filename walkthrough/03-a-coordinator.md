# 03 — A coordinator

> **Runtime: hermetic.** No port: the members are in this process. Its last
> part forks the template, and so runs from a checkout of hearth with its
> history.

A coordinator is the other side of the contract: something fires, and it hands
each member the part of the family block that names it. hearth holds it as one
text, `hearth.coordinator`, which an exemplar imports from `qm-hearth` or
copies whole, and runs beside its own code; this page imports it. It
is an exemplar at its smallest, a looper whose downbeat is what fires, with a
clock hosted in its process and a page that reads its action, and shows what
the coordinator keeps.

```python
>>> import hearth
>>> from hearth import coordinator
>>> class Clock(hearth.Member):
...     name, family, verbs = "clock", "instruments", ("clock",)
...     laps = 0
...
...     def understand(self, action):
...         if action["clock"] != "lap":
...             raise hearth.Refused(f"the clock cannot {hearth.shown(action['clock'])}")
...         return self._lap
...
...     def _lap(self): self.laps += 1
...
...     def state(self):
...         return {"laps": self.laps}
>>> clock = Clock()
>>> looper = coordinator.Coordinator(local={"clock": clock.receive}, pull=["lights"],
...                                  table="[looper.family]")

```

The looper decides what fires and names it as the contract names whatever
fired, a `cue`. `fire` returns at once with the members it queued for:

```python
>>> bar = {"number": "bar 1", "name": "downbeat", "fired_at": None}
>>> looper.fire(bar, {"clock": {"clock": "lap"}, "lights": {"flash": 1}, "wolf": {"play": 1}})
['clock', 'lights', 'wolf']
>>> looper.wait(5)
True
>>> clock.state()
{'laps': 1}

```

Every delivery is kept, with how it went. The clock was handed the block by a
call and answered as its route would, crediting the instance that took it. The
lights have not read theirs yet. `wolf` is not in the looper's table, and the
coordinator says where it looked:

```python
>>> for o in looper.snapshot()["last"]:
...     print(o["member"], o["via"], o["status"], o["done"], o["error"])
clock local 200 True None
lights pull None False None
wolf None None True wolf is not a member in [looper.family]
>>> looper.snapshot()["last"][0]["instance"] == clock.instance
True

```

A pulled member's first read is its delivery:

```python
>>> looper.read("lights")
{'cue': {'number': 'bar 1', 'name': 'downbeat', 'fired_at': None}, 'action': {'flash': 1}}
>>> [(o["member"], o["status"], o["done"]) for o in looper.snapshot()["last"]][1]
('lights', 200, True)
>>> looper.close()

```

A hub serves the same as routes, `coordinator.router`, and says what it is
with `coordinator.identity`; [`docs/coordinator.md`](../docs/coordinator.md)
has both, and how ShowRunner supplies what this looper did.

## A copy of it

An exemplar whose maintainer takes no dependency on hearth copies the text
whole instead, with `hearth fork`, which writes the template as committed at hearth's `HEAD` and
names that revision, and the template's text by its digest, in the copy's
`Copied from:` line. `hearth check --copy` says whether a copy is still the
template:

```python
>>> import pathlib, tempfile
>>> from hearth import copies
>>> copy = pathlib.Path(tempfile.mkdtemp()) / "coordinator.py"
>>> copies.fork(copy).current
True
>>> line = copies.NAMED.search(copy.read_text(encoding="utf-8"))
>>> len(line.group(1)), len(line.group(2))    # the revision, and the text's digest
(12, 16)
>>> found = copies.check(copy)
>>> found.status, found.current
(0, True)

```

What is the exemplar's own goes in a module beside the copy. A change made in
the copy itself leaves it no longer the template: the check shows the lines,
and `fork` will not write over them:

```python
>>> text = copy.read_text(encoding="utf-8")
>>> _ = copy.write_text(text.replace("KEPT = 200", "KEPT = 50"), encoding="utf-8")
>>> found = copies.check(copy)
>>> found.status, found.said.split(" at ")[0]
(1, 'differs from the template')
>>> for changed in found.changed:
...     if changed.startswith(("-KEPT", "+KEPT")):
...         print(changed.split("  #")[0])
-KEPT = 200
+KEPT = 50
>>> copies.fork(copy).said.endswith("nothing written")
True

```

Such a change goes to the template instead, and every exemplar takes it by
forking again.
