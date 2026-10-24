# The coordinator template

A coordinator delivers each fire's family block to the members it names, and
keeps what each answered. hearth holds it as a template,
[`template/coordinator.py`](../template/coordinator.py), outside the package.
An app that coordinates a family, an **exemplar**, copies it into its own code
and owns the copy. The template imports nothing of hearth, so neither does a
copy, and `hearth check --hub URL` holds every copy to the contract from
outside.

This is the split the corpus keeps for itself: a project owns its copies of
the seed, and the checks run in place. A change to the template reaches a copy
only when its owner carries it in; a fix to the check reaches every copy the
next time it runs.

## What an exemplar supplies

| | ShowRunner | The looper in `tests/test_coordinator.py` |
|---|---|---|
| What fires, and when | a cue: the programmer's GO, or any path that announces `cue.fired` | the downbeat of a bar, at `POST /beat` |
| Where the block is | the cue's `actions["family"]` | its own |
| Where the coordinator runs | ShowFamily, a pluggy plugin; its table is `[plugins.family]` | a FastAPI app; its table is `[looper.family]` |
| The members in its own process | members of `show-control`, from `showrunner_family_members` | none |
| What it is | `showrunner`, of `show-control` | `looper`, of `instruments` |

ShowRunner's copy came first: the template was cut from its family plugin,
with what fires and where it runs left open, and ShowRunner keeps its own.

## Forking it

1. Copy `template/coordinator.py` into the exemplar, under any name.
2. Set its `Copied from:` line to the hearth revision it came from.
3. Make the coordinator from the exemplar's settings, serve its routes in the
   exemplar's app, fire it when something fires, and close it at the app's
   stop:

   ```python
   running = coordinator.from_table(settings, local=hosted, table="[plugins.family]")
   app.include_router(coordinator.router(
       lambda: running, lambda: coordinator.identity("showrunner", "show-control", version),
       table="[plugins.family]"))

   running.fire({"number": "3", "name": "Second tune", "fired_at": fired_at}, block)
   ```

4. Run `hearth check --hub URL` against the running exemplar, from hearth's
   own environment or, once hearth is published, with
   `uvx --from qm-hearth hearth check --hub URL`.

To take a later change to the template, diff the copy against the revision
its `Copied from:` line names, carry in what the exemplar wants, and move the
line. A copy is never overwritten whole, since its owner may have changed
what it owns. Nothing reports a copy that has fallen behind; the check reports
one that breaks the contract.

## What it does

- **Three ways to a member:** pushed to at its URL, handed the body by a call
  when hosted in the exemplar's process, or read by the member itself, whose
  first read after a fire is the delivery. A URL wins over a hosted member of
  the same name, and either over a pull.
- **A fire never waits.** Each member has one queue, so its blocks arrive in
  the order they fired, and one HTTP client, kept for the coordinator's life,
  so no fire pays a client's setup. Every request has a timeout.
- **Every outcome is kept** at `GET /family/`: the member, how it went, the
  status, the error, the milliseconds from the fire, and the instance that
  took it, from the member's own answer. A member that is down, slow or
  refuses is recorded and never raised.
- **It says what it is** at `GET /family/identity`:
  `identity(hub, family, version)`, the instance being the process, so a
  coordinator remade when its settings change is the same instance to its
  members.
- **A malformed settings entry is skipped and said** in the exemplar's own
  table's words, through the exemplar's logger.

The template's tests are hearth's, and import it where it stands. A copy's
tests are its exemplar's.
