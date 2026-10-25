# The demo

`demo/proposal.py` runs a performing family on one machine, every part as it
runs at a show, and serves a page that says what to try.

```bash
uv run python demo/proposal.py --dev <dev>
```

`<dev>` holds the member checkouts on their family branches: ShowRunner,
ShowStopper, carlos, joe and leo. Open `http://127.0.0.1:18701/`. Each run
starts from an empty `--work` directory, and refuses to empty one it did not
make or to start while its ports are in use. Ctrl+C stops everything it
started.

## What runs

| Part | What it is | How it runs |
|---|---|---|
| The hub | ShowRunner, running its copy of the coordinator template | `sr start --config show.toml`, by ShowRunner's own CLI module, in a process of its own |
| ShowStopper's clock extension | an extension in the hub: a clock layer type, a Clock layer, a ⏱ chip under each Clock cue | found by ShowRunner's loader through the `showrunner` entry point |
| The metronome | a member hosted in the hub, whose device is missing at startup | the same, from the demo's own [`plugins/`](../demo/plugins) package |
| The rack | an `instruments` member offered to the hub, which refuses it | the same |
| ShowStopper, carlos, joe, leo | members beside the hub | `<member> serve`, each in its own checkout and process |
| The panel | the demo's own page | this script, on the port above the hub's |

Every process, the hub's included, is kept running by `hearth.supervise`.

**Nothing of ShowRunner is imported or changed.** The hub's run adds hearth,
the demo's plugins and ShowStopper to ShowRunner's environment for that run
alone (`uv run --with-editable`), and ShowRunner finds them as it finds any
installed plugin. Its `show.toml` sets them up as any show's would:
`[plugins.family]` names the members, `[plugins.metronome]` the metronome's
device, and `[plugins] disabled` turns off ShowStopper's hosted clock, since
the clock runs beside the hub. The show is made through the hub's own routes,
and the panel reads the running parts over HTTP. Beside its checks of each
member and of the hub, the panel says whether the hub's coordinator is still
hearth's template (`hearth check --copy`). `tests/test_demo.py` fails if the
demo imports ShowRunner, by name or otherwise, edits `sys.path` or sets an
attribute on a module, or if what runs inside the hub, the demo's plugins and
hearth's host, sets one.

## What to try

The panel lists these, with buttons for each:

1. **Fire the five cues.** Each one's family block reaches every member it
   names: pushed to ShowStopper, carlos and joe, read by leo from the hub's
   stream, handed to the metronome by a call. The metronome answers 503 *not
   ready*, and the rack 503 *not hosted*, naming both families. Neither stops
   the hub or the cue.
2. **Plug in the metronome's device.** The hub's next retry finds it ready,
   with no restart.
3. **Crash carlos.** It is back as a new instance in a few seconds, and the
   hub's audit credits the next cue to it, marking the answers of the one
   before.
4. **Crash the hub.** It comes back with its show, and the members run on.
5. **Open the script.** The ⏱ chip under each Clock cue drives the clock
   through the hub.

leo is a page, and the page is what follows the hub: with no page of it
open, its deliveries wait unread.

## Its ports

The hub takes `--port` (18700), the panel the one above it, and the members
`--port` plus 10, 20, 30 and 31 (joe's page and API), and 40.
