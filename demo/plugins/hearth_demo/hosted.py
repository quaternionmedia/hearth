"""The demo's members as ShowRunner plugins; imported only by a hub loading its plugins.

ShowRunner's loader calls ``ep.load()`` and registers what it finds under the
entry point's name, so each name here is the plugin itself. Each member's
settings are its own table in the hub's show.toml, ``[plugins.metronome]``.
"""

from __future__ import annotations

from pathlib import Path

from hearth import showrunner as hosting

from . import show
from .backstage import Waiting
from .members import Metronome, Rack, Stagehand

# A demo retries a missing device every few seconds at most, not every thirty.
RETRY_CAP = 8.0

metronome = hosting.plugin(lambda settings: Metronome(Path(settings["device"])),
                           name="metronome", family="show-control",
                           description="A demo metronome", retry_cap=RETRY_CAP)

rack = hosting.plugin(lambda settings: Rack(), name="rack", family="instruments",
                      description="An instrument offered to the wrong hub")

stagehand = hosting.plugin(
    lambda settings: Stagehand({name: Path(path) for name, path
                                in (settings.get("devices") or {}).items()},
                               Waiting(lambda: show.running), say=show.say),
    name="stagehand", family="show-control", description="The show's hands backstage")
