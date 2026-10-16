# kin

One contract for the performing family's members, served alone or inside a hub.

Distributed as `qm-kin`, imported as `kin`: the name `kin` on PyPI is another
project's.

A member says what an action changes and what its state is. kin serves it
the four `/family/*` routes every member answers, the same way under every
host:

| Host | How | When |
|---|---|---|
| Alone | `kin.web.app(member)`, any ASGI server | Always available; the only way across families |
| Beside an aiohttp page | `kin.aio.attach(app, member)` | ShowStopper, whose page is textual-serve |
| Inside ShowRunner | `kin.showrunner.plugin(make, name=..., family=...)` under the `showrunner` entry point | Only for a member of the hub's own family |

`kin check URL` judges any of them, in any language, by the routes alone.
`--action '{"clock": "lap"}'` also sends one real cue and times it to the
member's answer and to the event a follower receives.

The contract is [`docs/contract.md`](docs/contract.md). A page follows a
member with [`src/kin/static/follow.js`](src/kin/static/follow.js): the event
stream first, polling only while it is down.

FastAPI keeps an included router as one entry in `app.routes`, so code that
lists an app's routes finds kin's with `fastapi.routing.iter_route_contexts`.

```bash
uv sync
uv run pytest
uv run kin check http://127.0.0.1:18410 --action '{"clock": "lap"}'
```
