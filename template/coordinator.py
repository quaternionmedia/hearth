"""A family's coordinator: whatever fires, delivered to the members its family block names.

**Origin.** hearth's coordinator template, ``template/coordinator.py``, for
the family contract ``family/1``. In hearth this file is the template; anywhere
else it is a copy, and the app it was copied into owns it. It imports nothing
of hearth, so neither does a copy: an exemplar forks the template, changes
what it needs to, and keeps the contract, which ``hearth check --hub URL``
judges from outside. A change to the template reaches a copy only when the
copy's owner carries it in, diffing first, since the owner may have changed
what it owns. A copy records where it came from on the line below.

Copied from: this is the template.

A **coordinator** holds a family's members and, whenever something fires,
hands each member the part of the family block that names it. It is the other
side of the contract every member keeps (``docs/contract.md``), and it reaches
a member one of three ways:

* **push**: ``POST <base>/family/cue`` with
  ``{"cue": {"number", "name", "fired_at"}, "action": {...}}``;
* **local**: the member is hosted in the coordinator's own process and handed
  the same body by a call (a ``Receive``), answered as its route would answer;
* **pull**: the action is stored, and ``GET /family/members/<name>`` returns it
  as ``{"cue": {...}, "action": {...}}`` until the next block that names the
  member (``{"cue": null, "action": null}`` before the first);
  ``GET /family/members/<name>/events`` streams the same object as server-sent
  ``action`` events, at once and then as each block lands. The first read
  after a fire, by a request or by the stream, is the delivery.

``GET /family/`` lists every member and each recent delivery's outcome: how it
went, the HTTP status (``null`` when nothing answered), the milliseconds from
the fire to the member's answer or first read, and the member instance that
took it. A member that is down, slow or refuses is recorded, never raised, and
the others are delivered to. The coordinator asks each push member what it is
(``GET /family/identity``) before its first delivery and again after one that
failed, since the member may have restarted, and credits each outcome to the
instance the member's own answer names.

**What fires, and where the coordinator runs, are its exemplar's.** Nothing
here knows a cue list, a beat or a scene. An exemplar decides when something
fires, finds its family block, names it with a ``cue`` (the contract's word for
whatever fired), and serves ``router`` in its own app with ``identity`` saying
what it is. ShowRunner is the first exemplar, and the template was cut from
its family plugin: there a cue fires, the cue's ``actions`` carry the block,
and the coordinator is a pluggy plugin.

Delivery runs on worker threads, never on the event loop: one queue per push or
local member, so its blocks arrive in the order they fired. Each push member has
one HTTP client, made with the coordinator and kept for its life, and all of
them share one TLS context: making a client costs that setup, which on Windows
is most of a quarter second even for a plain-HTTP member, and a fire never pays
it. Every request has a timeout.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from copy import deepcopy
from functools import cache
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

CONTRACT = "family/1"  # the contract this coordinator keeps, both sides of it

DEFAULT_TIMEOUT = 5.0  # seconds per delivery
KEPT = 200  # outcomes listed at GET /family/, oldest dropped first
TABLE = "[family]"  # where an exemplar's settings name the members, as its messages say

# A pull member may read its action from a page in another origin (leo reads
# from the browser), so the routes it reads are readable cross-origin.
OPEN = {"Access-Control-Allow-Origin": "*"}
HEARTBEAT = 15.0  # seconds between keep-alive comments on a quiet stream
LOOK = 1.0  # seconds between looks for a stream's reader having gone

# A local member's receive: the body a push member is POSTed, and its
# (status, answer), as the member's own route would answer it.
Receive = Callable[[dict], "tuple[int, dict]"]

# This running process. A coordinator remade when its settings change is the
# same instance: the members it delivers to see one hub, not a new one.
INSTANCE = uuid4().hex[:12]


def identity(hub: str, family: str, version: str = "0") -> dict:
    """What a coordinator is, as ``GET /family/identity`` answers: its exemplar, the
    family it coordinates, the contract it keeps, and which running instance it is."""
    return {"hub": hub, "family": family, "contract": CONTRACT, "version": version,
            "instance": INSTANCE, "pid": os.getpid()}


@cache
def _tls() -> ssl.SSLContext:
    """The one TLS context every member's client shares: making it is the slow part."""
    return httpx.create_ssl_context()


class Coordinator:
    """A family's members, what waits for each pull member, and every delivery's outcome.

    ``members`` maps a push member's name to its base URL; ``local`` maps a
    member hosted in this process to its ``Receive``; ``pull`` names the members
    that read their action. A URL wins over a local member of the same name,
    and either wins over a pull. ``table`` is where the exemplar's settings name
    them, so a message says where to look; ``log`` is the exemplar's logger for
    warnings, the standard library's ``hearth`` logger when not given.
    """

    def __init__(
        self,
        members: dict[str, str] | None = None,
        pull: Iterable[str] = (),
        timeout: float = DEFAULT_TIMEOUT,
        local: dict[str, Receive] | None = None,
        *,
        table: str = TABLE,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.members = {name: str(url).rstrip("/") for name, url in (members or {}).items()}
        self.local = {name: receive for name, receive in (local or {}).items()
                      if name not in self.members}
        self.pull = [name for name in pull if name not in self.members and name not in self.local]
        self.timeout = float(timeout)
        self.table = table
        self._say = log or logging.getLogger("hearth").warning
        self._lock = threading.Lock()
        self._waiting: dict[str, dict] = {name: {"cue": None, "action": None} for name in self.pull}
        self._readers: dict[str, list[Callable[[], None]]] = {name: [] for name in self.pull}
        self._unread: dict[str, tuple[dict, float]] = {}  # pull member -> (outcome, fired)
        self._last: deque[dict] = deque(maxlen=KEPT)
        self._lanes: dict[str, ThreadPoolExecutor] = {}
        # One client per push member, made here rather than at its first delivery:
        # making one costs its TLS setup, which would otherwise be paid on the fire.
        self._clients = {name: httpx.Client(timeout=self.timeout, verify=_tls())
                         for name in self.members}
        # What each push member last said it is; None until it has said, and
        # again after a delivery that failed, since it may have restarted.
        self._identity: dict[str, dict | None] = {name: None for name in self.members}
        self._futures: list[Future] = []

    # --- something fires ----------------------------------------------------

    def fire(self, cue: dict, family: Any) -> list[str]:
        """Queue one delivery per member the block names; return their names.

        Returns at once: a push is sent, and a call made, from its member's worker thread.
        """
        if not isinstance(family, dict):
            self._say(f"cue {cue} has a family block that is not an object; nothing sent")
            return []
        fired = time.monotonic()
        told: list[Callable[[], None]] = []
        for name, action in family.items():
            outcome = {"cue": cue, "member": name, "via": None, "status": None, "ms": None,
                       "done": False, "error": None, "instance": None}
            with self._lock:
                self._last.append(outcome)
                if name in self.members:
                    outcome["via"] = "push"
                    future = self._lane(name).submit(
                        self._push, outcome, self._clients[name], self.members[name],
                        {"cue": cue, "action": action}, fired)
                    self._futures = [f for f in self._futures if not f.done()] + [future]
                elif name in self.local:
                    outcome["via"] = "local"
                    future = self._lane(name).submit(
                        self._call, outcome, self.local[name], {"cue": cue, "action": action},
                        fired)
                    self._futures = [f for f in self._futures if not f.done()] + [future]
                elif name in self._waiting:
                    outcome["via"] = "pull"
                    superseded = self._unread.get(name)
                    if superseded is not None:
                        superseded[0].update(
                            done=True,
                            error=f"cue {cue.get('number')} fired before {name} read this one")
                    self._waiting[name] = {"cue": cue, "action": action}
                    self._unread[name] = (outcome, fired)
                    told.extend(self._readers[name])
                else:
                    outcome.update(done=True, error=f"{name} is not a member in {self.table}")
                    self._say(f"cue {cue} names {name}, which {self.table} does not")
        for tell in told:  # outside the lock: a stream reads its action back through it
            tell()
        return list(family)

    def _lane(self, name: str) -> ThreadPoolExecutor:
        """The member's one worker thread: the only thread that uses its client or calls it."""
        if name not in self._lanes:
            self._lanes[name] = ThreadPoolExecutor(max_workers=1,
                                                   thread_name_prefix=f"family-{name}")
        return self._lanes[name]

    def _ask_identity(self, name: str, client: httpx.Client, base: str) -> dict | None:
        """The member's identity, asked only while unknown; None if it would not say."""
        known = self._identity.get(name)
        if known is not None:
            return known
        try:
            said = client.get(f"{base}/family/identity").json()
        except Exception:  # noqa: BLE001 -- an old member, or a down one: the push says which
            return None
        if isinstance(said, dict) and said.get("member"):
            with self._lock:
                self._identity[name] = said
            return said
        return None

    def _push(self, outcome: dict, client: httpx.Client, base: str, body: dict,
              fired: float) -> None:
        status, answer, error = None, None, None
        identity = self._ask_identity(outcome["member"], client, base)
        try:
            response = client.post(f"{base}/family/cue", json=body)
            status = response.status_code
            try:
                answer = response.json()
            except ValueError:
                answer = None
            if not response.is_success:
                said = answer.get("error") if isinstance(answer, dict) else None
                error = str(said) if said else response.text[:200]
        except httpx.TimeoutException as exc:
            error = f"no answer within {self.timeout:g}s ({type(exc).__name__})"
        except Exception as exc:  # noqa: BLE001 -- down, refused, malformed: recorded, never raised
            error = f"{type(exc).__name__}: {exc}"
        # The instance that took the cue, from its own answer when it says; a
        # member that restarted between two fires is never credited to the last one.
        said = answer.get("instance") if isinstance(answer, dict) else None
        took = said or (identity or {}).get("instance")
        with self._lock:
            outcome.update(status=status, answer=answer, error=error, done=True,
                           ms=round((time.monotonic() - fired) * 1000), instance=took)
            if error or (said and identity and said != identity.get("instance")):
                self._identity[outcome["member"]] = None  # ask again: it has restarted
        if error:
            self._say(f"family: {outcome['member']} answered {status} for cue "
                      f"{body['cue'].get('number')}: {error}")

    def _call(self, outcome: dict, receive: Receive, body: dict, fired: float) -> None:
        """A local member's delivery: its receive, called, and answered as its route would be."""
        status, answer, error = None, None, None
        try:
            status, answer = receive(deepcopy(body))
            if not 200 <= status < 300:
                said = answer.get("error") if isinstance(answer, dict) else None
                error = str(said) if said else f"answered {status}"
        except Exception as exc:  # noqa: BLE001 -- a member's fault is recorded, never the hub's
            error = f"{type(exc).__name__}: {exc}"
        took = answer.get("instance") if isinstance(answer, dict) else None
        with self._lock:
            outcome.update(status=status, answer=answer, error=error, done=True,
                           ms=round((time.monotonic() - fired) * 1000), instance=took)
        if error:
            self._say(f"family: {outcome['member']} (local) answered {status} for cue "
                      f"{body['cue'].get('number')}: {error}")

    # --- what the routes read -----------------------------------------------

    def read(self, name: str) -> dict | None:
        """A pull member's action, or None for a name that is not one; reading delivers it."""
        with self._lock:
            if name not in self._waiting:
                return None
            unread = self._unread.pop(name, None)
            if unread is not None:
                outcome, fired = unread
                outcome.update(status=200, done=True, ms=round((time.monotonic() - fired) * 1000))
            return deepcopy(self._waiting[name])

    def follow(self, name: str, tell: Callable[[], None]) -> Callable[[], None] | None:
        """Call ``tell`` whenever a block names pull member ``name``; None if it is not one.

        Returns what stops it. ``tell`` is called from whichever thread fired.
        """
        with self._lock:
            if name not in self._readers:
                return None
            self._readers[name].append(tell)

        def unfollow() -> None:
            with self._lock:
                if tell in self._readers.get(name, []):
                    self._readers[name].remove(tell)

        return unfollow

    def snapshot(self) -> dict:
        with self._lock:
            members = {name: {"via": "push", "url": url, "identity": deepcopy(self._identity[name])}
                       for name, url in self.members.items()}
            members.update({name: {"via": "local"} for name in self.local})
            members.update({name: {"via": "pull"} for name in self.pull})
            return {"members": members, "last": deepcopy(list(self._last))}

    def wait(self, timeout: float | None = None) -> bool:
        """Block until every queued push or call has an outcome; True when none is left."""
        with self._lock:
            futures = list(self._futures)
        _, pending = wait_for(futures, timeout=timeout)
        return not pending

    def close(self) -> None:
        for lane in self._lanes.values():
            lane.shutdown(wait=False, cancel_futures=True)
        self._lanes.clear()
        # A push already on the wire keeps its client until it ends; the
        # transport is released once nothing refers to it.
        self._clients.clear()


def from_table(settings: dict | None, local: dict[str, Receive] | None = None, *,
               table: str = TABLE, log: Callable[[str], None] | None = None) -> Coordinator:
    """A coordinator from an exemplar's settings table and the members hosted in its process.

    The table is ``{"members": {name: url}, "pull": [name], "timeout": seconds}``,
    each optional. A malformed entry is said and skipped, never fatal.
    """
    say = log or logging.getLogger("hearth").warning
    named = f"{table[:-1]}.members]" if table.startswith("[") and table.endswith("]") \
        else f"{table}.members"
    settings = settings or {}
    members = settings.get("members") or {}
    if not isinstance(members, dict):
        say(f"{named} must be a table of name = url; ignored")
        members = {}
    urls = {}
    for name, url in members.items():
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            urls[name] = url
        else:
            say(f"{named} {name} = {url!r} is not an http URL; ignored")
    pull = settings.get("pull") or []
    if not isinstance(pull, list) or not all(isinstance(name, str) for name in pull):
        say(f"{table} pull must be a list of names; ignored")
        pull = []
    for name in sorted(set(pull) & set(urls)):
        say(f"{name} is both pushed to and pulled; it is pushed to")
    for name in sorted(set(local or {}) & set(urls)):
        say(f"{name} is hosted here and named by URL; it is pushed to its URL")
    timeout = settings.get("timeout", DEFAULT_TIMEOUT)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        say(f"{table} timeout must be a positive number; {DEFAULT_TIMEOUT} used")
        timeout = DEFAULT_TIMEOUT
    return Coordinator(urls, pull, timeout, local, table=table, log=log)


# ---------------------------------------------------------------------------
# The coordinator's routes, for the exemplar's app
# ---------------------------------------------------------------------------


def router(coordinator: Callable[[], Coordinator | None], hub: Callable[[], dict], *,
           table: str = TABLE, tags: Iterable[str] = ("family",)) -> APIRouter:
    """``GET /family/``, ``/family/identity``, ``/family/members/<name>`` and its ``/events``.

    ``coordinator()`` is the exemplar's running coordinator, found per request so
    the exemplar may make it after the routes mount and remake it when its
    settings change; until there is one, the index is empty and no name is a pull
    member. ``hub()`` is what the exemplar says it is (``identity``).
    """
    routes = APIRouter(prefix="/family", tags=list(tags))

    def not_pulled(name: str) -> HTTPException:
        return HTTPException(status_code=404, headers=OPEN,
                             detail=f"{name} is not a pull member in {table}")

    @routes.get("/")
    async def index(response: Response):
        """The members, and the outcome of every recent delivery."""
        response.headers.update(OPEN)
        running = coordinator()
        if running is None:
            return {"members": {}, "last": []}
        return running.snapshot()

    @routes.get("/identity")
    async def hub_identity(response: Response):
        """What this coordinator is: its family, the contract it keeps, and this running instance."""
        response.headers.update(OPEN)
        return hub()

    @routes.get("/members/{name}")
    async def member(name: str, response: Response):
        """What a pull member is asked to do: the last block that named it, and its action."""
        response.headers.update(OPEN)
        running = coordinator()
        found = running.read(name) if running is not None else None
        if found is None:
            raise not_pulled(name)
        return found

    @routes.get("/members/{name}/events")
    async def member_events(name: str, request: Request):
        """The same as ``/members/<name>``, as a server-sent ``action`` event at once and at
        every block that names the member, so a page following it waits for no poll.
        Each event sent is a read, and the first one after a fire is its delivery."""
        running = coordinator()
        if running is None or name not in running.pull:
            raise not_pulled(name)
        loop = asyncio.get_running_loop()
        landed = asyncio.Event()

        def tell() -> None:  # any thread
            try:
                loop.call_soon_threadsafe(landed.set)
            except RuntimeError:  # the loop has closed
                pass

        unfollow = running.follow(name, tell)

        async def frames():
            try:
                yield _frame(running.read(name))
                quiet = 0.0
                while not await request.is_disconnected():
                    try:
                        await asyncio.wait_for(landed.wait(), LOOK)
                    except asyncio.TimeoutError:
                        quiet += LOOK
                        if quiet >= HEARTBEAT:
                            quiet = 0.0
                            yield ": still here\n\n"
                        continue
                    quiet = 0.0
                    landed.clear()
                    yield _frame(running.read(name))
            finally:
                if unfollow is not None:
                    unfollow()

        return StreamingResponse(frames(), media_type="text/event-stream",
                                 headers={**OPEN, "Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    return routes


def _frame(action: dict | None) -> str:
    return f"event: action\ndata: {json.dumps(action)}\n\n"
