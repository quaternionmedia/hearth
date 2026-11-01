# hearth

The contract a qm family's members keep, and what holds them to it.
Distributed as `qm-hearth`, imported as `hearth`; the PyPI name `hearth` is
another project's.

A family's members are separate apps. Something fires, a cue in ShowRunner or
a downbeat in a looper, and a **coordinator** hands each member its part of
the fire's family block and keeps what each answered. The wire is `family/1`:
four routes on a member, three on a coordinator, over HTTP, JSON and
server-sent events, in any language.

| | What | Read |
|---|---|---|
| **The contract and its check** | `family/1`, both sides, and the vector set it is measured by. `hearth check URL` judges a member and `hearth check --hub URL` a coordinator, by their routes alone | [`docs/contract.md`](docs/contract.md) |
| **The member library** | `hearth.Member` says what an action changes and what its state is. Hosts serve one alone, beside an aiohttp page or inside ShowRunner; `hearth.supervise` keeps one running; `follow.js` follows one from a page; `hearth.testing` holds one to the contract | [`docs/hosting.md`](docs/hosting.md) |
| **The coordinator** | [`src/hearth/coordinator.py`](src/hearth/coordinator.py), one text run two ways: imported from `qm-hearth`, or copied whole where an app's maintainer takes no dependency. `hearth fork` makes and updates a copy, and `hearth check --copy` says whether it is still the template | [`docs/coordinator.md`](docs/coordinator.md) |
| **The demo** | Loopback: nine cues ShowRunner runs alone, each a round trip through the hub, with a stagehand hosted in it doing the acts backstage | [`docs/demo.md`](docs/demo.md) |

## Start here

- **Write a member:** [`walkthrough/01-a-member.md`](walkthrough/01-a-member.md),
  then serve it three ways in [`walkthrough/02-three-hosts.md`](walkthrough/02-three-hosts.md).
- **Coordinate a family:** [`walkthrough/03-a-coordinator.md`](walkthrough/03-a-coordinator.md),
  then import or fork the coordinator as [`docs/coordinator.md`](docs/coordinator.md) says.
- **Run the show:** `uv run python demo/loopback.py --dev <dev>`, then press GO
  at `http://127.0.0.1:18700/programmer` ([`docs/demo.md`](docs/demo.md)).

The walkthrough's pages run as doctests under the ordinary test command.

```bash
uv sync
uv run pytest
uv run hearth check http://127.0.0.1:18410 --action '{"clock": "lap"}'
uv run hearth check --hub http://127.0.0.1:18700 --pull leo
uv run hearth check --copy <ShowRunner>/src/showrunner/plugins/family/coordinator.py
```

[`bench/hosting.py`](bench/hosting.py) measures what hosting a member in the
hub's process costs and risks, against serving it alone.
