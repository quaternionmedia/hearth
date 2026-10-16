"""Does what answers at a URL keep the family contract? ``kin check URL``.

It asks the routes only, so it judges a member in any language and under any
host: alone on its own port, or inside a hub at ``<hub>/<name>``. Each finding
is one line, ``pass`` or ``fail``, naming what was asked and what came back.

With ``--action '{"clock": "lap"}'`` it also sends one real cue and times it:
from the POST to the member's answer, and from the POST to the event that
carries the cue to a follower. That second figure is what a person watching a
page waits for.

Exit 0: every finding passed. 1: one failed. 3: nothing answered, so the check
could not say.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from .member import CONTRACT

CANNOT_SAY = 3
NOT_UNDERSTOOD = {"kin-conformance-unknown-verb": True}


@dataclass
class Finding:
    ok: bool
    what: str
    saw: str = ""

    def __str__(self) -> str:
        return f"{'pass' if self.ok else 'fail'}  {self.what}" + (f" -- {self.saw}" if self.saw
                                                                    else "")


@dataclass
class Report:
    url: str
    findings: list[Finding] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    answered: bool = True

    def add(self, ok: bool, what: str, saw: object = "") -> bool:
        self.findings.append(Finding(bool(ok), what, saw if isinstance(saw, str) else
                                     json.dumps(saw)[:160]))
        return bool(ok)

    @property
    def status(self) -> int:
        if not self.answered:
            return CANNOT_SAY
        return 0 if all(f.ok for f in self.findings) else 1


def events(client: httpx.Client, url: str, timeout: float) -> Iterator[dict]:
    """Each ``state`` event's data from ``url``'s stream, as it arrives."""
    with client.stream("GET", url, timeout=httpx.Timeout(timeout, read=timeout)) as response:
        if response.status_code != 200 or "text/event-stream" not in \
                response.headers.get("content-type", ""):
            raise ValueError(f"{response.status_code} {response.headers.get('content-type')}")
        name, data = None, []
        for line in response.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
            elif line == "" and data:
                if name in (None, "state"):
                    yield json.loads("\n".join(data))
                name, data = None, []


def check(url: str, action: dict | None = None, timeout: float = 5.0) -> Report:
    base = url.rstrip("/")
    report = Report(base)
    with httpx.Client(timeout=timeout) as client:
        try:
            said = client.get(f"{base}/family/identity")
        except httpx.HTTPError as exc:
            report.answered = False
            report.add(False, "GET /family/identity answers", f"{type(exc).__name__}: {exc}")
            return report

        identity = _json(said)
        report.add(said.status_code == 200 and isinstance(identity, dict),
                   "GET /family/identity is 200 with an object", f"{said.status_code} {identity}")
        identity = identity if isinstance(identity, dict) else {}
        report.add(identity.get("contract") == CONTRACT,
                   f"it keeps contract {CONTRACT}", identity.get("contract"))
        for key in ("member", "family", "instance"):
            report.add(isinstance(identity.get(key), str) and identity[key],
                       f"identity names its {key}", identity.get(key))
        name = identity.get("member")

        said = client.get(f"{base}/family/state")
        before = _json(said)
        report.add(said.status_code == 200 and isinstance(before, dict)
                   and before.get("member") == name and "cue" in before
                   and isinstance(before.get("state"), dict),
                   "GET /family/state is {member, cue, state} for the same member",
                   f"{said.status_code} {before}")

        said = client.post(f"{base}/family/cue", content=b"{not json",
                           headers={"Content-Type": "application/json"})
        answer = _json(said)
        report.add(said.status_code == 422 and isinstance(answer, dict)
                   and answer.get("ok") is False and isinstance(answer.get("error"), str),
                   "a body that is not JSON is refused 422 with its error",
                   f"{said.status_code} {answer}")

        probe = {"cue": {"number": "kin", "name": "conformance", "fired_at": None},
                 "action": NOT_UNDERSTOOD}
        said = client.post(f"{base}/family/cue", json=probe)
        answer = _json(said)
        report.add(said.status_code == 422 and isinstance(answer, dict)
                   and answer.get("ok") is False and isinstance(answer.get("error"), str),
                   "an action it does not take is refused 422 with its error",
                   f"{said.status_code} {answer}")
        after = _json(client.get(f"{base}/family/state"))
        report.add(isinstance(after, dict) and isinstance(before, dict)
                   and after.get("cue") == before.get("cue"),
                   "a refused cue changes nothing, the record of the last cue included",
                   f"{(before or {}).get('cue')} then {(after or {}).get('cue')}")

        _check_events(client, base, report, name, action, timeout)
    return report


def _check_events(client: httpx.Client, base: str, report: Report, name: object,
                  action: dict | None, timeout: float) -> None:
    started = time.perf_counter()
    stream = events(client, f"{base}/family/events", timeout)
    try:
        first = next(stream)
    except (httpx.HTTPError, ValueError, StopIteration) as exc:
        report.add(False, "GET /family/events streams the state at once", repr(exc))
        return
    report.timings["first event ms"] = round((time.perf_counter() - started) * 1000, 1)
    report.add(isinstance(first, dict) and first.get("member") == name,
               "GET /family/events streams the state at once", first)
    if action is None:
        stream.close()
        return

    number = f"kin-{int(time.time() * 1000)}"
    sent: dict[str, object] = {}
    # Made before the clock starts: making a client loads its TLS setup, which
    # on Windows is a quarter of a second the member never spent.
    sender = httpx.Client(timeout=timeout)

    def fire() -> None:
        with sender:
            sent["at"] = time.perf_counter()
            sent["answer"] = sender.post(f"{base}/family/cue", json={
                "cue": {"number": number, "name": "conformance", "fired_at": None},
                "action": action})
            sent["answered"] = time.perf_counter()

    # Fired once the stream is open, so the event it causes cannot be missed.
    poster = threading.Thread(target=fire)
    poster.start()
    seen, broke = None, False
    try:
        for snapshot in stream:
            if (snapshot.get("cue") or {}).get("number") == number:
                seen = time.perf_counter()
                break
    except httpx.HTTPError as exc:
        broke = report.add(False, "the cue reaches a follower as an event", repr(exc)) or True
    finally:
        stream.close()
        poster.join(timeout)
    answer = sent.get("answer")
    ok = isinstance(answer, httpx.Response) and answer.status_code in (200, 202)
    report.add(ok, f"the action {json.dumps(action)} is taken",
               f"{answer.status_code} {_json(answer)}" if isinstance(answer, httpx.Response)
               else "no answer")
    if ok:
        report.timings["cue answered ms"] = round((sent["answered"] - sent["at"]) * 1000, 1)
    if seen is not None:
        report.timings["cue to event ms"] = round((seen - sent["at"]) * 1000, 1)
    if not broke:  # a stream that broke has said so already
        report.add(seen is not None, "the cue reaches a follower as an event",
                   "" if seen is not None else f"no event named cue {number} within {timeout:g}s")


def _json(response: object) -> object:
    try:
        return response.json()  # type: ignore[union-attr]
    except (ValueError, AttributeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kin", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    asked = sub.add_parser("check", help="check the member answering at URL against the contract")
    asked.add_argument("url")
    asked.add_argument("--action", type=json.loads, default=None,
                       help='one real action to send and time, as JSON: \'{"clock": "lap"}\'')
    asked.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    report = check(args.url, args.action, args.timeout)
    print(f"kin check {report.url}")
    for finding in report.findings:
        print(f"  {finding}")
    for what, ms in report.timings.items():
        print(f"  {what}: {ms}")
    print({0: "conforms", 1: "does not conform", CANNOT_SAY: "could not say: nothing answered"}
          [report.status])
    return report.status


if __name__ == "__main__":
    sys.exit(main())
