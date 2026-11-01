# hearth

The contract a qm family's members keep, and what holds them to it.

Distributed as `qm-hearth`, imported as `hearth`: the name `hearth` on PyPI is
another project's.

A family's members are separate apps. Something fires (a cue in ShowRunner, a
downbeat in a looper) and a **coordinator** hands each member its part of the
fire's family block, then keeps what each answered. The wire between them is
`family/1`: four routes on every member and three on the coordinator, plain
HTTP, JSON and server-sent events, in any language.

hearth holds four things:

| | What | Read |
|---|---|---|
| **The contract and its check** | `family/1`, both sides; `hearth check URL` judges a member and `hearth check --hub URL` a coordinator, by their routes alone | [`docs/contract.md`](docs/contract.md) |
| **The member library** | `hearth.Member`, which says what an action changes and what its state is; the hosts that serve one alone, beside an aiohttp page, or inside ShowRunner; `hearth.supervise`, which keeps one running; `follow.js`, which a page follows one with; `hearth.testing` | [`docs/hosting.md`](docs/hosting.md) |
| **The coordinator** | [`src/hearth/coordinator.py`](src/hearth/coordinator.py), one text run two ways: an app that coordinates a family imports it from `qm-hearth`, or copies it whole where its maintainer takes no dependency; `hearth fork` makes and updates the copy, and `hearth check --copy` says whether it is still the template | [`docs/coordinator.md`](docs/coordinator.md) |
| **The demo** | Loopback, a show of nine cues run by ShowRunner alone: its plugins keep the members beside it, and a stagehand hosted in it does the acts backstage on its cues | [`docs/demo.md`](docs/demo.md) |

A member runs hearth's library. A coordinator runs hearth's text too, imported
from `qm-hearth`, or copied whole into the app beside the app's own code where
the app's maintainer takes no dependency. ShowRunner is the copy's example:
its family plugin is its own, and the coordinator under it is the template at
a named revision.

## Start here

- **Write a member:** [`walkthrough/01-a-member.md`](walkthrough/01-a-member.md),
  then serve it three ways in
  [`walkthrough/02-three-hosts.md`](walkthrough/02-three-hosts.md).
- **Coordinate a family:**
  [`walkthrough/03-a-coordinator.md`](walkthrough/03-a-coordinator.md), then
  `hearth fork` the template into the app as
  [`docs/coordinator.md`](docs/coordinator.md) says.
- **See it all run, as a show:** `uv run python demo/loopback.py --dev <dev>`,
  then press GO through the nine cues at `http://127.0.0.1:18700/programmer`
  ([`docs/demo.md`](docs/demo.md)).

The walkthrough's pages run as doctests in the ordinary test command.

```bash
uv sync
uv run pytest
uv run hearth check http://127.0.0.1:18410 --action '{"clock": "lap"}'
uv run hearth check --hub http://127.0.0.1:18700 --pull leo   # its read is a delivery
uv run hearth check --copy <ShowRunner>/src/showrunner/plugins/family/coordinator.py
```

[`bench/hosting.py`](bench/hosting.py) measures what hosting a member in the
hub's process costs and what it risks, against serving it alone.
