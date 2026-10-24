"""The demo's two hosted members, as hearth members: what an action changes, and what each is."""

from __future__ import annotations

from pathlib import Path

import hearth


class Metronome(hearth.Member):
    """A member hosted in the hub, whose MIDI clock device may not be there yet.

    The device is a file the demo's panel writes, standing in for the clock a
    performer plugs in: until it is there, ``start`` raises, and the hub's
    retry keeps trying.
    """

    name, family, verbs = "metronome", "show-control", ("beat",)

    def __init__(self, device: Path) -> None:
        super().__init__()
        self.device, self.bpm, self.beats = device, None, 0

    def start(self) -> None:
        if not self.device.exists():
            raise OSError(f"no MIDI clock device 'Beat Box' (it appears as {self.device.name})")

    def understand(self, action):
        bpm = action["beat"]
        if not isinstance(bpm, int) or not 20 <= bpm <= 300:
            raise hearth.Refused(f"a beat is 20 to 300 bpm, not {hearth.shown(bpm)}")

        def change():
            self.bpm, self.beats = bpm, self.beats + 1

        return change

    def state(self) -> dict:
        return {"bpm": self.bpm, "beats": self.beats}


class Rack(hearth.Member):
    """An instruments-family member, offered to a show-control hub: it must be refused."""

    name, family, verbs = "rack", "instruments", ("turn",)

    def understand(self, action):
        return lambda: None

    def state(self) -> dict:
        return {}
