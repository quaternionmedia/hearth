# The coordinator

A coordinator delivers each fire's family block to the members it names, and
keeps what each answered. `hearth.coordinator` is the whole of that. An
exemplar makes it a running hub by supplying what hearth leaves open:

| An exemplar supplies | ShowRunner | The looper in `tests/test_coordinator.py` |
|---|---|---|
| What fires, and when | a cue: the programmer's GO, `POST /programmer/cue/{n}`, any path that announces `cue.fired` | the downbeat of a bar, at `POST /beat` |
| Where the block is | the cue's `actions["family"]` | its own |
| Where the coordinator runs | ShowFamily, a pluggy plugin of the hub; its table is `[plugins.family]` | a FastAPI app; its table is `[looper.family]` |
| The members in its own process | members of `show-control`, from `showrunner_family_members` | none |
| What it is | `identity("showrunner", "show-control", version)` | `identity("looper", "instruments")` |

Both serve the same routes and pass the same check, `hearth check --hub URL`.

## What the coordinator does

**Three ways to a member.** A member named by URL is pushed to: `POST
<url>/family/cue`. A member hosted in the coordinator's process is handed the
same body by a call, its `Receive`, and answers as its route would. A member
named as pulled reads its action at `GET /family/members/<name>`, or follows
it at `/family/members/<name>/events`, and its first read after a fire is the
delivery. A URL wins over a hosted member of the same name, and either wins
over a pull.

**A fire never waits.** `fire(cue, block)` queues one delivery per member the
block names and returns at once. Each pushed or called member has one worker
thread, so its blocks arrive in the order they fired. Each pushed member has
one HTTP client, made with the coordinator and kept for its life, sharing one
TLS context, so no fire pays a client's setup. Every request has a timeout.

**Every outcome is kept.** `GET /family/` lists each member, how it is
reached, and the last 200 deliveries: the cue, the member, how it went, the
HTTP status (`null` when nothing answered), the error, and the milliseconds
from the fire to the answer or the first read. A member that is down, slow or
refuses is recorded and never raised, and the other members are delivered to.
A pull action overtaken before it was read says so.

**Each outcome names the instance that took it.** The coordinator asks a
pushed member's `GET /family/identity` before the first delivery and again
after one that failed. It credits each outcome to the instance the member's
own answer names, so a member restarted between two fires is never credited
as the one before.

**The coordinator says what it is.** `identity(hub, family, version)` is its
answer at `GET /family/identity`: the exemplar, the family it coordinates, the
contract it keeps, and the running instance. The instance is the process, so
a coordinator remade when its settings change is the same instance to its
members.

## What an exemplar does with it

```python
from hearth import coordinator

running = coordinator.from_table(settings, local=hosted, table="[plugins.family]")
app.include_router(coordinator.router(lambda: running, lambda: coordinator.identity(
    "showrunner", "show-control", version), table="[plugins.family]"))

running.fire({"number": "3", "name": "Second tune", "fired_at": fired_at}, block)
```

- `from_table(settings, local, table=..., log=...)` makes the coordinator from a
  settings table: `members` maps a name to a URL, `pull` lists names, `timeout`
  is seconds per delivery. A malformed entry is said through `log` in the
  table's own name and skipped, never fatal.
- `router(coordinator, hub, table=...)` finds the running coordinator at each
  request, so the exemplar may make it after the routes mount and remake it
  when its settings change. Until there is one, the index is empty.
- `fire(cue, block)` takes the contract's `cue`, `{"number", "name",
  "fired_at"}`, whatever fired: a beat is a cue to the contract.
- `close()` at the exemplar's shutdown ends the queues. A delivery already on
  the wire finishes.

The exemplar hosts in its own process only members of its own family
([`hosting.md`](hosting.md)), and says what it is before a hosted member
starts, since the member reads the hub's family rather than assuming it.
