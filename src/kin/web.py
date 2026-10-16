"""The contract's routes on FastAPI, and a member served alone.

``router(member)`` is the four ``/family/*`` routes; it mounts on any FastAPI
app, which is how one member is served alone (``app``) or inside a hub
(``kin.showrunner``) with no change to the member. ``member`` may be a callable
returning the member, for a host that makes it after the routes are mounted;
until it does, the routes answer 503.

``GET /family/events`` is a server-sent event stream: the snapshot at once,
then one ``state`` event per change, so a follower needs no polling and no
second request to begin. A follower that falls behind is sent the newest
snapshot, never a backlog: a state, not a log.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .member import Member, Refused, body_of

# Read-only routes a page in another origin reads (a follower, a stage).
OPEN = {"Access-Control-Allow-Origin": "*"}
HEARTBEAT = 15.0  # seconds between keep-alive comments on a quiet stream
LOOK = 1.0  # seconds between looks for a follower that has gone
BEHIND = 8  # snapshots queued for a slow follower before older ones are dropped


def frame(snapshot: dict, event: str = "state") -> str:
    return f"event: {event}\ndata: {json.dumps(snapshot)}\n\n"


def following(member: Member) -> tuple[asyncio.Queue, Callable[[], None]]:
    """A queue on this event loop that the member's changes land in, from any thread,
    and what stops them landing."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=BEHIND)

    def put(snapshot: dict) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(snapshot)

    def follower(snapshot: dict) -> None:
        try:
            loop.call_soon_threadsafe(put, snapshot)
        except RuntimeError:  # the loop has closed
            pass

    return queue, member.follow(follower)


async def frames(member: Member, gone: Callable[[], Awaitable[bool]],
                 heartbeat: float = HEARTBEAT) -> AsyncIterator[str]:
    """The snapshot now, then the newest at every change, a comment when quiet, until ``gone()``.

    A follower that has gone is noticed within ``LOOK`` seconds rather than at
    the next write, so a host shutting down is not held open by a quiet stream.
    """
    queue, unfollow = following(member)
    try:
        yield frame(member.snapshot())
        quiet = 0.0
        while not await gone():
            try:
                snapshot = await asyncio.wait_for(queue.get(), LOOK)
            except asyncio.TimeoutError:
                quiet += LOOK
                if quiet >= heartbeat:
                    quiet = 0.0
                    yield ": still here\n\n"
                continue
            quiet = 0.0
            while not queue.empty():
                snapshot = queue.get_nowait()
            yield frame(snapshot)
    finally:
        unfollow()


def router(member: Member | Callable[[], Member | None]) -> APIRouter:
    """``POST /family/cue``, ``GET /family/state``, ``/family/events`` and ``/family/identity``."""
    the = (lambda: member) if isinstance(member, Member) else member
    routes = APIRouter(prefix="/family", tags=["family"])

    def started() -> Member:
        found = the()
        if found is None:
            raise _NotStarted
        return found

    @routes.post("/cue")
    async def cue(request: Request):
        """Take one cue's action from the hub. The body is read here rather than declared,
        so a body that is not JSON is answered in the contract's words, not FastAPI's."""
        try:
            body = body_of(await request.body())
            this = started()
        except Refused as refusal:
            return JSONResponse({"ok": False, "error": str(refusal)}, status_code=422)
        except _NotStarted:
            return _not_started()
        # Off the event loop: understanding an action may read a file.
        status, answer = await run_in_threadpool(this.receive, body)
        return JSONResponse(answer, status_code=status)

    @routes.get("/state")
    async def state():
        try:
            return JSONResponse(started().snapshot(), headers=OPEN)
        except _NotStarted:
            return _not_started()

    @routes.get("/identity")
    async def identity():
        try:
            return JSONResponse(started().identity(), headers=OPEN)
        except _NotStarted:
            return _not_started()

    @routes.get("/events")
    async def events(request: Request):
        try:
            this = started()
        except _NotStarted:
            return _not_started()
        return StreamingResponse(frames(this, request.is_disconnected),
                                 media_type="text/event-stream",
                                 headers={**OPEN, "Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    return routes


class _NotStarted(Exception):
    pass


def _not_started() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "the member has not started"}, status_code=503,
                        headers=OPEN)


def app(member: Member, *, routers: Iterable[APIRouter] = (), title: str | None = None) -> FastAPI:
    """One member served alone: its contract routes, its own routers, and its lifecycle.

    ``member.start()`` runs before the first request and ``member.stop()`` after
    the last, on the ASGI lifespan, so any ASGI server runs it the same way.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await run_in_threadpool(member.start)
        try:
            yield
        finally:
            await run_in_threadpool(member.stop)

    served = FastAPI(title=title or member.name, lifespan=lifespan)
    served.include_router(router(member))
    for extra in routers:
        served.include_router(extra)
    return served
