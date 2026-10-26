# The demo

The demo is a show, Loopback: ShowRunner, by its own command, on a show whose
nine cues each show a part of the arrangement, each a round trip through the
hub. Nothing of the demo's own runs beside it.

```bash
uv run python demo/loopback.py --dev <dev>
```

`<dev>` holds the member checkouts on their family branches: ShowRunner,
ShowStopper, carlos, joe and leo. The script writes the hub's show.toml and
runs ShowRunner in the foreground; open `http://127.0.0.1:18700/script` for
the script with its cues, and press GO at `http://127.0.0.1:18700/programmer`.
It prints each member's page. Each run starts from an empty `--work`
directory, and refuses to empty one it did not make or to start while its
ports are in use. Ctrl+C stops the show, and with it every member it started.

## The show

[`demo/show/`](../demo/show) is the show: `loopback.fountain`, its script, and
`cues.toml`, its cues. Each cue sits on the line of the script it begins with;
its notes say what to look for, and its family block is what GO fires. The
show is made through the hub's own routes at its first start.

| Cue | On the line | What it shows |
|---|---|---|
| 1 House open | The house opens. | a cue's family block reaching ShowStopper and carlos by push, and leo by its stream |
| 2 Count in | Count me in. | the metronome, hosted in the hub, answering 503 *not ready*, its device missing; the cue goes on |
| 3 Second tune | The band plays the second tune. | the rack, of `instruments`, refused by a `show-control` hub, 503 *not hosted* |
| 4 Device in | A stagehand plugs in the metronome's device. | the hub's retry finding the metronome ready, with no restart |
| 5 The solo | Here comes the solo. | the metronome answering 200 |
| 6 carlos down | carlos falls over. | carlos's process knocked over, and brought back by the show's supervisor |
| 7 carlos back | carlos is back, and is someone new. | the hub's audit crediting the cue to carlos's new instance |
| 8 The checks | The stagehand holds every part to the contract. | `hearth check` on each member served alone and on the hub, `hearth check --copy` on its coordinator |
| 9 Curtain | The curtain falls. | the clock stopped, leo's last song |

leo is a page, and the page is what follows the hub: with no page of it open,
its deliveries wait unread, and the audit says so.

## What runs

| Part | What it is | How it runs |
|---|---|---|
| The hub | ShowRunner, running its copy of the coordinator template | `sr start --config show.toml`, by ShowRunner's own CLI module |
| The show | the `loopback` plugin: the members kept running, the show made | found by ShowRunner's loader through the `showrunner` entry point, from the demo's own [`plugins/`](../demo/plugins) package |
| The stagehand | a member hosted in the hub that does the show's acts backstage: plugs in a device, knocks a member over, runs the checks | the same |
| The metronome | a member hosted in the hub, whose device is missing at first | the same |
| The rack | an `instruments` member offered to the hub, which refuses it | the same |
| ShowStopper's clock extension | a clock layer type, a Clock layer, a ⏱ chip under each Clock cue | found through ShowStopper's `showrunner` entry point |
| ShowStopper, carlos, joe, leo | members beside the hub | `<member> serve`, each in its own checkout and process, kept running by `hearth.supervise` in the show's plugin |

What each cue did is in the hub's audit at `/family/`, and the stagehand's
acts and the checks' verdicts are its state at `/stagehand/family/state` and
lines in ShowRunner's log.

**Nothing of ShowRunner is imported or changed.** The hub's run adds hearth,
the demo's plugins and ShowStopper to ShowRunner's environment for that run
alone (`uv run --with-editable`), and ShowRunner finds them as it finds any
installed plugin. Its show.toml sets each up as any show's would:
`[plugins.family]` names the members, `[plugins.metronome]` the metronome's
device, `[plugins.stagehand.devices]` what the stagehand may plug in,
`[plugins.loopback]` the show's script, cues and the members it keeps running,
and `[plugins] disabled` turns off ShowStopper's hosted clock, since the clock
runs beside the hub. `tests/test_demo.py` fails if the script imports
ShowRunner, by name or otherwise, edits `sys.path`, sets an attribute on a
module, or runs anything of its own beside the show, or if what runs inside
the hub, the demo's plugins and hearth's host, sets one.

The hub stops its members when it stops, since its plugin keeps them; a hub
that should outlive a crash of its own is its machine's service manager's to
keep, not the show's.

## Its ports

The hub takes `--port` (18700), and the members `--port` plus 10, 20, 30, 31
and 32 (joe's page, API and its qmcp address), and 40.
