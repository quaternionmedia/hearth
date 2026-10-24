# The family contract, `family/1`

What every member of the performing family answers, whatever language it is
written in and whatever serves it. `hearth check URL` asks these routes and
nothing else, so it is the contract's test; `src/hearth/member.py` is one
implementation of it, not the contract.

## A member's routes

All under the member's base URL: its own origin when it is served alone,
`<hub>/<name>` when a hub hosts it.

| Route | Answer |
|---|---|
| `POST /family/cue` | the hub delivers one cue's action, below |
| `GET /family/state` | `{"member": name, "cue": cue \| null, "state": {...}}` |
| `GET /family/events` | `text/event-stream`: one `state` event carrying the same object at once, then one per change |
| `GET /family/identity` | `{"member", "family", "version", "contract": "family/1", "verbs": [...], "instance", "pid"}` |

The three `GET` routes are readable from any origin
(`Access-Control-Allow-Origin: *`); a follower is often a page in another one.

### `POST /family/cue`

```json
{"cue": {"number": "3", "name": "Second tune", "fired_at": "2026-10-15T21:00:00+00:00"},
 "action": {"clock": "start"}}
```

| Status | Body | Meaning |
|---|---|---|
| 200 | `{"ok": true, "state": {...}, "instance": "..."}` | done |
| 202 | `{"ok": true, "state": {...}, "instance": "..."}` | taken; the work finishes after the answer, and `state` says when |
| 422 | `{"ok": false, "error": "..."}` | not understood: a body that is not JSON, a cue that is not an object, an action it does not take |
| 500 | `{"ok": false, "error": "..."}` | understood, and the member failed acting on it |

`instance` is the one `GET /family/identity` names: the running instance that
took this cue. A hub attributes the delivery to it, so a member that restarted
between two cues is never credited to the instance before it.

**A refused cue changes nothing**, the record of the last cue included. A cue
the member failed to act on leaves the record of the last cue as it was.

`action` is an object whose keys are the member's verbs, named in its
identity's `verbs`. A cue's `family` block maps each member's name to its
action, and the hub delivers each one.

### `GET /family/events`

```
event: state
data: {"member": "clock", "cue": {...}, "state": {...}}

: still here
```

The first event is the state at once, so a follower needs no second request to
begin. A comment line keeps a quiet stream open. A follower that falls behind
is sent the newest state, never a backlog.

## A hub's routes

A hub is a coordinator running in its exemplar's app
([`coordinator.md`](coordinator.md)); `hearth check --hub URL` asks these.

| Route | Answer |
|---|---|
| `GET /family/identity` | `{"hub", "family", "contract": "family/1", "version", "instance", "pid"}` |
| `GET /family/` | each member, how it is reached (`push`, `pull` or `local`), and every recent delivery's outcome: status, error, milliseconds from the fire to the answer |
| `GET /family/members/<name>` | for a pull member: `{"cue", "action"}`, the last cue that named it |
| `GET /family/members/<name>/events` | the same, as a `text/event-stream` of `action` events |

A **push** member is sent `POST <url>/family/cue`. A **pull** member, a page
with no server of its own, reads its action from the hub. A **local** member
is hosted in the hub's process and handed the cue by a call; it is still
reachable at `<hub>/<name>/family/*`.

## Serving

`serve --host HOST --port PORT --state DIR` binds only the port it is given
and answers 2xx at its URL only once it can be checked. `check --url URL`
runs the member's own behavioural check against an instance already up: exit
0 pass, 1 fail, any other status could not say.
