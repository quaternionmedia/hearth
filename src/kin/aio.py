"""The contract's routes on aiohttp, for a member whose page is served by aiohttp.

ShowStopper serves its page with textual-serve, which is aiohttp; these are the
same four routes ``kin.web.router`` serves on FastAPI, answering the same way,
from the same event stream.
"""

from __future__ import annotations

import asyncio

from .member import Member, Refused, body_of
from .web import HEARTBEAT, OPEN, frames


def routes(member: Member, heartbeat: float = HEARTBEAT) -> list:
    """``POST /family/cue``, ``GET /family/state``, ``/family/events`` and ``/family/identity``."""
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
            return request.transport is None or request.transport.is_closing()

        response = web.StreamResponse(headers={**OPEN, "Content-Type": "text/event-stream",
                                               "Cache-Control": "no-cache"})
        await response.prepare(request)
        try:
            async for item in frames(member, gone, heartbeat):
                await response.write(item.encode())
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        return response

    return [web.post("/family/cue", cue), web.get("/family/state", state),
            web.get("/family/identity", identity), web.get("/family/events", events)]
