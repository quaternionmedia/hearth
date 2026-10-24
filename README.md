# hearth

The coordinator of a qm family, and the contract its members keep.

Distributed as `qm-hearth`, imported as `hearth`: the name `hearth` on PyPI is
another project's.

A family's members are separate apps. A **coordinator** is what they gather
round: something fires, and the coordinator hands each member its part of the
fire's family block, keeps every outcome, and credits each to the instance
that answered. hearth is that coordinator with two things left open. What
fires, and where the coordinator runs, belong to an **exemplar**. ShowRunner is
the first exemplar: a cue fires, the cue's actions carry the block, and its
ShowFamily plugin holds the coordinator.

| Side | What hearth gives | Read |
|---|---|---|
| The coordinator | `hearth.coordinator`: each member pushed to, called in-process or pulled; a client and a queue per member; every outcome; the `/family/*` routes a hub serves | [`docs/coordinator.md`](docs/coordinator.md) |
| A member | `hearth.Member`: the envelope, the refusal, the record of the last cue, its followers; the four routes every member answers | [`docs/contract.md`](docs/contract.md) |
| Hosting a member | served alone, beside an aiohttp page, or inside its hub when the two share a family | [`docs/hosting.md`](docs/hosting.md) |
| The check | `hearth check URL` judges a member, `hearth check --hub URL` a coordinator, in any language, by the routes alone | `hearth.conformance` |

A member is served by whichever host fits it:

| Host | How | When |
|---|---|---|
| Alone | `hearth.web.app(member)`, any ASGI server | Always available; the only way across families |
| Beside an aiohttp page | `hearth.aio.attach(app, member)` | ShowStopper, whose page is textual-serve |
| Inside ShowRunner | `hearth.showrunner.plugin(make, name=..., family=...)` under the `showrunner` entry point | Only for a member of the hub's own family |

`--action '{"clock": "lap"}'` makes `hearth check` send one real cue and time
it to the member's answer and to the event a follower receives. A page follows
a member with [`src/hearth/static/follow.js`](src/hearth/static/follow.js): the
event stream first, polling only while it is down.

[`walkthrough/`](walkthrough/) builds a member, serves it three ways, and
coordinates it, run by `uv run pytest` as doctests.

`hearth.supervise` keeps members served alone running beside a hub, restarting
one that stops on Companion's schedule. [`bench/hosting.py`](bench/hosting.py)
measures what hosting costs and what it risks against serving alone;
[`demo/proposal.py`](demo/proposal.py) runs the whole arrangement on one
machine, ShowRunner as the hub, with a panel that says what to try.

FastAPI keeps an included router as one entry in `app.routes`, so code that
lists an app's routes finds hearth's with `fastapi.routing.iter_route_contexts`.

```bash
uv sync
uv run pytest
uv run hearth check http://127.0.0.1:18410 --action '{"clock": "lap"}'
uv run hearth check --hub http://127.0.0.1:18400 --pull leo
```
