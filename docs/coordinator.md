# The coordinator template

A coordinator delivers each fire's family block to the members it names, and
keeps what each answered. hearth holds it as a template,
[`template/coordinator.py`](../template/coordinator.py), outside the package.
An app that coordinates a family, an **exemplar**, runs the template: it copies
the file whole, and writes what is its own in a module beside the copy. The
template imports nothing of hearth, so neither does the exemplar.

The template is where the coordinator changes. A copy is the template's text
at the revision its `Copied from:` line names, whatever its line endings, and
the line names that text too, by its digest:

```text
Copied from: hearth e15792b6ba43, sha256 0f3c9a1d27b4e856.
```

So two facts about a copy are mechanical. Whether it is still the template its
line names, the copy shows by itself, and the exemplar's own tests say it with
nothing of hearth installed. Whether the template has changed since,
`hearth check --copy PATH` says from hearth's history. `hearth check --hub URL`
judges the running exemplar from outside. The digest catches a change made by
hand or by a formatter; it is not a signature.

## What an exemplar supplies

| | ShowRunner | The looper in `tests/test_coordinator.py` |
|---|---|---|
| What fires, and when | a cue: the programmer's GO, or any path that announces `cue.fired` | the downbeat of a bar, at `POST /beat` |
| Where the block is | the cue's `actions["family"]` | its own |
| Where the coordinator runs | ShowFamily, a pluggy plugin in `plugins/family/__init__.py`, beside its copy in `plugins/family/coordinator.py`; its table is `[plugins.family]` | a FastAPI app; its table is `[looper.family]` |
| The members in its own process | members of `show-control`, from `showrunner_family_members` | none |
| What it is | `showrunner`, of `show-control` | `looper`, of `instruments` |

## Forking it

1. From hearth's checkout, write the template into the exemplar:

   ```bash
   uv run hearth fork <exemplar>/coordinator.py
   ```

   The copy is the template as committed at hearth's `HEAD`, its
   `Copied from:` line naming that revision and its text. Fork from a
   revision a remote of hearth holds, since a copy is read against the
   revision it names: `hearth fork` says when no remote holds `HEAD`.
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

3. In the exemplar's own tests, show that the copy is the template its line
   names, so its own suite fails when the copy is changed, by hand or by a
   formatter run over the tree:

   ```python
   def test_the_coordinator_is_the_template_its_line_names():
       text = Path(coordinator.__file__).read_text(encoding="utf-8")
       line = re.search(r"^Copied from: hearth [0-9a-f]+, sha256 ([0-9a-f]{16})\.$", text, re.M)
       template = text.replace(line.group(0), "Copied from: this is the template.")
       assert hashlib.sha256(template.encode("utf-8")).hexdigest()[:16] == line.group(1)
   ```

4. Run `hearth check --hub URL` against the running exemplar, and
   `hearth check --copy <exemplar>/coordinator.py` against its tree.

To take a later template, run `hearth fork` on the copy again. It writes the
newer template over a copy that is still the template at a revision hearth's
`HEAD` descends from. It refuses a copy that is not the template, showing the
lines that differ, since writing over it would lose them, and a copy taken at
a revision `HEAD` does not descend from, since writing over it could take it
back to an older template. A change the exemplar needs in its copy is offered
to the template instead, so the copy stays the template and every exemplar can
take the change.

`hearth check --copy` reads hearth's history from a checkout of hearth with all
of it. From a release of hearth, or a shallow clone, it says from the digest
alone whether the copy is the template its line names, and not whether the
template has changed since. Its exit is 0 whenever the copy is the template it
names; how far the template has moved since is said, not failed.

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

The template's tests are hearth's, and import it where it stands; they test
every copy whose line names a revision they passed at. An exemplar's tests hold
what it supplies, one delivery each way through its own app, and the digest.
hearth lints the template with the rules of the exemplars that copy it, since a
copy is never edited to pass its owner's lint; an exemplar whose formatter
would change the copy leaves the copy out of it.
