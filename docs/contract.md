# The family contract, `family/1`

What every member of a family answers, in any language, under any host.
`hearth check URL` asks these routes and nothing else, so it is the contract's
test; `hearth.Member` is one implementation of it, not the contract.

## A member's routes

Under the member's base URL: its own origin when served alone, `<hub>/<name>`
when a hub hosts it.

| Route | Answer |
|---|---|
| `POST /family/cue` | takes one cue's action, below |
| `GET /family/state` | `{"member": name, "cue": cue \| null, "state": {...}}` |
| `GET /family/events` | `text/event-stream`: a `state` event with that object at once, then one per change |
| `GET /family/identity` | `{"member", "family", "version", "contract": "family/1", "conformance", "verbs": [...], "instance", "pid"}` |

The `GET` routes answer any origin (`Access-Control-Allow-Origin: *`), since a
follower is often a page served elsewhere.

### `POST /family/cue`

```json
{"cue": {"number": "3", "name": "Second tune", "fired_at": "2026-10-15T21:00:00+00:00"},
 "action": {"clock": "start"}}
```

| Status | Body | Meaning |
|---|---|---|
| 200 | `{"ok": true, "state": {...}, "instance": "..."}` | done |
| 202 | `{"ok": true, "state": {...}, "instance": "..."}` | taken; the work finishes after the answer, and `state` says when |
| 422 | `{"ok": false, "error": "..."}` | not understood: a body that is not JSON, a cue that is not an object, an action the member does not take |
| 500 | `{"ok": false, "error": "..."}` | understood, and the member failed acting on it |

`action` is an object keyed by the member's verbs, the ones its identity
lists; a cue's `family` block maps each member's name to its action.
`instance` is the running member that took the cue, as its identity names it,
so a hub never credits a delivery to the instance before a restart.

**A refused or failed cue changes nothing**, the record of the last cue
included.

### `GET /family/events`

```
event: state
data: {"member": "clock", "cue": {...}, "state": {...}}

: still here
```

The first event is the state at once. A comment keeps a quiet stream open. A
follower that falls behind gets the newest state, never a backlog.

## A hub's routes

A hub is a coordinator running in its exemplar's app
([`coordinator.md`](coordinator.md)). `hearth check --hub URL` asks these.

| Route | Answer |
|---|---|
| `GET /family/identity` | `{"hub", "family", "contract": "family/1", "conformance", "version", "instance", "pid"}` |
| `GET /family/` | each member, how it is reached (`push`, `pull` or `local`), and each recent delivery's outcome: status, error, milliseconds from the fire |
| `GET /family/members/<name>` | a pull member's last cue and action: `{"cue", "action"}` |
| `GET /family/members/<name>/events` | the same, as a `text/event-stream` of `action` events |

A **push** member is sent `POST <url>/family/cue`. A **pull** member, a page
with no server, reads its action from the hub, and the first read after a fire
is the delivery, whoever reads. A **local** member is hosted in the hub's
process and handed the cue by a call, and still answers at
`<hub>/<name>/family/*`.

## Serving

`serve --host HOST --port PORT --state DIR` binds only the port it is given
and answers 2xx once it can be checked. `check --url URL` runs the member's
own check against an instance already up: exit 0 pass, 1 fail, anything else
could not say.

## Conformance and its version

[`conformance/vectors.json`](../conformance/vectors.json) lists the cases
`hearth check` asserts, member side and hub side, under one `version`. That
version is the coordinate every repository on `family/1` shares
(`records/DRAFT-a-shared-tag-asserts-interoperability.md` in the corpus): each
member and hub pins the version it replayed in its own suite, the corpus's
`ci/interop-registry.yaml` says where each pin is read, and `uv run qm interop`
compares them with the publisher's. hearth tags a version only once every
repository on the surface has replayed it; until then `pyproject.toml` carries
a development version. An implementation in another language replays the same
cases with a runner of its own and prints one line in the shape the registry
names.

An instance names the version it replayed as `conformance` on its identity.
`contract` stays the wire generation and `version` the app's own.
