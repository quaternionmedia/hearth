# Hosting a member

A member answers [the contract](contract.md) the same way under every host;
which host serves it is a deployment choice. A part that adds to the hub's own
data or pages, such as a layer type or a chip under a cue, is a ShowRunner
plugin on ShowRunner's hooks, and hearth has nothing to say about it.

| Host | Call | Serves the routes at | Lifecycle |
|---|---|---|---|
| Alone | `hearth.web.app(member, routers=...)` | the server's root | `start` and `stop` on the ASGI lifespan |
| Beside an aiohttp page | `hearth.aio.attach(app, member)` | the page's root | `start` and `stop` on the application's startup and cleanup; open streams end at shutdown |
| Inside ShowRunner | `hearth.showrunner.plugin(make, name=..., family=...)` | `<hub>/<name>` | made at the hub's startup from `[plugins.<name>]`, stopped at its shutdown |

`hearth.web.router(member)` is the four routes alone, for a FastAPI app that
exists already; `member` may be a callable that returns the member once the
app has made it, and the routes answer 503 until then. FastAPI keeps an
included router as one entry in `app.routes`, and
`fastapi.routing.iter_route_contexts` lists hearth's routes among an app's.
[`walkthrough/02-three-hosts.md`](../walkthrough/02-three-hosts.md) runs all
three hosts against one check.

## Which host, by family

A hub hosts in its process only members of its own family. `plugin` refuses
any other, and a member of another family is served alone and named to the
hub by its URL.

| Family | Its coordinator | A member is |
|---|---|---|
| show-control | ShowRunner | alone, inside ShowRunner, or both |
| instruments | none yet | alone, reached by URL |
| performer-display | none | alone, reached by URL, or a page that follows the hub's stream |

A member with a device or a native library is served alone whatever its
family: a crash in either, a page that blocks the event loop, or a dependency
the hub cannot share takes a hosted member's hub down with it, and no code
catches that. `bench/hosting.py` breaks a member each of these ways, hosted
and alone.

## Inside ShowRunner

Register the plugin under the `showrunner` entry-point group. ShowRunner's
loader calls `ep.load()` and instantiates the result only when it is a class,
so the entry point names a module attribute that **is** the plugin, made when
its module is imported, and imported only by a hub loading its plugins:

```toml
[project.entry-points.showrunner]
showstopper = "showstopper_hosted:plugin"
```

```python
# showstopper_hosted.py
import family
plugin = family.showrunner_plugin()
```

The plugin's `__name__` is the member's name, which `[plugins] disabled`
matches; its settings are the hub's `[plugins.<name>]` table.

- **It asks what the hub is first.** When the hub lacks
  `showrunner_hub_identity` or `showrunner_family_members`, or names another
  family than the member's, it hosts nothing and says why once; the member's
  routes answer 503 with the reason.
- **It hands the hub's coordinator the member's `receive`** through
  `showrunner_family_members`, so a cue is delivered by a call and audited as
  `via: "local"`. A URL for the same name in `[plugins.family.members]` wins
  over the hosted member.
- **A member that cannot start leaves the hub running.** When `make` or
  `start` raises, say for a device not plugged in, its routes answer 503 with
  the reason, and the start is tried again after 1, 2, 4… seconds up to the
  plugin's `retry_cap` (30 s by default) until it succeeds or the hub stops.
  The reason is logged once, and again when it changes.

## What a hub owes a member it hosts

- `start` and `stop`, once each, on the server's own lifecycle.
- A failure at start, stop or delivery recorded against that member, with the
  others carried on.
- The member imported only when it is enabled.
- The member's own settings table, and nothing else of the hub's.

hearth's plugin does the first and the last, and catches its own member's
failure to start. The hub's coordinator records each delivery's failure
against its member. Isolating every plugin's startup, and importing only what
is enabled, are the hub's.

## Beside the hub, kept running

`hearth.supervise` starts members served alone, knows each is up when its
`/family/identity` answers, and restarts one that stops: 1 s after each of
its first three exits, then after a wait doubling to 60 s, never giving up, as
Bitfocus Companion restarts its modules.

```python
from hearth.supervise import Spec, Supervisor

supervisor = Supervisor([Spec("carlos", ["uv", "run", "carlos", "serve", "--port", "18720",
                                         "--state", "state/carlos"],
                              "http://127.0.0.1:18720", cwd="../carlos")])
supervisor.start()
supervisor.wait_up(60)
```

Each restart is a new instance, and every answer to a cue names the instance
that took it, so the hub credits each delivery to the right one.

## Following from a page

`src/hearth/static/follow.js` is a classic script: vendor it beside the page
and load it with a `<script>` tag, or import it for its effect from a bundle.
Both give `hearth.follow`:

```js
const stop = hearth.follow({events: '/family/events', state: '/family/state'},
                           snapshot => draw(snapshot),
                           {onLink: link => badge(link)});  // 'stream' | 'polling' | 'down'
```

It follows the stream, polls `state` only while the stream is down, and
reopens a stream the browser gave up on every ten seconds. Draw from the
snapshot alone: a page that missed an event draws the same thing at the next.

## Testing a member

`hearth.testing` serves a member over a real socket and stands in for
ShowRunner, so a member's tests hold it to the contract with a copy of
neither:

```python
from hearth import conformance, testing, web

def test_it_keeps_the_contract(member):
    with testing.serving(web.app(member)) as url:
        assert conformance.check(url, action={"clock": "lap"}).status == 0
```

`testing.serving_aiohttp(application)` and `testing.showrunner_hub()` do the
same for the other two hosts.
