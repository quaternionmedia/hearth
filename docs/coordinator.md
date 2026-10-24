# The coordinator template

A coordinator delivers each fire's family block to the members it names, and
keeps what each answered. hearth holds it as a template,
[`template/coordinator.py`](../template/coordinator.py), outside the package.
An app that coordinates a family, an **exemplar**, runs the template: it copies
the file whole, and writes what is its own in a module beside the copy. The
template imports nothing of hearth, so neither does the exemplar.

The template is where the coordinator changes. A copy is the template at the
revision its `Copied from:` line names, byte for byte but for that line, so
two facts about it are mechanical: whether it is still the template, and
whether the template has changed since. `hearth check --copy PATH` states
both; `hearth check --hub URL` judges the running exemplar from outside.

## What an exemplar supplies

| | ShowRunner | The looper in `tests/test_coordinator.py` |
|---|---|---|
| What fires, and when | a cue: the programmer's GO, or any path that announces `cue.fired` | the downbeat of a bar, at `POST /beat` |
| Where the block is | the cue's `actions["family"]` | its own |
| Where the coordinator runs | ShowFamily, a pluggy plugin in `plugins/family.py`, beside its copy in `plugins/coordinator.py`; its table is `[plugins.family]` | a FastAPI app; its table is `[looper.family]` |
| The members in its own process | members of `show-control`, from `showrunner_family_members` | none |
| What it is | `showrunner`, of `show-control` | `looper`, of `instruments` |

## Forking it

1. From hearth's checkout, write the template into the exemplar:

   ```bash
   uv run hearth fork <exemplar>/coordinator.py
   ```

   The copy is the template as committed at hearth's `HEAD`, its
   `Copied from:` line naming that revision.
2. In a module of the exemplar's own, make the coordinator from the
   exemplar's settings, serve its routes in the exemplar's app, fire it when
   something fires, and close it at the app's stop:

   ```python
   from . import coordinator

   running = coordinator.from_table(settings, local=hosted, table="[plugins.family]")
   app.include_router(coordinator.router(
       lambda: running, lambda: coordinator.identity("showrunner", "show-control", version),
       table="[plugins.family]"))

   running.fire({"number": "3", "name": "Second tune", "fired_at": fired_at}, block)
   ```

3. Run `hearth check --hub URL` against the running exemplar, and
   `hearth check --copy <exemplar>/coordinator.py` against its tree.

To take a later template, run `hearth fork` on the copy again. It writes the
newer template over a copy that is still the template at its revision, and
refuses one that is not, showing the lines that differ, since writing over it
would lose them. A change the exemplar needs in its copy is offered to the
template instead, so the copy stays the template and every exemplar can take
the change.

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

The template's tests are hearth's, and import it where it stands. An
exemplar's tests hold what it supplies, and the copy with it.
