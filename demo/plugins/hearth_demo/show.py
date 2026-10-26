"""Loopback, the demo's show, as a ShowRunner plugin: imported only by a hub loading its plugins.

At the hub's startup it starts the members ``[plugins.loopback]`` names and
keeps each running, and makes the show once the hub answers; at its shutdown it
stops them. What it does is ``backstage``'s.
"""

from __future__ import annotations

import showrunner

try:  # ShowRunner's own log, so what the show says is beside what the hub says
    from loguru import logger

    say = logger.info
except ImportError:  # outside ShowRunner, as in hearth's own tests
    say = print

from .backstage import Show

# The running show, which the stagehand reaches when it acts.
running: Show | None = None


class Loopback:
    """Loopback: its members kept running, and its script and cues made.

    ShowRunner registers it as ``loopback``, the name ``[plugins] disabled`` matches.
    """

    @showrunner.hookimpl
    def showrunner_register(self):
        return {"name": "loopback", "description": "Loopback, the demo's show in cues",
                "version": "0"}

    @showrunner.hookimpl
    def showrunner_startup(self, app):
        global running
        config = getattr(app, "config", None)
        settings = (config.plugins.settings.get("loopback", {}) if config is not None
                    else {}) or {}
        running = Show(settings, say=say)
        running.start()

    @showrunner.hookimpl
    def showrunner_shutdown(self, app):
        global running
        if running is not None:
            running.stop()
        running = None
