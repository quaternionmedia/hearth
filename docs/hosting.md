# Hosting a member

A member answers [the contract](contract.md) the same way under every host.
Which host serves it is a deployment choice. `walkthrough/02-three-hosts.md`
runs all three against one check, and `demo/proposal.py` runs the family with
ShowRunner as the hub.

**Extend the hub in-process; act on a cue across the contract.** A part that
adds to the hub's data and pages -- a layer type, a preview chip under a cue,
a cue-list importer -- is a ShowRunner plugin on ShowRunner's own hooks, and
hearth has nothing to say about it. A part that acts on a cue is a member, and
this page is about where it runs. A member may ship both: ShowStopper's clock
is a member, and `showstopper_clock` is a small extension that gives it a
layer and a chip in the hub's script page. The two meet in the hub's data and
the cue's family block, never in each other's code.

| Host | Call | Serves the routes at | Lifecycle |
|---|---|---|---|
| Alone | `hearth.web.app(member, routers=...)` | the server's root | `start`/`stop` on the ASGI lifespan |
| Beside an aiohttp page | `hearth.aio.attach(app, member)` | the page's root | `start`/`stop` on the application's startup and cleanup; open streams end at shutdown |
| Inside ShowRunner | `hearth.showrunner.plugin(make, name=..., family=...)` | `<hub>/<name>` | made at the hub's startup from `[plugins.<name>]`, stopped at its shutdown |

`hearth.web.router(member)` is the four routes alone, for a FastAPI app that
already exists; `member` may be a callable returning the member, for an app
that makes it after the routes are mounted. Until it does, they answer 503.

## Which host, by family

A hub hosts in its process only members of its own family. A member of
another family is served alone and named to the hub by URL. `plugin` refuses
the other case.

| Family | Its hub | Hosting |
|---|---|---|
| show-control | ShowRunner | alone, inside ShowRunner, or both |
| instruments | none | alone, reached by URL |
| performer-display | none | alone, reached by URL, or a page that follows the hub's stream |

## Inside ShowRunner

The plugin answers ShowRunner's hooks: `showrunner_register`,
`showrunner_startup`, `showrunner_shutdown`, `showrunner_get_routes`,
`showrunner_get_nav` and `showrunner_family_members`. The last hands
ShowFamily the member's `receive`, found at each call, so ShowFamily delivers
a cue by a call and audits it as `via: "local"`. A URL for the same name in
`[plugins.family.members]` wins over the hosted member.

At the hub's startup the plugin first asks what the hub is. It hosts nothing,
and says why once, when the hub does not declare `showrunner_hub_identity`
and `showrunner_family_members`, or when the hub's identity names another
family than the member's. Either way the member's routes answer 503 with the
reason.

**A member that cannot start is not ready, and the hub runs on.** `make` or
`start` raising -- a device not plugged in -- leaves the member's routes
answering 503 saying why, and ShowFamily audits a cue to it as an error. The
start is tried again after 1, 2, 4… seconds up to `RETRY_CAP` (30), until it
succeeds or the hub stops, so a device plugged in late is picked up without a
restart. The reason is logged once, and again only when it changes; the try
that succeeds is logged too.

Register it under the `showrunner` entry-point group. ShowRunner's loader
calls `ep.load()` and instantiates the result only when it is a class, so the
entry point names a module attribute that **is** the plugin, made when that
module is imported:

```toml
[project.entry-points.showrunner]
showstopper = "showstopper_hosted:plugin"
```

```python
# showstopper_hosted.py -- imported only by a hub loading its plugins
import family
plugin = family.showrunner_plugin()
```

The plugin's `__name__` is the member's name, which is what `[plugins]
disabled` matches.

## What a hub owes a member it hosts

- `start` and `stop`, once each, on the server's own lifecycle.
- A failure at start, stop or delivery recorded against that member, and the
  others carried on.
- The member imported only when it is enabled.
- The member's own settings table, and nothing else of the hub's
  configuration.

hearth's plugin does the first and the last, and catches a failure of its own
member's start. ShowFamily records each delivery's failure against its member.
A failure in another plugin's startup, and importing only what is enabled,
are the hub's.

What no host can catch in code is a crash (a native library, `os._exit`), a
page that blocks the event loop, or a dependency the hub cannot share: a
hosted member takes the hub with it. `bench/hosting.py` breaks a member each
of these ways, hosted and alone. A member with a device or a native library
is served alone.

## Beside the hub, kept running

`hearth.supervise` starts members served alone, knows each is up when its
`/family/identity` answers, and starts it again when it stops: 1 s after each
of the first three stops, then doubling to 60 s, never giving up, as Bitfocus
Companion restarts its modules.

```python
from hearth.supervise import Spec, Supervisor

supervisor = Supervisor([Spec("carlos", ["uv", "run", "carlos", "serve", "--port", "18720",
                                         "--state", "state/carlos"],
                              "http://127.0.0.1:18720", cwd="../carlos")])
supervisor.start()
supervisor.wait_up(60)
```

Each restart is a new instance, and the hub knows it: every answer to a cue
names the instance that took it, and ShowFamily credits the delivery to that
instance.

## Following from a page

`src/hearth/static/follow.js` is a classic script. Vendor it beside the page and
load it with a `<script>` tag, or import it for its effect from a bundle; both
call `hearth.follow`:

```js
const stop = hearth.follow({events: '/family/events', state: '/family/state'},
                        snapshot => draw(snapshot),
                        {onLink: link => badge(link)});  // 'stream' | 'polling' | 'down'
```

It follows the stream, polls `state` only while the stream is down, and
reopens a stream the browser has given up on every ten seconds. Draw from the
snapshot alone: a page that missed an event draws the same thing at the next.

## Testing a member

`hearth.testing` serves a member over a real socket and stands in for
ShowRunner, so a member's tests hold it to the contract without copies of
either:

```python
from hearth import conformance, testing, web

def test_it_keeps_the_contract(member):
    with testing.serving(web.app(member)) as url:
        assert conformance.check(url, action={"clock": "lap"}).status == 0
```

`testing.serving_aiohttp(application)` and `testing.showrunner_hub()` do the
same for the other two hosts.
