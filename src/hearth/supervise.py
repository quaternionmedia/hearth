"""Members served alone, kept running: start each, know when it is up, start it again when it stops.

A prototype of the supervisor a show machine needs once members are servers of
their own (``plans/plugin-or-server.md`` in the corpus calls it H4). Each
member is a command and the URL it answers at; it is *up* once
``GET <url>/family/identity`` answers, and the instance it names is kept, so a
restart shows as a new one.

The restart policy is Bitfocus Companion's: 1 s after each of the first three
stops, then 2, 4, 8… s up to 60 s, never giving up -- a show that is running
wants its member back. A member that stayed up ``stable`` seconds before it
stopped counts from the start again.

::

    supervisor = Supervisor([Spec("carlos", ["uv", "run", "carlos", "serve", ...],
                                  "http://127.0.0.1:18720", cwd="../carlos")])
    supervisor.start()
    supervisor.wait_up(60)
    ...
    supervisor.stop()
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx


def companion_backoff(restarts: int) -> float:
    """Seconds before restart ``restarts`` (1-based): 1, 1, 1, then 2, 4, 8… up to 60."""
    return 1.0 if restarts <= 3 else min(2.0 ** (restarts - 3), 60.0)


@dataclass
class Spec:
    """A member to keep running: its command, where it answers, and how to tell it is up.

    ``ready`` is the path probed; a member keeping ``family/1`` is up when its
    ``/family/identity`` answers. A page with no routes of its own (leo follows
    the hub) is up when ``ready="/"`` answers, and has no instance to keep.
    """

    name: str
    command: list[str]
    url: str
    cwd: str | None = None
    env: dict[str, str | None] | None = None  # a None value unsets the variable
    ready: str = "/family/identity"


@dataclass
class Watched:
    spec: Spec
    state: str = "stopped"  # starting | up | restarting | stopped
    pid: int | None = None
    instance: str | None = None
    restarts: int = 0
    since: float = field(default_factory=time.monotonic)
    process: subprocess.Popen | None = None
    exits: list[int] = field(default_factory=list)


def kill_tree(process: subprocess.Popen) -> None:
    """Stop ``process`` and every process it started, as a crash would."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                       capture_output=True, check=False)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(10)


class Supervisor:
    """Keeps each member running; ``status()`` says what each is doing now."""

    def __init__(self, specs: list[Spec], *, logs: Path | None = None,
                 log: Callable[[str], None] = print, up_within: float = 120.0,
                 stable: float = 10.0,
                 backoff: Callable[[int], float] = companion_backoff) -> None:
        self.watched = {spec.name: Watched(spec) for spec in specs}
        self.logs, self.log = logs, log
        self.up_within, self.stable, self.backoff = up_within, stable, backoff
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self.logs is not None:
            self.logs.mkdir(parents=True, exist_ok=True)
        for watched in self.watched.values():
            thread = threading.Thread(target=self._keep, args=(watched,), daemon=True,
                                      name=f"supervise-{watched.spec.name}")
            thread.start()
            self._threads.append(thread)

    def wait_up(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all(w.state == "up" for w in self.watched.values()):
                return True
            time.sleep(0.1)
        return False

    def status(self) -> dict[str, dict]:
        now = time.monotonic()
        return {name: {"state": w.state, "pid": w.pid, "instance": w.instance,
                       "restarts": w.restarts, "for_s": round(now - w.since, 1),
                       "exits": list(w.exits)}
                for name, w in self.watched.items()}

    def stop(self) -> None:
        self._stop.set()
        for watched in self.watched.values():
            if watched.process is not None:
                kill_tree(watched.process)
        for thread in self._threads:
            thread.join(15)

    # --- one member ---------------------------------------------------------

    def _launch(self, watched: Watched) -> subprocess.Popen:
        spec = watched.spec
        flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} \
            if sys.platform == "win32" else {"start_new_session": True}
        env = {key: value for key, value in {**os.environ, **(spec.env or {})}.items()
               if value is not None}
        with contextlib.ExitStack() as held:
            # The child holds the log open for itself; this process's handle closes here.
            out = (held.enter_context(open(self.logs / f"{spec.name}.log", "ab"))
                   if self.logs is not None else subprocess.DEVNULL)
            return subprocess.Popen(spec.command, cwd=spec.cwd, env=env,
                                    stdout=out, stderr=subprocess.STDOUT, **flags)

    def _identity(self, client: httpx.Client, spec: Spec) -> dict | None:
        try:
            said = client.get(f"{spec.url.rstrip('/')}{spec.ready}")
        except httpx.HTTPError:
            return None
        if said.status_code != 200:
            return None
        try:
            answer = said.json()
        except ValueError:
            answer = None
        return answer if isinstance(answer, dict) else {}

    def _keep(self, watched: Watched) -> None:
        name = watched.spec.name
        with httpx.Client(timeout=2) as client:
            while not self._stop.is_set():
                watched.state, watched.since, watched.instance = "starting", time.monotonic(), None
                process = watched.process = self._launch(watched)
                watched.pid = process.pid
                deadline = time.monotonic() + self.up_within
                while not self._stop.is_set() and process.poll() is None:
                    said = self._identity(client, watched.spec)
                    if said is not None:
                        watched.state, watched.since = "up", time.monotonic()
                        watched.instance = said.get("instance")
                        self.log(f"supervise: {name} is up (instance {watched.instance}, "
                                 f"pid {process.pid})")
                        break
                    if time.monotonic() > deadline:
                        self.log(f"supervise: {name} did not answer within "
                                 f"{self.up_within:g}s; stopping it to start again")
                        kill_tree(process)
                        break
                    time.sleep(0.25)
                while not self._stop.is_set() and process.poll() is None:
                    time.sleep(0.25)
                if self._stop.is_set():
                    break
                ran = time.monotonic() - watched.since
                watched.exits.append(process.returncode)
                watched.restarts = 1 if ran >= self.stable and watched.state == "up" \
                    else watched.restarts + 1
                wait = self.backoff(watched.restarts)
                watched.state = "restarting"
                self.log(f"supervise: {name} stopped (exit {process.returncode}) after "
                         f"{ran:.1f}s; restart {watched.restarts} in {wait:g}s")
                if self._stop.wait(wait):
                    break
        watched.state = "stopped"
