"""The proposal, running: extensions in the hub, members beside it, one contract either way.

What `plans/plugin-or-server.md` in the corpus proposes, on one machine:

* **The hub** is ShowRunner, in this process. It says what it is
  (`GET /family/identity`), delivers each cue's family block, and asks every
  member it pushes to who it is, so its audit names the instance that answered.
* **An extension in the hub**: ShowStopper's clock extension adds a `clock`
  layer type, a Clock layer and a ⏱ chip under each cue that drives the clock
  in `/script`. It reads the hub's data and never talks to the clock.
* **Members beside the hub**, each its own process, kept running by
  `kin.supervise`: ShowStopper's clock, carlos, joe (pushed to) and leo (which
  follows the hub's stream). Crash one from the panel and watch it come back
  as a new instance.
* **A member hosted in the hub**: a metronome whose MIDI device is missing at
  startup. The hub runs on; the metronome is *not ready* and retried, and
  becomes ready when its device is "plugged in" from the panel.
* **The family border**: an instruments-family rack offered to the hub as a
  hosted plugin is refused, and says why.

Run it in the environment of a ShowRunner checkout carrying the family stack::

    cd <dev>/ShowRunner
    uv run --no-sync python <kin>/demo/proposal.py --dev <dev>

`<dev>` holds the member checkouts (ShowStopper, carlos, joe, leo) on their
family branches; this checkout's kin and `<dev>/ShowStopper` are put on the
path. Each run begins from nothing in a fresh `--work` directory. Open
`http://127.0.0.1:18700/demo`; the panel says what to try. Ctrl+C stops
everything it started.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

# This checkout's kin, whatever the hub's environment holds.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import kin
from kin import conformance
from kin import showrunner as hosting
from kin.supervise import Spec, Supervisor, _kill_tree

MARK = ".kin-proposal"  # a --work directory this demo made, and may empty again

SCRIPT = """Title: Proposal night

INT. THE ROOM - NIGHT

The house opens. A clock waits at zero.

PERFORMER
Count me in.

The band plays the second tune.

PERFORMER
Here comes the solo.

The curtain falls.
"""

# What a stage manager writes on each cue, for people; the family block is its actions.
NOTES = {1: "When the house is settled", 2: "On the performer's nod", 3: "Band in on the downbeat",
         4: "Hold for the solo", 5: "Slow fade with the curtain"}

# (number, name, layer, the line it sits on, its family block)
CUES = [
    (1, "House open", "Clock", "The house opens.",
     {"showstopper": {"clock": "reset"}, "leo": {"song": "Autumn Leaves"},
      "carlos": {"patch": "novation.launchpad-x.complex"}}),
    (2, "Count in", "Sound", "Count me in.",
     {"showstopper": {"clock": "start"}, "metronome": {"beat": 120},
      "joe": {"take": {"notes": ["C4", "E4", "G4", "C5"], "seconds_per_note": 0.5}}}),
    (3, "Second tune", "Stage", "The band plays the second tune.",
     {"leo": {"song": "Blue Bossa"}, "carlos": {"turn": "back"},
      "metronome": {"beat": 96}, "rack": {"turn": "back"}}),
    (4, "The solo", "Sound", "Here comes the solo.",
     {"showstopper": {"clock": "lap"}, "carlos": {"patch": "moog.dfam.complex"},
      "joe": {"take": {"notes": ["G3", "B3", "D4", "F4", "G4"], "seconds_per_note": 0.5}}}),
    (5, "Curtain", "Clock", "The curtain falls.",
     {"showstopper": {"clock": "stop"}, "leo": {"song": "Take The A Train"}}),
]


class Metronome(kin.Member):
    """A member hosted in the hub, whose MIDI clock device may not be there yet."""

    name, family, verbs = "metronome", "show-control", ("beat",)

    def __init__(self, device: Path) -> None:
        super().__init__()
        self.device, self.bpm, self.beats = device, None, 0

    def start(self) -> None:
        if not self.device.exists():
            raise OSError(f"no MIDI clock device 'Beat Box' (it appears as {self.device.name})")

    def understand(self, action):
        bpm = action["beat"]
        if not isinstance(bpm, int) or not 20 <= bpm <= 300:
            raise kin.Refused(f"a beat is 20 to 300 bpm, not {kin.shown(bpm)}")

        def change():
            self.bpm, self.beats = bpm, self.beats + 1

        return change

    def state(self) -> dict:
        return {"bpm": self.bpm, "beats": self.beats}


class Rack(kin.Member):
    """An instruments-family member, offered to a show-control hub: it must be refused."""

    name, family, verbs = "rack", "instruments", ("turn",)

    def understand(self, action):
        return lambda: None

    def state(self) -> dict:
        return {}


def fresh(work: Path | None) -> Path:
    """The run's state directory, empty: a new one, or one an earlier run made."""
    if work is None:
        work = Path(tempfile.mkdtemp(prefix="kin-proposal-"))
    work = work.resolve()
    if work.exists() and any(work.iterdir()):
        if not (work / MARK).exists():
            raise SystemExit(f"{work} holds files this demo did not make; name an empty "
                             f"directory, or leave --work out")
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / MARK).write_text("made by kin/demo/proposal.py; emptied at each run\n",
                             encoding="utf-8")
    return work


def members(dev: Path, work: Path, port: int) -> list[Spec]:
    def run(member: str, *args: str) -> list[str]:
        checkout = {"showstopper": "ShowStopper"}.get(member, member)
        return ["uv", "run", "--no-sync", "--project", str(dev / checkout), member, "serve",
                "--host", "127.0.0.1", *args, "--state", str(work / member)]

    clean = {"VIRTUAL_ENV": None, "PYTHONPATH": None, "UV_PROJECT_ENVIRONMENT": None}
    # Each runs in its own checkout: carlos, for one, finds itself from where it starts.
    return [
        Spec("showstopper", run("showstopper", "--port", str(port + 10)),
             f"http://127.0.0.1:{port + 10}", cwd=str(dev / "ShowStopper"), env=clean),
        Spec("carlos", run("carlos", "--port", str(port + 20)),
             f"http://127.0.0.1:{port + 20}", cwd=str(dev / "carlos"), env=clean),
        Spec("joe", run("joe", "--port", str(port + 30), "--api-port", str(port + 31),
                        "--qmcp-url", f"http://127.0.0.1:{port + 32}"),
             f"http://127.0.0.1:{port + 31}", cwd=str(dev / "joe"), env=clean),
        Spec("leo", run("leo", "--port", str(port + 40), "--follow", f"http://127.0.0.1:{port}"),
             f"http://127.0.0.1:{port + 40}", cwd=str(dev / "leo"), env=clean, ready="/"),
    ]


def hub(work: Path, port: int, extras: list):
    """ShowRunner as the hub, with the demo's plugins registered beside its own."""
    import showrunner.app as app_module

    state = work / "hub"
    state.mkdir(parents=True, exist_ok=True)
    config = state / "show.toml"
    config.write_text(
        f'[database]\npath = "{(state / "show.db").as_posix()}"\n\n'
        f"[server]\nport = {port}\n\n"
        '[plugins.family]\npull = ["leo"]\ntimeout = 5.0\n\n'
        "[plugins.family.members]\n"
        f'showstopper = "http://127.0.0.1:{port + 10}"\n'
        f'carlos = "http://127.0.0.1:{port + 20}"\n'
        f'joe = "http://127.0.0.1:{port + 31}"\n\n'
        f'[plugins.metronome]\ndevice = "{(work / "beat-box.device").as_posix()}"\n',
        encoding="utf-8")
    original = app_module.get_plugin_manager

    def with_the_demo(config):
        pm = original(config)
        for plugin in extras:
            pm.register(plugin, name=getattr(plugin, "__name__", None))
        return pm

    app_module.get_plugin_manager = with_the_demo
    try:
        return app_module.ShowRunner(config_path=config)
    finally:
        app_module.get_plugin_manager = original


def seed(base: str) -> tuple[int, int]:
    """The show, made through the hub's routes and its database: (show id, cue list id)."""
    from showrunner.models import Cue, CueList, Script
    from showrunner.plugins.db import get_db

    show = httpx.post(f"{base}/db/shows", params={"name": "Proposal night"}).json()["id"]
    lines = SCRIPT.splitlines()
    with get_db().session() as session:
        session.add(Script(show_id=show, title="Proposal night", format="fountain",
                           content=SCRIPT))
        cue_list = CueList(show_id=show, name="Main")
        session.add(cue_list)
        session.commit()
        session.refresh(cue_list)
        for number, name, layer, line, family in CUES:
            session.add(Cue(cue_list_id=cue_list.id, number=str(number), name=name, layer=layer,
                            notes=NOTES[number], actions={"family": family},
                            script_line=next(i for i, text in enumerate(lines, 1)
                                             if text.startswith(line)),
                            script_char=0))
        session.commit()
        return show, cue_list.id


PANEL = """<!doctype html><meta charset=utf-8><title>The proposal, running</title>
<style>
:root{--bg:#f7f7f4;--fg:#1c1c1a;--muted:#6a6a64;--line:#dddcd5;--ok:#1f7a3a;--bad:#b3261e;--wait:#8a6d00}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecece8;--muted:#a2a29b;--line:#33332f;--ok:#5fc77f;--bad:#ff8a80;--wait:#e2c25b}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px;display:grid;gap:22px}
h1{margin:0;font-size:1.5rem}h2{margin:0 0 6px;font-size:1.05rem}p{margin:0;color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:.9rem}td,th{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600}.up,.pass{color:var(--ok);font-weight:600}.stopped,.restarting,.fail,.refused{color:var(--bad);font-weight:600}
.starting,.waiting{color:var(--wait);font-weight:600}code{font-size:.85em}
ol{margin:6px 0 0;padding-left:22px}li{margin:3px 0}.now{font-weight:700}.stale{color:var(--bad)}
.row{display:flex;flex-wrap:wrap;gap:8px}button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:transparent;color:inherit;cursor:pointer}
button:hover{border-color:var(--fg)}a{color:inherit}.wrap{overflow-x:auto}
</style>
<main>
<div><h1>The proposal, running</h1>
<p>Extensions in the hub; members beside it, kept running; one contract either way. This panel asks <code>/demo/state</code> once a second.</p></div>
<div><h2>What to try</h2><ol>
<li><b>Fire the five cues.</b> Each one's family block goes to every member it names: pushed to ShowStopper, carlos and joe in milliseconds, read by leo from the hub's stream, handed in-process to the metronome. leo is a page, and the page is what follows: open <i>leo, following the hub</i> under Look and its deliveries are read in a few milliseconds; with no page open they wait unread. The metronome answers 503 <i>not ready</i>, its device missing; the rack 503 <i>not hosted</i>, being another family's. Neither stops the hub or the cue.</li>
<li><b>Plug in the metronome's device.</b> Within eight seconds the hub's retry finds it ready. Go back to cue 1 and fire cue 2: it answers 200.</li>
<li><b>Crash carlos.</b> The supervisor brings it back as a new instance in about a second. Fire a cue naming carlos (1, 3 or 4): the audit credits the new instance, and marks the answers of the one before it.</li>
<li><b>Open the script.</b> The &#x23F1; chip under each Clock cue drives the clock through the hub, by ShowStopper's extension; the clock itself is the member beside the hub.</li>
</ol></div>
<div><h2>Act</h2><div class=row>
<button onclick="post('/demo/go')">Fire the next cue</button>
<button onclick="post('/demo/reset')">Back to cue 1</button>
<button onclick="post('/demo/metronome/plug')">Plug in the metronome's device</button>
<button onclick="post('/demo/crash/carlos')">Crash carlos</button>
<button onclick="post('/demo/crash/showstopper')">Crash ShowStopper</button>
</div><p id=said></p></div>
<div><h2>Look</h2><div class=row id=links></div></div>
<div><h2>The cues</h2><div class=wrap><table id=sheet></table></div></div>
<div><h2>Members beside the hub (supervised)</h2><div class=wrap><table id=sup></table></div></div>
<div><h2>In the hub</h2><div class=wrap><table id=hosted></table></div></div>
<div><h2>Deliveries, newest first (the hub's audit)</h2><div class=wrap><table id=audit></table></div></div>
<div><h2>The contract, checked</h2><div class=wrap><table id=checks></table></div></div>
</main>
<script>
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function post(path){const r=await fetch(path,{method:'POST'});document.getElementById('said').textContent=JSON.stringify(await r.json());}
function rows(id, head, body){document.getElementById(id).innerHTML='<tr>'+head.map(h=>'<th>'+h+'</th>').join('')+'</tr>'+body.join('');}
async function tick(){
  try{
    const s=await (await fetch('/demo/state',{cache:'no-store'})).json();
    document.getElementById('links').innerHTML=s.links.map(([t,u])=>'<a href="'+esc(u)+'" target=_blank>'+esc(t)+'</a>').join(' · ');
    rows('sheet',['cue','name','layer','on the line','names'],s.sheet.map(c=>
      '<tr class="'+(c.fired?'now':'')+'"><td>'+esc(c.number)+(c.fired?' &#x25C0; last fired':'')+'</td><td>'+esc(c.name)+'</td><td>'+esc(c.layer)+'</td><td>'+esc(c.line)+'</td><td>'+esc(c.members.join(', '))+'</td></tr>'));
    rows('sup',['member','state','instance','pid','restarts','exits'],Object.entries(s.supervised).map(([n,w])=>
      '<tr><td>'+esc(n)+'</td><td class="'+esc(w.state)+'">'+esc(w.state)+'</td><td><code>'+esc(w.instance)+'</code></td><td>'+esc(w.pid)+'</td><td>'+esc(w.restarts)+'</td><td>'+esc(w.exits.join(', '))+'</td></tr>'));
    rows('hosted',['what','kind','state'],s.hosted.map(h=>'<tr><td>'+esc(h.name)+'</td><td>'+esc(h.kind)+'</td><td class="'+esc(h.css)+'">'+esc(h.state)+'</td></tr>'));
    rows('audit',['cue','member','via','status','ms','instance','error'],s.audit.map(o=>
      '<tr><td>'+esc(o.cue&&o.cue.number)+'</td><td>'+esc(o.member)+'</td><td>'+esc(o.via)+'</td><td class="'+(o.error?'fail':'pass')+'">'+esc(o.status)+'</td><td>'+esc(o.ms)+'</td><td><code class="'+(o.stale?'stale':'')+'">'+esc(o.instance)+'</code>'+(o.stale?' (before a restart)':'')+'</td><td>'+esc(o.error)+'</td></tr>'));
    rows('checks',['what','at','verdict','findings'],s.checks.map(c=>'<tr><td>'+esc(c.what)+'</td><td><code>'+esc(c.url)+'</code></td><td class="'+(c.status===0?'pass':'fail')+'">'+esc(c.verdict)+'</td><td>'+esc(c.failed)+'</td></tr>'));
  }catch(e){}
  setTimeout(tick,1000);
}
tick();
</script>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dev", type=Path, required=True,
                        help="the directory holding ShowStopper, carlos, joe and leo")
    parser.add_argument("--work", type=Path,
                        help="this run's state, emptied first (default: a new temporary one)")
    parser.add_argument("--port", type=int, default=18700, help="the hub's port; members above it")
    args = parser.parse_args()
    dev, work = args.dev.resolve(), fresh(args.work)
    port, base = args.port, f"http://127.0.0.1:{args.port}"
    device = work / "beat-box.device"
    hosting.RETRY_CAP = 8.0  # a demo should not make anyone wait thirty seconds
    print(f"this run's state: {work}", flush=True)

    sys.path.insert(0, str(dev / "ShowStopper"))
    import showstopper_clock  # the clock's extension: needs ShowRunner, which is here

    metronome = hosting.plugin(lambda s: Metronome(Path(s["device"])), name="metronome",
                               family="show-control", description="A demo metronome")
    rack = hosting.plugin(lambda s: Rack(), name="rack", family="instruments",
                          description="An instrument offered to the wrong hub")
    the_hub = hub(work, port, [showstopper_clock.plugin, metronome, rack])
    supervisor = Supervisor(members(dev, work, port), logs=work / "logs",
                            log=lambda text: print(text, flush=True))
    checks: list[dict] = []
    state = {"show": None, "cue_list": None}

    panel = APIRouter(prefix="/demo")

    @panel.get("", response_class=HTMLResponse)
    def page():
        return PANEL

    @panel.get("/state")
    def demo_state():
        audit = httpx.get(f"{base}/family/", timeout=5).json()
        hosted = [
            {"name": "ShowStopper clock extension", "kind": "extension (in the hub)",
             "state": "loaded: a clock layer type, a Clock layer, ⏱ chips in /script",
             "css": "up"},
            {"name": "metronome", "kind": "member hosted in the hub",
             "state": "ready" if metronome.member else metronome.why,
             "css": "up" if metronome.member else "waiting"},
            {"name": "rack", "kind": "member offered to the hub", "state": rack.why,
             "css": "refused"},
        ]
        supervised = supervisor.status()
        current = {name: w["instance"] for name, w in supervised.items()}
        if metronome.member is not None:
            current["metronome"] = metronome.member.instance
        last = audit.get("last", [])
        fired = last[-1]["cue"]["number"] if last else None
        for outcome in last:  # an answer from an instance since replaced, said so
            took = outcome.get("instance")
            outcome["stale"] = bool(took and current.get(outcome["member"])
                                    and took != current[outcome["member"]])
        sheet = [{"number": str(n), "name": name, "layer": layer, "line": line,
                  "members": sorted(block), "fired": str(n) == fired}
                 for n, name, layer, line, block in CUES]
        links = [("the script, with the clock's chips", f"{base}/script"),
                 ("the programmer", f"{base}/programmer"),
                 ("the hub's audit", f"{base}/family/"),
                 ("the hub's identity", f"{base}/family/identity"),
                 ("ShowStopper", f"http://127.0.0.1:{port + 10}/"),
                 ("carlos", f"http://127.0.0.1:{port + 20}/rack"),
                 ("joe", f"http://127.0.0.1:{port + 30}/joe/"),
                 ("leo, following the hub", f"http://127.0.0.1:{port + 40}/")]
        return {"supervised": supervised, "hosted": hosted, "links": links, "sheet": sheet,
                "audit": list(reversed(last))[:24], "checks": checks}

    @panel.post("/go")
    def go():
        said = httpx.post(f"{base}/programmer/go",
                          params={"cue_list_id": state["cue_list"], "show_id": state["show"]},
                          timeout=10)
        return {"status": said.status_code, "answer": said.json()}

    @panel.post("/reset")
    def reset():
        return {"status": httpx.post(f"{base}/programmer/reset", timeout=10).status_code}

    @panel.post("/metronome/plug")
    def plug():
        device.write_text("plugged in", encoding="utf-8")
        return {"ok": True, "said": "the metronome's device is plugged in; the hub tries it "
                                    "again at its next retry"}

    @panel.post("/crash/{name}")
    def crash(name: str):
        watched = supervisor.watched.get(name)
        if watched is None or watched.process is None:
            return {"ok": False, "said": f"{name} is not supervised"}
        _kill_tree(watched.process)
        return {"ok": True, "said": f"{name} killed; the supervisor brings it back"}

    the_hub.api.include_router(panel)
    print(f"supervising {', '.join(supervisor.watched)}; starting the hub on {base}", flush=True)
    supervisor.start()
    the_hub.startup()
    server = uvicorn.Server(uvicorn.Config(the_hub.api, host="127.0.0.1", port=port,
                                           log_level="warning", lifespan="on"))
    serving = threading.Thread(target=server.run, daemon=True)
    serving.start()
    try:
        while not server.started:
            time.sleep(0.1)
        state["show"], state["cue_list"] = seed(base)
        print(f"the show is on the hub; waiting for the members ({base}/demo)", flush=True)
        if not supervisor.wait_up(240):
            print(f"not every member came up: {supervisor.status()}", flush=True)
        for name, url, action in [
                ("ShowStopper", f"http://127.0.0.1:{port + 10}", {"clock": "lap"}),
                ("carlos", f"http://127.0.0.1:{port + 20}", {"turn": "front"}),
                ("joe", f"http://127.0.0.1:{port + 31}", None)]:
            report = conformance.check(url, action)
            checks.append({"what": f"{name}, served alone", "url": url, "status": report.status,
                           "verdict": "conforms" if report.status == 0 else "does not conform",
                           "failed": "; ".join(f.what for f in report.findings if not f.ok)})
        report = conformance.check_hub(base, pull="leo")
        checks.append({"what": "the hub", "url": base, "status": report.status,
                       "verdict": "conforms" if report.status == 0 else "does not conform",
                       "failed": "; ".join(f.what for f in report.findings if not f.ok)})
        for check in checks:
            print(f"  kin check {check['what']}: {check['verdict']} {check['failed']}", flush=True)
        print(f"ready: open {base}/demo   (Ctrl+C stops everything)", flush=True)
        while serving.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        supervisor.stop()
        try:
            the_hub.shutdown()
        except Exception:  # noqa: BLE001, S110 -- stopping, whatever is left
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
