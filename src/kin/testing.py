"""What a member's tests need to hold it to the contract over a real socket.

Every helper is a context manager that yields an address and stops what it
started on the way out::

    with serving(kin.web.app(member)) as url:
        assert kin.conformance.check(url).status == 0

    with serving_aiohttp(application) as url: ...

    with showrunner_hub() as hub:   # pluggy, ShowRunner's hook names, no ShowRunner
        hub.register(kin.showrunner.plugin(...))

None of them is imported by a member's running code.
"""

from __future__ import annotations

import asyncio
import socket
import sys
import threading
import time
import types
from collections.abc import Iterator
from contextlib import contextmanager

STARTS_WITHIN = 10.0  # seconds


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextmanager
def serving(asgi) -> Iterator[str]:
    """An ASGI app served by uvicorn on a free port in a thread, lifespan included."""
    import uvicorn

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(asgi, host="127.0.0.1", port=port,
                                           log_level="warning", lifespan="on", ws="none"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + STARTS_WITHIN
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(STARTS_WITHIN)


@contextmanager
def serving_aiohttp(application) -> Iterator[str]:
    """An aiohttp application on a free port, on an event loop in a thread of its own."""
    from aiohttp import web

    port = free_port()
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    runner = web.AppRunner(application)

    async def start() -> None:
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", port).start()
        ready.set()

    def main() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start())
        loop.run_forever()

    thread = threading.Thread(target=main, daemon=True)
    thread.start()
    if not ready.wait(STARTS_WITHIN):
        raise RuntimeError("aiohttp did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        asyncio.run_coroutine_threadsafe(runner.cleanup(), loop).result(STARTS_WITHIN * 3)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(STARTS_WITHIN)


@contextmanager
def showrunner_hub():
    """A pluggy manager with ShowRunner's hook marker and the hooks kin answers, no ShowRunner.

    It stands a module called ``showrunner`` in ``sys.modules`` for the
    duration, so ``kin.showrunner.plugin`` builds against it.
    """
    import pluggy

    fake = types.ModuleType("showrunner")
    fake.hookimpl = pluggy.HookimplMarker("showrunner")
    spec = pluggy.HookspecMarker("showrunner")

    class Spec:
        @spec
        def showrunner_register(self): ...

        @spec
        def showrunner_startup(self, app): ...

        @spec
        def showrunner_shutdown(self, app): ...

        @spec
        def showrunner_get_routes(self): ...

        @spec
        def showrunner_family_members(self): ...

        @spec
        def showrunner_get_nav(self): ...

    hub = pluggy.PluginManager("showrunner")
    hub.add_hookspecs(Spec)
    previous = sys.modules.get("showrunner")
    sys.modules["showrunner"] = fake
    try:
        yield hub
    finally:
        if previous is None:
            sys.modules.pop("showrunner", None)
        else:
            sys.modules["showrunner"] = previous
