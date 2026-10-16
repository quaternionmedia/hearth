# Hosting a member

A member answers [the contract](contract.md) the same way under every host.
Which host serves it is a deployment choice. `walkthrough/02-three-hosts.md`
runs all three against one check.

| Host | Call | Serves the routes at | Lifecycle |
|---|---|---|---|
| Alone | `kin.web.app(member, routers=...)` | the server's root | `start`/`stop` on the ASGI lifespan |
| Beside an aiohttp page | `kin.aio.attach(app, member)` | the page's root | `start`/`stop` on the application's startup and cleanup; open streams end at shutdown |
| Inside ShowRunner | `kin.showrunner.plugin(make, name=..., family=...)` | `<hub>/<name>` | made at the hub's startup from `[plugins.<name>]`, stopped at its shutdown |

`kin.web.router(member)` is the four routes alone, for a FastAPI app that
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

kin's plugin does the first and the last. The middle two are the hub's.

## Following from a page

`src/kin/static/follow.js` is a classic script. Vendor it beside the page and
load it with a `<script>` tag, or import it for its effect from a bundle; both
call `kin.follow`:

```js
const stop = kin.follow({events: '/family/events', state: '/family/state'},
                        snapshot => draw(snapshot),
                        {onLink: link => badge(link)});  // 'stream' | 'polling' | 'down'
```

It follows the stream, polls `state` only while the stream is down, and
reopens a stream the browser has given up on every ten seconds. Draw from the
snapshot alone: a page that missed an event draws the same thing at the next.

## Testing a member

`kin.testing` serves a member over a real socket and stands in for
ShowRunner, so a member's tests hold it to the contract without copies of
either:

```python
from kin import conformance, testing, web

def test_it_keeps_the_contract(member):
    with testing.serving(web.app(member)) as url:
        assert conformance.check(url, action={"clock": "lap"}).status == 0
```

`testing.serving_aiohttp(application)` and `testing.showrunner_hub()` do the
same for the other two hosts.
