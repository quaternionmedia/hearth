# The coordinator template

A coordinator delivers each fire's family block to the members it names, and
keeps what each answered. hearth holds it as a template,
[`template/coordinator.py`](../template/coordinator.py), outside the package.
An app that coordinates a family, an **exemplar**, runs the template: it copies
the file whole, and writes what is its own in a module beside the copy. The
template imports nothing of hearth, so neither does the exemplar.

The template is where the coordinator changes. A copy is the template's text
but for its `Copied from:` line, which names the hearth revision it was taken at
and that text's digest, the first sixteen hex digits of its sha256:

```text
Copied from: hearth <revision>, sha256 <digest>.
```

Three facts about a copy are mechanical, at three strengths:

- **That it still agrees with its line,** the exemplar's own tests say with
  nothing of hearth. It catches a change made by hand or by a formatter; the
  digest is not a signature, and whoever changes the copy can change its line.
- **That its text is one hearth's template has had,** `hearth check --copy PATH`
  says from any hearth, a release included: `hearth.copies.KNOWN` lists every
  digest the template has had, and a digest it does not know cannot be said.
- **That it is the template at the revision it names, and how far the template
  has moved since,** `hearth check --copy PATH` says from a checkout of hearth
  with its history.

`hearth check --hub URL` judges the running exemplar from outside.

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
   revision a remote of hearth off this machine holds, since a copy is read
   against the revision it names: `hearth fork` and `hearth check --copy` say
   when none does.
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

3. In the exemplar's own tests, show that the copy still agrees with its line,
   so its own suite catches a change made by hand or by a formatter, and leave
   the copy out of the formatter, for paths given to it by name too (ruff's
   `force-exclude`, black's `force-exclude`):

   ```python
   def test_the_coordinator_is_the_template_its_copied_from_line_names():
       text = Path(coordinator.__file__).read_text(encoding="utf-8")
       line = re.search(r"^Copied from: hearth [0-9a-f]{7,40}, sha256 ([0-9a-f]{16})\.$", text,
                        re.MULTILINE)
       template = text.replace(line.group(0), "Copied from: this is the template.", 1)
       assert hashlib.sha256(template.encode("utf-8")).hexdigest()[:16] == line.group(1)
   ```

4. Run `hearth check --hub URL` against the running exemplar, and
   `hearth check --copy <exemplar>/coordinator.py` against its tree. Neither
   needs hearth in the exemplar's environment: each runs from hearth's own.

To take a later template, run `hearth fork` on the copy again. It refuses a
copy that is not the template, showing the lines that differ, and one taken at
a revision `HEAD` does not descend from, which writing could take back to an
older template. A change the exemplar needs is made in the template instead,
and a commit that changes the template adds its digest to `KNOWN`; hearth's
tests are red until it does.

`hearth check --copy` exits 0 when the copy is the template's text, 1 when it
is not, and 3 when it cannot say: a digest this hearth does not know, from a
newer hearth or from no template. How far the template has moved since is said,
not failed.

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

The template's tests are hearth's, and import it where it stands. An exemplar
runs its copy on its own locked versions, so its tests hold what it supplies,
with a delivery each way through the copy, and that the copy agrees with its
line. hearth lints the template with the rules of the exemplars that copy it,
since a copy is never edited to pass its owner's lint.
