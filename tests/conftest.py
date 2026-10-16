"""A clock member, and a real server to serve one on: the contract is judged over sockets."""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
import uvicorn

from kin import Member, Refused, shown

ACTIONS = ("start", "stop", "reset", "lap")


class Clock(Member):
    """The smallest member worth serving: ShowStopper's clock, without the time."""

    name = "clock"
    family = "show-control"
    version = "test"
    verbs = ("clock",)

    def __init__(self) -> None:
        super().__init__()
        self.running = False
        self.laps = 0
        self.started = self.stopped = 0

    def understand(self, action):
        verb = action["clock"]
        if verb not in ACTIONS:
            raise Refused(f"the clock can {', '.join(ACTIONS)}; it cannot {shown(verb)}")
        return getattr(self, f"_{verb}")

    def _start(self):
        self.running = True

    def _stop(self):
        self.running = False

    def _reset(self):
        self.running, self.laps = False, 0

    def _lap(self):
        self.laps += 1

    def state(self):
        return {"running": self.running, "laps": self.laps}

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


@pytest.fixture()
def clock() -> Clock:
    return Clock()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Served:
    """An ASGI app on a real port, in a thread, until the test ends."""

    def __init__(self, asgi) -> None:
        port = free_port()
        self.url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(asgi, host="127.0.0.1", port=port,
                                                    log_level="warning", lifespan="on"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("the server did not start")
            time.sleep(0.02)

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(10)


@pytest.fixture()
def serve():
    started: list[Served] = []

    def start(asgi) -> Served:
        served = Served(asgi)
        started.append(served)
        return served

    yield start
    for served in started:
        served.close()


class AioServed:
    """An aiohttp application on a real port, in a thread of its own."""

    def __init__(self, application) -> None:
        from aiohttp import web

        port = free_port()
        self.url = f"http://127.0.0.1:{port}"
        self.loop = asyncio.new_event_loop()
        ready = threading.Event()

        async def run() -> None:
            self.runner = web.AppRunner(application)
            await self.runner.setup()
            await web.TCPSite(self.runner, "127.0.0.1", port).start()
            ready.set()

        def main() -> None:
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(run())
            self.loop.run_forever()

        self.thread = threading.Thread(target=main, daemon=True)
        self.thread.start()
        if not ready.wait(10):
            raise RuntimeError("aiohttp did not start")

    def close(self) -> None:
        asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)


@pytest.fixture()
def aio_serve():
    started: list[AioServed] = []

    def start(application) -> AioServed:
        served = AioServed(application)
        started.append(served)
        return served

    yield start
    for served in started:
        served.close()
