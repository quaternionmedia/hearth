"""A clock member, and kin.testing's servers as fixtures: the contract is judged over sockets."""

from __future__ import annotations

from contextlib import ExitStack

import pytest

from kin import Member, Refused, shown, testing

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


@pytest.fixture()
def serve():
    """``serve(asgi)`` -> its URL, for the rest of the test."""
    with ExitStack() as stack:
        yield lambda asgi: stack.enter_context(testing.serving(asgi))


@pytest.fixture()
def aio_serve():
    """``aio_serve(application)`` -> its URL, for the rest of the test."""
    with ExitStack() as stack:
        yield lambda application: stack.enter_context(testing.serving_aiohttp(application))


@pytest.fixture()
def showrunner_hub():
    with testing.showrunner_hub() as hub:
        yield hub
