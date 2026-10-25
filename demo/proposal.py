"""The proposal, running: ShowRunner as itself, its plugins installed beside it, members beside it.

Every part runs as it runs at a show: ShowRunner by its own command with an
ordinary show.toml, its extension and hosted members found through its entry
points, each member in its own process, all of them supervised, and the show
made through the hub's routes. This script imports nothing of ShowRunner and
changes nothing in it. It serves its own page on the port above the hub's.
``docs/demo.md`` says what runs and what to try::

    uv run python demo/proposal.py --dev <dev>
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from hearth import conformance, copies
from hearth.supervise import Spec, Supervisor, _kill_tree

HEARTH = Path(__file__).resolve().parents[1]
PLUGINS = HEARTH / "demo" / "plugins"  # the metronome and the rack, as an installable package
COPY = "src/showrunner/plugins/family/coordinator.py"  # the hub's copy of the template
MARK = ".hearth-proposal"  # a --work directory this demo made, and may empty again
# What a member's process is started without: the shell's own environment, which
# would point uv at another project's.
CLEAN = {"VIRTUAL_ENV": None, "PYTHONPATH": None, "UV_PROJECT_ENVIRONMENT": None}

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


def ports(port: int) -> dict[str, int]:
    """Every port a run binds: the hub's, the panel's above it, and the members' above that."""
    return {"hub": port, "panel": port + 1, "showstopper": port + 10, "carlos": port + 20,
            "joe": port + 30, "joe api": port + 31, "leo": port + 40}


def taken(candidates: list[int]) -> list[int]:
    """The ports something on this machine already listens on: an earlier run, most likely."""
    busy = []
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                busy.append(port)
    return busy


def fresh(work: Path | None) -> Path:
    """The run's state directory, empty: a new one, or one an earlier run made."""
    if work is None:
        work = Path(tempfile.mkdtemp(prefix="hearth-proposal-"))
    work = work.resolve()
    if work.exists() and any(work.iterdir()):
        if not (work / MARK).exists():
            raise SystemExit(f"{work} holds files this demo did not make; name an empty "
                             f"directory, or leave --work out")
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / MARK).write_text("made by hearth/demo/proposal.py; emptied at each run\n",
                             encoding="utf-8")
    return work


def show_toml(work: Path, port: int) -> str:
    """The hub's show.toml: where it keeps its show, and how each of its plugins is set up."""
    at = ports(port)
    state = work / "hub"
    return (
        f'[server]\nhost = "127.0.0.1"\nport = {port}\n\n'
        f'[database]\npath = {json.dumps((state / "show.db").as_posix())}\n\n'
        "# ShowStopper's clock runs beside the hub, so its hosted plugin stays off.\n"
        '[plugins]\ndisabled = ["showstopper"]\n\n'
        f'[plugins.showlogger]\nlevel = "INFO"\nfile = {json.dumps((state / "show.log").as_posix())}\n\n'
        '[plugins.family]\npull = ["leo"]\ntimeout = 5.0\n\n'
        "[plugins.family.members]\n"
        f'showstopper = "http://127.0.0.1:{at["showstopper"]}"\n'
        f'carlos = "http://127.0.0.1:{at["carlos"]}"\n'
        f'joe = "http://127.0.0.1:{at["joe api"]}"\n\n'
        f'[plugins.metronome]\ndevice = {json.dumps((work / "beat-box.device").as_posix())}\n'
    )


def hub(dev: Path, work: Path, port: int) -> Spec:
    """ShowRunner, run by its own command, with hearth, the demo's plugins and ShowStopper
    installed beside it for this run alone; its checkout and its lock are left as they are."""
    state = work / "hub"
    state.mkdir(parents=True, exist_ok=True)
    config = state / "show.toml"
    config.write_text(show_toml(work, port), encoding="utf-8")
    # ShowRunner's CLI by its module, run by this run's interpreter: the `sr` script
    # belongs to ShowRunner's own environment, which does not see what is installed beside it.
    command = ["uv", "run", "--no-sync", "--project", str(dev / "ShowRunner"),
               "--with-editable", str(HEARTH), "--with-editable", str(PLUGINS),
               "--with-editable", str(dev / "ShowStopper"),
               "python", "-m", "showrunner.cli", "start", "--config", str(config),
               "--host", "127.0.0.1", "--port", str(port)]
    return Spec("hub", command, f"http://127.0.0.1:{port}", cwd=str(state), env=CLEAN)


def members(dev: Path, work: Path, port: int) -> list[Spec]:
    at = ports(port)

    def run(member: str, *args: str) -> list[str]:
        checkout = {"showstopper": "ShowStopper"}.get(member, member)
        return ["uv", "run", "--no-sync", "--project", str(dev / checkout), member, "serve",
                "--host", "127.0.0.1", *args, "--state", str(work / member)]

    # Each runs in its own checkout: carlos, for one, finds itself from where it starts.
    return [
        Spec("showstopper", run("showstopper", "--port", str(at["showstopper"])),
             f"http://127.0.0.1:{at['showstopper']}", cwd=str(dev / "ShowStopper"), env=CLEAN),
        Spec("carlos", run("carlos", "--port", str(at["carlos"])),
             f"http://127.0.0.1:{at['carlos']}", cwd=str(dev / "carlos"), env=CLEAN),
        # joe serves only its media API until told: the hub's cues, and what its page reads.
        Spec("joe", run("joe", "--port", str(at["joe"]), "--api-port", str(at["joe api"]),
                        "--qmcp-url", f"http://127.0.0.1:{port + 32}",
                        "--allow", "family", "--allow", "library", "--allow", "transcripts"),
             f"http://127.0.0.1:{at['joe api']}", cwd=str(dev / "joe"), env=CLEAN),
        Spec("leo", run("leo", "--port", str(at["leo"]), "--follow", f"http://127.0.0.1:{port}"),
             f"http://127.0.0.1:{at['leo']}", cwd=str(dev / "leo"), env=CLEAN, ready="/"),
    ]


def seed(base: str) -> tuple[int, int]:
    """The show, made through the hub's own routes: (show id, cue list id)."""
    with httpx.Client(base_url=base, timeout=10) as hub_api:
        def made(method: str, path: str, **kwargs) -> dict:
            answer = hub_api.request(method, path, **kwargs)
            answer.raise_for_status()
            return answer.json()

        show = made("POST", "/db/shows", params={"name": "Proposal night"})["id"]
        made("POST", f"/db/shows/{show}/scripts",
             json={"title": "Proposal night", "format": "fountain", "content": SCRIPT})
        cue_list = made("POST", f"/db/shows/{show}/cue-lists", json={"name": "Main"})["id"]
        lines = SCRIPT.splitlines()
        for number, name, layer, line, family in CUES:
            made("POST", f"/db/cue-lists/{cue_list}/cues",
                 json={"number": number, "name": name, "layer": layer, "notes": NOTES[number],
                       "actions": {"family": family},
                       "script_line": next(i for i, text in enumerate(lines, 1)
                                           if text.startswith(line)),
                       "script_char": 0})
        return show, cue_list


def hosted_state(base: str, name: str) -> dict:
    """What a member hosted in the hub says it is, at the hub's own address for it."""
    try:
        said = httpx.get(f"{base}/{name}/family/identity", timeout=3)
    except httpx.HTTPError as exc:
        return {"ready": False, "said": f"the hub did not answer: {type(exc).__name__}"}
    body = said.json() if said.headers.get("content-type", "").startswith("application/json") \
        else {}
    if said.status_code == 200:
        return {"ready": True, "said": "ready", "instance": body.get("instance")}
    return {"ready": False, "said": body.get("error") or f"answered {said.status_code}"}


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
<p>ShowRunner as itself, its plugins installed beside it; members beside it, kept running; one contract either way. This page is the demo's own, beside the hub, and asks <code>/state</code> once a second.</p></div>
<div><h2>What to try</h2><ol>
<li><b>Fire the five cues.</b> Each one's family block goes to every member it names: pushed to ShowStopper, carlos and joe in milliseconds, read by leo from the hub's stream, handed in-process to the metronome. leo is a page, and the page is what follows: open <i>leo, following the hub</i> under Look and its deliveries are read in a few milliseconds; with no page open they wait unread. The metronome answers 503 <i>not ready</i>, its device missing; the rack 503 <i>not hosted</i>, being another family's. Neither stops the hub or the cue.</li>
<li><b>Plug in the metronome's device.</b> Within eight seconds the hub's retry finds it ready. Go back to cue 1 and fire cue 2: it answers 200.</li>
<li><b>Crash carlos.</b> The supervisor brings it back as a new instance in a few seconds. Fire a cue naming carlos (1, 3 or 4): the audit credits the new instance, and marks the answers of the one before it.</li>
<li><b>Crash the hub.</b> It is a process like the members, and comes back with its show; the members keep running, and leo follows it again.</li>
<li><b>Open the script.</b> The &#x23F1; chip under each Clock cue drives the clock through the hub, by ShowStopper's extension; the clock itself is the member beside the hub.</li>
</ol></div>
<div><h2>Act</h2><div class=row>
<button onclick="post('go')">Fire the next cue</button>
<button onclick="post('reset')">Back to cue 1</button>
<button onclick="post('metronome/plug')">Plug in the metronome's device</button>
<button onclick="post('crash/carlos')">Crash carlos</button>
<button onclick="post('crash/showstopper')">Crash ShowStopper</button>
<button onclick="post('crash/hub')">Crash the hub</button>
</div><p id=said></p></div>
<div><h2>Look</h2><div class=row id=links></div></div>
<div><h2>The cues</h2><div class=wrap><table id=sheet></table></div></div>
<div><h2>Each its own process (supervised)</h2><div class=wrap><table id=sup></table></div></div>
<div><h2>In the hub, as ShowRunner loaded it</h2><div class=wrap><table id=hosted></table></div></div>
<div><h2>Deliveries, newest first (the hub's audit)</h2><div class=wrap><table id=audit></table></div></div>
<div><h2>The contract, checked</h2><div class=wrap><table id=checks></table></div></div>
</main>
<script>
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function post(path){const r=await fetch(path,{method:'POST'});document.getElementById('said').textContent=JSON.stringify(await r.json());}
function rows(id, head, body){document.getElementById(id).innerHTML='<tr>'+head.map(h=>'<th>'+h+'</th>').join('')+'</tr>'+body.join('');}
async function tick(){
  try{
    const s=await (await fetch('state',{cache:'no-store'})).json();
    document.getElementById('links').innerHTML=s.links.map(([t,u])=>'<a href="'+esc(u)+'" target=_blank>'+esc(t)+'</a>').join(' · ');
    rows('sheet',['cue','name','layer','on the line','names'],s.sheet.map(c=>
      '<tr class="'+(c.fired?'now':'')+'"><td>'+esc(c.number)+(c.fired?' &#x25C0; last fired':'')+'</td><td>'+esc(c.name)+'</td><td>'+esc(c.layer)+'</td><td>'+esc(c.line)+'</td><td>'+esc(c.members.join(', '))+'</td></tr>'));
    rows('sup',['process','state','instance','pid','restarts','exits'],Object.entries(s.supervised).map(([n,w])=>
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


def panel_app(base: str, port: int, supervisor: Supervisor, device: Path, state: dict,
              checks: list[dict]) -> FastAPI:
    """The demo's own page and its actions: it reads over HTTP and acts through the hub's
    routes and the supervisor, as an operator's console beside the hub would."""
    at = ports(port)
    panel = FastAPI(title="The proposal, running")

    @panel.get("/", response_class=HTMLResponse)
    def page():
        return PANEL

    @panel.get("/state")
    def demo_state():
        try:
            audit = httpx.get(f"{base}/family/", timeout=3).json()
        except httpx.HTTPError:
            audit = {"last": []}
        try:
            layers = httpx.get(f"{base}/db/shows/{state['show']}/layers", timeout=3).json() \
                if state["show"] else []
        except httpx.HTTPError:
            layers = []
        clock = any(isinstance(layer, dict) and layer.get("type") == "clock" for layer in layers)
        metronome, rack = hosted_state(base, "metronome"), hosted_state(base, "rack")
        hosted = [
            {"name": "ShowStopper clock extension", "kind": "extension (in the hub)",
             "state": ("loaded: a clock layer type, a Clock layer, ⏱ chips in /script" if clock
                       else "no clock layer in the show"),
             "css": "up" if clock else "waiting"},
            {"name": "metronome", "kind": "member hosted in the hub", "state": metronome["said"],
             "css": "up" if metronome["ready"] else "waiting"},
            {"name": "rack", "kind": "member offered to the hub", "state": rack["said"],
             "css": "refused"},
        ]
        supervised = supervisor.status()
        current = {name: w["instance"] for name, w in supervised.items()}
        if metronome.get("instance"):
            current["metronome"] = metronome["instance"]
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
                 ("ShowStopper", f"http://127.0.0.1:{at['showstopper']}/"),
                 ("carlos", f"http://127.0.0.1:{at['carlos']}/rack"),
                 ("joe", f"http://127.0.0.1:{at['joe']}/joe/"),
                 ("leo, following the hub", f"http://127.0.0.1:{at['leo']}/")]
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

    return panel


def copy_row(dev: Path) -> dict:
    """The panel's row for the hub's coordinator: whether ShowRunner's copy is still the template."""
    copy = copies.check(dev / "ShowRunner" / COPY)
    return {"what": "the hub's coordinator", "url": COPY, "status": copy.status,
            "verdict": copy.said if copy.status == 0 else "is not the template",
            "failed": "" if copy.status == 0 else copy.said}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dev", type=Path, required=True,
                        help="the directory holding ShowRunner, ShowStopper, carlos, joe and leo")
    parser.add_argument("--work", type=Path,
                        help="this run's state, emptied first (default: a new temporary one)")
    parser.add_argument("--port", type=int, default=18700,
                        help="the hub's port; the panel one above it, members above that")
    args = parser.parse_args()
    at = ports(args.port)
    # Before anything is emptied: a run still serving holds the state an empty start removes.
    busy = taken(list(at.values()))
    if busy:
        raise SystemExit(f"ports {', '.join(map(str, busy))} are in use, by an earlier run "
                         f"most likely: stop it, or give another --port")
    dev, work = args.dev.resolve(), fresh(args.work)
    port, base = args.port, f"http://127.0.0.1:{args.port}"
    print(f"this run's state: {work}", flush=True)

    supervisor = Supervisor([hub(dev, work, port), *members(dev, work, port)],
                            logs=work / "logs", log=lambda text: print(text, flush=True))
    checks: list[dict] = []
    state: dict = {"show": None, "cue_list": None}
    panel = panel_app(base, port, supervisor, work / "beat-box.device", state, checks)
    server = uvicorn.Server(uvicorn.Config(panel, host="127.0.0.1", port=at["panel"],
                                           log_level="warning"))
    serving = threading.Thread(target=server.run, daemon=True)
    print(f"supervising {', '.join(supervisor.watched)}; the hub on {base}", flush=True)
    supervisor.start()
    try:
        # The hub's first run builds the environment its plugins are installed in.
        if not supervisor.wait_up(600):
            print(f"not everything came up: {supervisor.status()}", flush=True)
        state["show"], state["cue_list"] = seed(base)
        serving.start()
        for name, url, action in [
                ("ShowStopper", f"http://127.0.0.1:{at['showstopper']}", {"clock": "lap"}),
                ("carlos", f"http://127.0.0.1:{at['carlos']}", {"turn": "front"}),
                ("joe", f"http://127.0.0.1:{at['joe api']}", None)]:
            report = conformance.check(url, action)
            checks.append({"what": f"{name}, served alone", "url": url, "status": report.status,
                           "verdict": "conforms" if report.status == 0 else "does not conform",
                           "failed": "; ".join(f.what for f in report.findings if not f.ok)})
        report = conformance.check_hub(base, pull="leo")
        checks.append({"what": "the hub", "url": base, "status": report.status,
                       "verdict": "conforms" if report.status == 0 else "does not conform",
                       "failed": "; ".join(f.what for f in report.findings if not f.ok)})
        checks.append(copy_row(dev))
        for check in checks:
            print(f"  hearth check {check['what']}: {check['verdict']} {check['failed']}",
                  flush=True)
        print(f"ready: open http://127.0.0.1:{at['panel']}/   (Ctrl+C stops everything)",
              flush=True)
        while serving.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        supervisor.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
