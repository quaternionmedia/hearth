# The coordinator

A coordinator delivers each fire's family block to the members it names and
keeps what each answered. hearth holds it as one text,
[`src/hearth/coordinator.py`](../src/hearth/coordinator.py), which imports
nothing else of hearth. An app that coordinates a family, an **exemplar**,
runs it one of two ways:

- **Import it**, depending on `qm-hearth` at a version:
  `from hearth import coordinator`.
- **Copy it whole** with `hearth fork`, where the app's maintainer takes no
  dependency. ShowRunner runs such a copy.

apothecary imports it, as the `irl` family's hub.

Either way the exemplar writes what is its own in a module beside it.

## What an exemplar supplies

| | ShowRunner | The looper in `tests/test_coordinator.py` | apothecary |
|---|---|---|---|
| What fires, and when | a cue: the programmer's GO, or any path that announces `cue.fired` | the downbeat of a bar, at `POST /beat` | a hold of a site's wiring, when the wiring changes or is sent |
| Where the block is | the cue's `actions["family"]` | its own | its own, one member's action to a delivery |
| Where the coordinator runs | ShowFamily, a pluggy plugin in `plugins/family/__init__.py`, beside its copy in `plugins/family/coordinator.py`; its table is `[plugins.family]` | a FastAPI app; its table is `[looper.family]` | imported, in `apothecary/family/hub.py`, on its FastAPI app; its table is `family.json` in the state folder |
| The members in its own process | members of `show-control`, from `showrunner_family_members` | none | none |
| What it is | `showrunner`, of `show-control` | `looper`, of `instruments` | `apothecary`, of `irl` |

```python
from hearth import coordinator   # in a copy's exemplar: from . import coordinator

running = coordinator.from_table(settings, local=hosted, table="[looper.family]")
app.include_router(coordinator.router(
    lambda: running, lambda: coordinator.identity("looper", "instruments", version),
    table="[looper.family]"))
running.fire({"number": "3", "name": "Second tune", "fired_at": fired_at}, block)
```

Close it at the app's stop. `hearth check --hub URL` judges the running
exemplar from outside, whichever way it runs the text. An importing exemplar
takes a fix at its next dependency bump, and the version it pins names the
contract's conformance version ([`contract.md`](contract.md)).

## A copy

A copy is the template's text but for its `Copied from:` line, which names
the hearth revision it was taken at and the text's digest, the first sixteen
hex digits of its sha256:

```text
Copied from: hearth <revision>, sha256 <digest>.
```

1. From hearth's checkout, write the template into the exemplar:
   `uv run hearth fork <exemplar>/coordinator.py`. Fork from a revision a
   remote of hearth holds, since a copy is read against the revision it
   names; `fork` and `check --copy` say when none does.
2. In the exemplar's tests, hold the copy to its line, and leave the copy out
   of the formatter (ruff's and black's `force-exclude`):

   ```python
   def test_the_coordinator_is_the_template_its_copied_from_line_names():
       text = Path(coordinator.__file__).read_text(encoding="utf-8")
       line = re.search(r"^Copied from: hearth [0-9a-f]{7,40}, sha256 ([0-9a-f]{16})\.$", text,
                        re.MULTILINE)
       template = text.replace(line.group(0), "Copied from: this is the template.", 1)
       assert hashlib.sha256(template.encode("utf-8")).hexdigest()[:16] == line.group(1)
   ```

3. Run `hearth check --copy <exemplar>/coordinator.py` from hearth's own
   environment; the exemplar's needs nothing of hearth.

Three facts about a copy are mechanical, at three strengths. That it agrees
with its line, the exemplar's own test says; the digest is not a signature,
since whoever changes the copy can change the line. That its text is one the
template has had, `hearth check --copy` says from any hearth, by
`hearth.copies.KNOWN`. That it is the template at the revision it names, and
how far the template has moved since, `hearth check --copy` says from a
checkout with hearth's history.

To take a later template, run `hearth fork` on the copy again. It refuses a
copy that is not the template, showing the lines that differ, and one taken
at a revision `HEAD` does not descend from. A change the exemplar needs is
made in the template, and a commit that changes the template adds the new
text's digest to `KNOWN`; hearth's tests are red until it does.
`check --copy` exits 0 for the template's text, 1 for a changed copy, and 3
when it cannot say.

## What it does

- **Three ways to a member:** pushed to at its URL, handed the body by a call
  when hosted in the exemplar's process, or read by the member itself, whose
  first read after a fire is the delivery. A URL wins over a hosted member of
  the same name, and either over a pull.
- **A fire never waits.** Each member has one queue, so its blocks arrive in
  the order they fired, and one HTTP client for the coordinator's life. Every
  request has a timeout.
- **Every outcome is kept** at `GET /family/`: the member, how it went, the
  status, the error, the milliseconds from the fire, and the instance that
  took it. A member that is down, slow or refuses is recorded, never raised.
- **It says what it is** at `GET /family/identity`, the instance being the
  process, so a coordinator remade when its settings change is the same
  instance to its members.
- **A malformed settings entry is skipped and said** in the exemplar's own
  table's words, through its logger.

hearth's tests import the text where it stands and lint it with the rules of
the exemplars that copy it, since a copy is never edited to pass its owner's
lint. An exemplar's tests hold what it supplies, with a delivery each way.
