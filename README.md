# hearth

One contract for the performing family's members, served alone or inside a hub.

Distributed as `qm-hearth`, imported as `hearth`: the name `hearth` on PyPI is another
project's.

A member says what an action changes and what its state is. hearth serves it
the four `/family/*` routes every member answers, the same way under every
host:

| Host | How | When |
|---|---|---|
| Alone | `hearth.web.app(member)`, any ASGI server | Always available; the only way across families |
| Beside an aiohttp page | `hearth.aio.attach(app, member)` | ShowStopper, whose page is textual-serve |
| Inside ShowRunner | `hearth.showrunner.plugin(make, name=..., family=...)` under the `showrunner` entry point | Only for a member of the hub's own family |

`hearth check URL` judges any of them, in any language, by the routes alone.
`--action '{"clock": "lap"}'` also sends one real cue and times it to the
member's answer and to the event a follower receives.

The contract is [`docs/contract.md`](docs/contract.md); which host serves a
member, and what a hub owes one it hosts, is
[`docs/hosting.md`](docs/hosting.md). A page follows a member with
[`src/hearth/static/follow.js`](src/hearth/static/follow.js): the event stream
first, polling only while it is down.

[`walkthrough/`](walkthrough/) is a member built and served three ways, run
by `uv run pytest` as doctests.

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
```
