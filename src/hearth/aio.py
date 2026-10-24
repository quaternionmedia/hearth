"""The contract's routes on aiohttp, for a member whose page is served by aiohttp.

ShowStopper serves its page with textual-serve, which is aiohttp; these are the
same four routes ``hearth.web.router`` serves on FastAPI, answering the same way,
from the same event stream.

``attach(app, member)`` is the whole of it: the routes, the member's
``start``/``stop`` on the application's own startup and cleanup, and every open
stream closed when the application shuts down -- without that, aiohttp waits
for each follower's stream to end before it will stop.
"""

from __future__ import annotations

import asyncio

from .member import Member, Refused, body_of
from .web import HEARTBEAT, OPEN, frames


def attach(app, member: Member, heartbeat: float = HEARTBEAT) -> None:
    """Serve ``member``'s contract on aiohttp application ``app``, for the application's life."""
    closing = asyncio.Event()

    async def started(_) -> None:
        await asyncio.get_running_loop().run_in_executor(None, member.start)

    async def shutting(_) -> None:
        closing.set()

    async def stopped(_) -> None:
        await asyncio.get_running_loop().run_in_executor(None, member.stop)

    app.add_routes(routes(member, heartbeat, closing))
    app.on_startup.append(started)
    app.on_shutdown.append(shutting)
    app.on_cleanup.append(stopped)


def routes(member: Member, heartbeat: float = HEARTBEAT,
           closing: asyncio.Event | None = None) -> list:
    """``POST /family/cue``, ``GET /family/state``, ``/family/events`` and ``/family/identity``.

    ``closing``, once set, ends every open stream; ``attach`` sets it at shutdown.
    """
    from aiohttp import web

    async def cue(request: web.Request) -> web.Response:
        try:
            body = body_of(await request.read())
        except Refused as refusal:
            return web.json_response({"ok": False, "error": str(refusal)}, status=422)
        status, answer = await asyncio.get_running_loop().run_in_executor(
            None, member.receive, body)
        return web.json_response(answer, status=status)

    async def state(request: web.Request) -> web.Response:
        return web.json_response(member.snapshot(), headers=OPEN)

    async def identity(request: web.Request) -> web.Response:
        return web.json_response(member.identity(), headers=OPEN)

    async def events(request: web.Request) -> web.StreamResponse:
        async def gone() -> bool:
            transport = request.transport
            return (transport is None or transport.is_closing()
                    or (closing is not None and closing.is_set()))

        response = web.StreamResponse(headers={**OPEN, "Content-Type": "text/event-stream",
                                               "Cache-Control": "no-cache"})
        await response.prepare(request)
        try:
            async for item in frames(member, gone, heartbeat):
                await response.write(item.encode())
        except ConnectionResetError:  # the follower went between two looks
            pass
        return response

    return [web.post("/family/cue", cue), web.get("/family/state", state),
            web.get("/family/identity", identity), web.get("/family/events", events)]
