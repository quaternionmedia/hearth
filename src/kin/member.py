"""A member of the performing family: what a hub's cue does to it, and what it says it is.

The hub fires a cue and hands each member its part of the cue's ``family``
block. Every member answers the same four routes, whatever serves them
(``docs/contract.md``)::

    POST /family/cue       {"cue": {"number", "name", "fired_at"}, "action": {...}}
                           200 {"ok": true, "state": {...}, "instance"}  done
                           202 {"ok": true, "state": {...}, "instance"}  taken; finishes later
                           422 {"ok": false, "error": "..."}  not understood
                           500 {"ok": false, "error": "..."}  failed acting on it
    GET  /family/state     {"member": name, "cue": {...} | null, "state": {...}}
    GET  /family/events    text/event-stream: the state now, then at every change
    GET  /family/identity  {"member", "family", "version", "contract", "verbs",
                            "instance", "pid"}

A subclass says what an action changes and what its state is. The envelope,
the refusal, the record of the last cue and telling every follower are here,
once. **A refused cue changes nothing**, its record included: ``understand``
returns the change without making it, and the change is made only once
nothing is left to refuse.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

CONTRACT = "family/1"

Change = Callable[[], None]
Follower = Callable[[dict], None]


class Refused(ValueError):
    """A body this member does not understand: answered 422 in the member's words."""


def shown(value: object) -> str:
    """A value as an error message quotes it: JSON where it can be, never past 80 characters."""
    try:
        text = repr(value) if isinstance(value, str) else json.dumps(value)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


class Member(ABC):
    """One member of a family, as every host serves it.

    ``name`` is the member's key in a cue's family block. ``verbs`` are the
    action keys it takes: an action naming any other is refused before
    ``understand`` sees it; left empty, ``understand`` judges every key.
    ``later`` says its work finishes after the answer, which is then 202.
    """

    name: ClassVar[str]
    family: ClassVar[str]
    version: ClassVar[str] = "0"
    verbs: ClassVar[tuple[str, ...]] = ()
    later: ClassVar[bool] = False

    def __init__(self, *, version: str | None = None, instance: str | None = None) -> None:
        """``version`` and ``instance`` name this running member when the process
        knows them better than the class does: a build's version, a server's own
        instance id that its health route also reports."""
        self.cue: dict | None = None
        if version is not None:
            self.version = version
        self.instance = instance or uuid.uuid4().hex[:12]
        self._lock = threading.RLock()
        self._followers: list[Follower] = []

    # --- what a member says ------------------------------------------------

    @abstractmethod
    def understand(self, action: dict) -> Change:
        """The change ``action`` makes, unmade; or ``Refused`` saying why not."""

    @abstractmethod
    def state(self) -> dict:
        """What this member is doing now, as a JSON object."""

    def start(self) -> None:
        """Called once by the host before the first request; a member opens what it holds here."""

    def stop(self) -> None:
        """Called once by the host after the last request."""

    # --- what every member does the same way -------------------------------

    def receive(self, body: object) -> tuple[int, dict]:
        """Act on one cue's body: the HTTP status and the answer. Never raises.

        The change runs under the member's lock with ``self.cue`` already the cue
        it acts on, so a change that needs its cue -- a recording named for it --
        reads it there. A change that raises leaves the record of the last cue as
        it was and is answered 500 in the contract's shape.
        """
        try:
            cue, action = self._envelope(body)
            change = self.understand(action)
        except Refused as refusal:
            return 422, {"ok": False, "error": str(refusal)}
        with self._lock:
            previous, self.cue = self.cue, cue
            try:
                change()
            except Exception as exc:  # noqa: BLE001 -- the member's fault, answered, never raised
                self.cue = previous
                return 500, {"ok": False,
                             "error": f"{self.name} failed acting on the cue: "
                                      f"{type(exc).__name__}: {exc}"}
            state = self.state()
        self.changed()
        # The instance that took the cue rides on the answer, so a hub attributes
        # the delivery to it even when the member restarted between two cues.
        return (202 if self.later else 200), {"ok": True, "state": state,
                                              "instance": self.instance}

    def _envelope(self, body: object) -> tuple[dict, dict]:
        if not isinstance(body, dict):
            raise Refused("the body must be a JSON object with a cue and an action")
        cue = body.get("cue")
        if not isinstance(cue, dict):
            raise Refused("cue must be an object: {number, name, fired_at}")
        action = body.get("action")
        if not isinstance(action, dict) or not action:
            raise Refused(f"{self.name} takes an action object{self._taking()}, "
                          f"not {shown(action)}")
        unknown = sorted(set(action) - set(self.verbs)) if self.verbs else []
        if unknown:
            raise Refused(f"{self.name} does not take {', '.join(map(repr, unknown))}"
                          f"{self._taking()}")
        return cue, action

    def _taking(self) -> str:
        return f" ({', '.join(self.verbs)})" if self.verbs else ""

    def snapshot(self) -> dict:
        with self._lock:
            return {"member": self.name, "cue": self.cue, "state": self.state()}

    def identity(self) -> dict:
        """What this member is, so a reader can tell it from anything else answering the port."""
        return {"member": self.name, "family": self.family, "version": self.version,
                "contract": CONTRACT, "verbs": list(self.verbs),
                "instance": self.instance, "pid": os.getpid()}

    # --- followers ---------------------------------------------------------

    def follow(self, follower: Follower) -> Callable[[], None]:
        """Call ``follower`` with the snapshot at every change; returns what stops it."""
        with self._lock:
            self._followers.append(follower)

        def unfollow() -> None:
            with self._lock:
                if follower in self._followers:
                    self._followers.remove(follower)

        return unfollow

    def changed(self) -> None:
        """Tell every follower the state now.

        A cue calls this itself. A member whose state moves on its own -- a
        take that finishes on a worker -- calls it when it does, from any thread.
        """
        snapshot = self.snapshot()
        with self._lock:
            followers = list(self._followers)
        for follower in followers:
            try:
                follower(snapshot)
            except Exception:  # noqa: BLE001, S110 -- a follower that has gone is not the member's fault
                pass


def body_of(raw: bytes) -> Any:
    """A request body as JSON, or ``Refused`` in the contract's words."""
    try:
        return json.loads(raw)
    except ValueError:  # not JSON, or not UTF-8
        raise Refused("the body is not JSON") from None
