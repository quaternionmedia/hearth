"""Plugin or server: one member hosted both ways, timed, and broken on purpose.

The hub here is ShowRunner's own: the coordinator it runs, its copy of hearth's
template (``showrunner.plugins.family.coordinator``), the ShowFamily plugin that serves
it, and, for startup, its ``ShowRunner`` app.
So this runs in ShowRunner's environment with hearth importable::

    cd <a ShowRunner checkout carrying the family stack>
    PYTHONPATH=<hearth>/src uv run --no-sync python <hearth>/bench/hosting.py

Everything binds 127.0.0.1 on ports the OS picks, and every process it starts,
it stops. ``BENCH_N`` sets the cues per path (default 300).

What it prints is one run on one machine: read the relations between the rows
(which path is an order of magnitude slower, which failure the hub survives),
not the digits.
"""

from __future__ import annotations

import contextlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI
from showrunner.plugins import family
from showrunner.plugins.family import coordinator

import hearth
from hearth import showrunner as hosting
from hearth import testing, web

N = int(os.environ.get("BENCH_N", "300"))
LAP = {"clock": "lap"}


class Clock(hearth.Member):
    """A member that notes when each cue reached it, by the bench's own clock."""

    name, family, verbs = "clock", "show-control", ("clock",)

    def __init__(self) -> None:
        super().__init__()
        self.laps = 0
        self.at: dict[str, float] = {}
        self.arrived = threading.Event()

    def understand(self, action):
        return self._lap

    def _lap(self) -> None:
        self.laps += 1
        self.at[self.cue["number"]] = time.perf_counter()
        self.arrived.set()

    def state(self) -> dict:
        return {"laps": self.laps}


def cue(n: int) -> dict:
    return {"number": str(n), "name": "bench", "fired_at": None}


def summary(seconds: list[float]) -> str:
    ms = sorted(s * 1000 for s in seconds)
    p95 = ms[max(0, int(len(ms) * 0.95) - 1)]
    return f"median {statistics.median(ms):7.2f} ms   p95 {p95:7.2f} ms   max {ms[-1]:7.2f} ms"


def row(label: str, seconds: list[float]) -> None:
    print(f"  {label:<46} {summary(seconds)}", flush=True)


class Follower:
    """Reads a server-sent event stream on a thread; notes when each cue's event lands."""

    def __init__(self, url: str, event: str, number_of) -> None:
        self.at: dict[str, float] = {}
        self.arrived = threading.Event()
        self.ready = threading.Event()
        self._stop = False
        self.thread = threading.Thread(target=self._run, args=(url, event, number_of), daemon=True)
        self.thread.start()
        if not self.ready.wait(10):
            raise RuntimeError(f"no stream from {url}")

    def _run(self, url, event, number_of) -> None:
        with httpx.Client(timeout=None) as client, client.stream("GET", url) as stream:
            name, data = None, []
            for line in stream.iter_lines():
                if self._stop:
                    return
                if line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].strip())
                elif line == "" and data:
                    if name == event:
                        self.ready.set()
                        number = number_of(json.loads("\n".join(data)))
                        if number is not None:
                            self.at[number] = time.perf_counter()
                            self.arrived.set()
                    name, data = None, []

    def stop(self) -> None:
        self._stop = True


def timed(fire, arrived: threading.Event, at: dict, n: int) -> float:
    arrived.clear()
    t0 = time.perf_counter()
    fire(n)
    if not arrived.wait(10) or str(n) not in at:
        raise RuntimeError(f"cue {n} never arrived")
    return at[str(n)] - t0


# ---------------------------------------------------------------------------
# 1. How long a cue takes, by path
# ---------------------------------------------------------------------------


def latency() -> None:
    print(f"\n1. A cue, from the hub firing it to its arrival ({N} cues per path)\n")

    member = Clock()
    times = []
    for n in range(N):
        t0 = time.perf_counter()
        member.receive({"cue": cue(n), "action": LAP})
        times.append(member.at[str(n)] - t0)
    row("call, no hub (the floor)", times)

    member = Clock()
    hub = coordinator.Coordinator(local={"clock": member.receive})
    row("hub -> member hosted in the hub (local)",
        [timed(lambda n: hub.fire(cue(n), {"clock": LAP}), member.arrived, member.at, n)
         for n in range(N)])
    hub.close()

    member = Clock()
    with testing.serving(web.app(member)) as url:
        hub = coordinator.Coordinator(members={"clock": url})
        row("hub -> member served alone (HTTP push)",
            [timed(lambda n: hub.fire(cue(n), {"clock": LAP}), member.arrived, member.at, n)
             for n in range(N)])
        page = Follower(f"{url}/family/events", "state",
                        lambda s: (s.get("cue") or {}).get("number"))
        row("hub -> member alone -> a page following it",
            [timed(lambda n: hub.fire(cue(n), {"clock": LAP}), page.arrived, page.at, n)
             for n in range(N)])
        page.stop()
        hub.close()

    api = FastAPI()
    api.include_router(family.router)
    hub = family.configure({"pull": ["leo"]})
    with testing.serving(api) as url:
        page = Follower(f"{url}/family/members/leo/events", "action",
                        lambda a: (a.get("cue") or {}).get("number"))
        row("hub -> a page that follows the hub (pull)",
            [timed(lambda n: hub.fire(cue(n), {"leo": {"song": "x"}}), page.arrived, page.at, n)
             for n in range(N)])
        page.stop()
    hub.close()


# ---------------------------------------------------------------------------
# 2. What a misbehaving member costs the hub, by host
# ---------------------------------------------------------------------------


def fails_to_start() -> None:
    print("\n2a. A member whose start fails (its device is missing)\n")
    from showrunner.app import ShowRunner

    class Broken(Clock):
        def start(self) -> None:
            raise RuntimeError("no MIDI device called 'Launchkey'")

    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "show.toml"
        db = (Path(tmp) / "bench.db").as_posix()
        config.write_text(f'[database]\npath = "{db}"\n', encoding="utf-8")
        hub = ShowRunner(config_path=config)
        hub.pm.register(hosting.plugin(lambda settings: Broken(), name="broken",
                                       family="show-control"))
        try:
            hub.startup()
            hosted = "the hub started"
        except Exception as exc:  # the outcome is the measurement
            hosted = f"the hub's startup raised {type(exc).__name__}: {exc}"
        finally:
            with contextlib.suppress(Exception):
                hub.shutdown()
    print(f"  hosted in the hub: {hosted}")

    hub = coordinator.Coordinator(members={"broken": "http://127.0.0.1:9"}, timeout=2)
    hub.fire(cue(1), {"broken": LAP})
    hub.wait(10)
    said = hub.snapshot()["last"][0]
    print(f"  served alone, never came up: the hub runs; the delivery is audited "
          f"status={said['status']} error={said['error'][:60]!r}")
    hub.close()


def slow_member() -> None:
    print("\n2b. A member that takes 2 s to act on a cue, beside one that does not\n")

    class Slow(Clock):
        name = "slow"

        def understand(self, action):
            return lambda: time.sleep(2)

    slow, clock = Slow(), Clock()
    hub = coordinator.Coordinator(local={"slow": slow.receive, "clock": clock.receive})
    clock.arrived.clear()
    t0 = time.perf_counter()
    hub.fire(cue(1), {"slow": LAP, "clock": LAP})
    clock.arrived.wait(10)
    beside = (clock.at["1"] - t0) * 1000
    t1 = time.perf_counter()
    hub.fire(cue(2), {"slow": LAP})
    hub.wait(10)
    second = (time.perf_counter() - t1) * 1000
    hub.close()
    print(f"  hosted: the other member still had its cue in {beside:.1f} ms "
          "(each member has its own lane);")
    print(f"          a second cue to the slow member queued behind the first: both done in "
          f"{second:.0f} ms (its lane is in order)")


def blocking_page() -> None:
    print("\n2c. A member's page that blocks the event loop for 2 s (time.sleep in async)\n")
    page = APIRouter()

    @page.get("/clock/slow")
    async def slow_page():
        time.sleep(2)  # the mistake under test: blocking an async route
        return {"ok": True}

    def probe(hub_url: str, page_url: str) -> float:
        # Both clients made before any clock starts: making one costs its TLS setup.
        with httpx.Client(timeout=30) as asker, httpx.Client(timeout=30) as blocker_client:
            asker.get(f"{hub_url}/family/")  # warm
            blocker = threading.Thread(target=lambda: blocker_client.get(f"{page_url}/clock/slow"))
            blocker.start()
            time.sleep(0.2)
            t0 = time.perf_counter()
            asker.get(f"{hub_url}/family/")
            took = (time.perf_counter() - t0) * 1000
            blocker.join()
            return took

    family.configure({})
    together = FastAPI()
    together.include_router(family.router)
    together.include_router(page)
    with testing.serving(together) as url:
        hosted = probe(url, url)

    hub_app = FastAPI()
    hub_app.include_router(family.router)
    member_app = FastAPI()
    member_app.include_router(page)
    with testing.serving(hub_app) as hub_url, testing.serving(member_app) as member_url:
        alone = probe(hub_url, member_url)
    family.configure(None).close()
    print(f"  hosted (one event loop): the hub's own GET /family/ took {hosted:.0f} ms")
    print(f"  served alone (its own loop): the hub's GET /family/ took {alone:.0f} ms")


CRASHER = textwrap.dedent('''
    import os, sys
    import hearth
    from hearth import web
    import uvicorn

    class Crash(hearth.Member):
        name, family, verbs = "crash", "show-control", ("clock",)
        def understand(self, action):
            return lambda: os._exit(7)
        def state(self):
            return {}

    uvicorn.run(web.app(Crash()), host="127.0.0.1", port=int(sys.argv[1]), log_level="error")
''')

HOSTED_CRASH = textwrap.dedent('''
    import os, time
    import hearth
    from showrunner.plugins.family import coordinator

    class Crash(hearth.Member):
        name, family, verbs = "crash", "show-control", ("clock",)
        def understand(self, action):
            return lambda: os._exit(7)
        def state(self):
            return {}

    hub = coordinator.Coordinator(local={"crash": Crash().receive})
    hub.fire({"number": "1"}, {"crash": {"clock": "lap"}})
    time.sleep(2)
    print("the hub is still running")
''')


def crashing_member() -> None:
    print("\n2d. A member that kills its own process on a cue (a native crash, os._exit)\n")
    env = dict(os.environ)
    with tempfile.TemporaryDirectory() as tmp:
        hosted = Path(tmp) / "hosted_crash.py"
        hosted.write_text(HOSTED_CRASH, encoding="utf-8")
        run = subprocess.run([sys.executable, str(hosted)], capture_output=True, text=True,
                             env=env, timeout=60, check=False)  # its exit code is the result
        said = run.stdout.strip() or "(nothing: it never got that far)"
        print(f"  hosted: the hub's process exited with {run.returncode}; it printed {said!r}")

        server = Path(tmp) / "crash_server.py"
        server.write_text(CRASHER, encoding="utf-8")
        port = testing.free_port()
        member = subprocess.Popen([sys.executable, str(server), str(port)], env=env)
        try:
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    httpx.get(f"{url}/family/identity", timeout=1)
                    break
                except httpx.HTTPError:
                    time.sleep(0.1)
            hub = coordinator.Coordinator(members={"crash": url}, timeout=3)
            hub.fire(cue(1), {"crash": LAP})
            hub.wait(10)
            first = hub.snapshot()["last"][-1]
            hub.fire(cue(2), {"crash": LAP})
            hub.wait(10)
            second = hub.snapshot()["last"][-1]
            hub.close()
            member.wait(10)
            print(f"  served alone: the member exited with {member.returncode}; the hub runs on "
                  f"and audits cue 1 as {first['error'][:50]!r}, cue 2 as {second['error'][:50]!r}")
        finally:
            if member.poll() is None:
                member.kill()


if __name__ == "__main__":
    print(f"python {sys.version.split()[0]} on {sys.platform}; hearth {hearth.CONTRACT}")
    latency()
    fails_to_start()
    slow_member()
    blocking_page()
    crashing_member()
