"""The demo's hosted members, as hearth members: what an action changes, and what each is."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import hearth


class Metronome(hearth.Member):
    """A member hosted in the hub, whose MIDI clock device may not be there yet.

    The device is a file the stagehand writes on a cue, standing in for the
    clock a performer plugs in: until it is there, ``start`` raises, and the
    hub's retry keeps trying.
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


class Backstage(Protocol):
    """What the stagehand reaches: the members the show keeps running, and the checks."""

    def running(self) -> list[str]: ...

    def knock_over(self, name: str) -> None: ...

    def check(self) -> list[dict]: ...


class Stagehand(hearth.Member):
    """The show's hands backstage, hosted in the hub, so that a cue does each of its acts.

    ``plug`` writes a device's file, as a performer plugs a device in; ``crash``
    stops a member the show keeps running, which its supervisor brings back;
    ``check`` holds the family to the contract with hearth's checks. Each act is
    kept in the stagehand's state and said through ``say``.
    """

    name, family, verbs = "stagehand", "show-control", ("plug", "crash", "check")

    def __init__(self, devices: dict[str, Path], backstage: Backstage,
                 say: Callable[[str], None] = print) -> None:
        super().__init__()
        self.devices, self.backstage, self.say = devices, backstage, say
        self.plugged: list[str] = []
        self.crashed: list[str] = []
        self.checked: list[dict] = []

    def understand(self, action):
        if len(action) != 1:
            raise hearth.Refused(f"the stagehand does one thing a cue, not {len(action)}")
        verb, what = next(iter(action.items()))
        if verb == "plug":
            device = self.devices.get(what)
            if device is None:
                raise hearth.Refused(f"there is no device of {hearth.shown(what)} to plug in")

            def plug():
                device.write_text("plugged in", encoding="utf-8")
                self.plugged.append(what)
                self.say(f"stagehand: {what}'s device is plugged in")

            return plug
        if verb == "crash":
            if what not in self.backstage.running():
                raise hearth.Refused(f"{hearth.shown(what)} is not a member the show keeps "
                                     "running")

            def crash():
                self.backstage.knock_over(what)
                self.crashed.append(what)
                self.say(f"stagehand: {what} knocked over; its supervisor brings it back")

            return crash

        def check():
            self.checked = self.backstage.check()
            for row in self.checked:
                self.say(f"hearth check {row['what']}: {row['verdict']} {row['failed']}".rstrip())

        return check

    def state(self) -> dict:
        return {"plugged": self.plugged, "crashed": self.crashed, "checked": self.checked}
