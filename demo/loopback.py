"""Loopback, the demo's show: ShowRunner by its own command, on the show's own show.toml.

ShowRunner is the one app that runs. The show is ``demo/show/``: a script, and
cues whose family blocks are what each GO fires. The demo's plugins, found
through ShowRunner's entry points as any installed plugin is, start the
members beside the hub and keep them running, make the show through the hub's
own routes, and host the members that live in the hub, the stagehand among
them, which does the show's acts backstage on its cues. This script writes the
show.toml for the checkouts under ``--dev`` and runs ShowRunner in the
foreground; it imports nothing of ShowRunner and changes nothing in it.
``docs/demo.md`` says what each cue does::

    uv run python demo/loopback.py --dev <dev>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

HEARTH = Path(__file__).resolve().parents[1]
PLUGINS = HEARTH / "demo" / "plugins"  # the show and its hosted members, an installable package
SHOW = HEARTH / "demo" / "show"  # the show's script and its cues
COPY = "src/showrunner/plugins/family/coordinator.py"  # the hub's copy of the template
MARK = ".hearth-loopback"  # a --work directory this demo made, and may empty again
# What the hub's process is started without: the shell's own environment, which
# would point uv at another project's.
CLEAN = {"VIRTUAL_ENV": None, "PYTHONPATH": None, "UV_PROJECT_ENVIRONMENT": None}


def ports(port: int) -> dict[str, int]:
    """Every port a run binds: the hub's, and the members' above it."""
    return {"hub": port, "showstopper": port + 10, "carlos": port + 20, "joe": port + 30,
            "joe api": port + 31, "joe qmcp": port + 32, "leo": port + 40}


def taken(candidates: list[int]) -> list[int]:
    """The ports something on this machine already listens on: an earlier run, most likely."""
    busy = []
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                busy.append(port)
    return busy


def fresh(work: Path | None) -> Path:
    """The run's state directory, empty: a new one, or one an earlier run made."""
    if work is None:
        work = Path(tempfile.mkdtemp(prefix="hearth-loopback-"))
    work = work.resolve()
    if work.exists() and any(work.iterdir()):
        if not (work / MARK).exists():
            raise SystemExit(f"{work} holds files this demo did not make; name an empty "
                             f"directory, or leave --work out")
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / MARK).write_text("made by hearth/demo/loopback.py; emptied at each run\n",
                             encoding="utf-8")
    return work


def members(dev: Path, work: Path, port: int) -> list[dict]:
    """The members beside the hub, as ``[[plugins.loopback.members]]`` names them."""
    at = ports(port)

    def run(member: str, *args: str) -> list[str]:
        checkout = {"showstopper": "ShowStopper"}.get(member, member)
        return ["uv", "run", "--no-sync", "--project", str(dev / checkout), member, "serve",
                "--host", "127.0.0.1", *args, "--state", str(work / member)]

    def url(name: str) -> str:
        return f"http://127.0.0.1:{at[name]}"

    # Each runs in its own checkout: carlos, for one, finds itself from where it starts.
    return [
        {"name": "showstopper", "command": run("showstopper", "--port", str(at["showstopper"])),
         "cwd": str(dev / "ShowStopper"), "url": url("showstopper"),
         "page": f"{url('showstopper')}/", "check": {"clock": "lap"}},
        {"name": "carlos", "command": run("carlos", "--port", str(at["carlos"])),
         "cwd": str(dev / "carlos"), "url": url("carlos"), "page": f"{url('carlos')}/rack",
         "check": {"turn": "front"}},
        # joe serves only its media API until told: the hub's cues, and what its page reads.
        {"name": "joe", "command": run("joe", "--port", str(at["joe"]),
                                       "--api-port", str(at["joe api"]),
                                       "--qmcp-url", url("joe qmcp"), "--allow", "family",
                                       "--allow", "library", "--allow", "transcripts"),
         "cwd": str(dev / "joe"), "url": url("joe api"), "page": f"{url('joe')}/joe/",
         "check": {}},
        {"name": "leo", "command": run("leo", "--port", str(at["leo"]),
                                       "--follow", f"http://127.0.0.1:{port}"),
         "cwd": str(dev / "leo"), "url": url("leo"), "page": f"{url('leo')}/", "ready": "/"},
    ]


def toml(value) -> str:
    """``value`` as a TOML value: a string, a number, a list, or an inline table."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    return "{" + ", ".join(f"{json.dumps(k)} = {toml(v)}" for k, v in value.items()) + "}"


def show_toml(dev: Path, work: Path, port: int) -> str:
    """The hub's show.toml: where it keeps its show, and how each of its plugins is set up."""
    at, state, device = ports(port), work / "hub", (work / "beat-box.device").as_posix()
    hub = f"http://127.0.0.1:{port}"
    text = (
        f'[server]\nhost = "127.0.0.1"\nport = {port}\n\n'
        f'[database]\npath = {toml((state / "show.db").as_posix())}\n\n'
        "# ShowStopper's clock runs beside the hub, so its hosted plugin stays off.\n"
        '[plugins]\ndisabled = ["showstopper"]\n\n'
        f'[plugins.showlogger]\nlevel = "INFO"\nfile = {toml((state / "show.log").as_posix())}\n\n'
        '[plugins.family]\npull = ["leo"]\ntimeout = 5.0\n\n'
        "[plugins.family.members]\n"
        f'showstopper = "http://127.0.0.1:{at["showstopper"]}"\n'
        f'carlos = "http://127.0.0.1:{at["carlos"]}"\n'
        f'joe = "http://127.0.0.1:{at["joe api"]}"\n\n'
        f"[plugins.metronome]\ndevice = {toml(device)}\n\n"
        "# The show's hands backstage: a member the hub hosts, and what it may plug in.\n"
        f"[plugins.stagehand.devices]\nmetronome = {toml(device)}\n\n"
        "# The show: its script and cues, and the members it keeps running beside the hub.\n"
        f"[plugins.loopback]\nhub = {toml(hub)}\n"
        f"script = {toml((SHOW / 'loopback.fountain').as_posix())}\n"
        f"cues = {toml((SHOW / 'cues.toml').as_posix())}\n"
        f"copy = {toml((dev / 'ShowRunner' / COPY).as_posix())}\n"
        f"logs = {toml((work / 'logs').as_posix())}\n"
    )
    for member in members(dev, work, port):
        text += "\n[[plugins.loopback.members]]\n" + "".join(
            f"{key} = {toml(value)}\n" for key, value in member.items())
    return text


def hub(dev: Path, work: Path, port: int) -> list[str]:
    """ShowRunner's own command, with hearth, the demo's plugins and ShowStopper installed
    beside it for this run alone; its checkout and its lock are left as they are."""
    state = work / "hub"
    state.mkdir(parents=True, exist_ok=True)
    config = state / "show.toml"
    config.write_text(show_toml(dev, work, port), encoding="utf-8")
    # ShowRunner's CLI by its module, run by this run's interpreter: the `sr` script
    # belongs to ShowRunner's own environment, which does not see what is installed beside it.
    # The demo's package is installed afresh, so its entry points are the ones it declares now.
    return ["uv", "run", "--no-sync", "--project", str(dev / "ShowRunner"),
            "--reinstall-package", "hearth-demo-plugins",
            "--with-editable", str(HEARTH), "--with-editable", str(PLUGINS),
            "--with-editable", str(dev / "ShowStopper"),
            "python", "-m", "showrunner.cli", "start", "--config", str(config),
            "--host", "127.0.0.1", "--port", str(port)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dev", type=Path, required=True,
                        help="the directory holding ShowRunner, ShowStopper, carlos, joe and leo")
    parser.add_argument("--work", type=Path,
                        help="this run's state, emptied first (default: a new temporary one)")
    parser.add_argument("--port", type=int, default=18700,
                        help="the hub's port; the members' are above it")
    args = parser.parse_args()
    # Before anything is emptied: a run still serving holds the state an empty start removes.
    busy = taken(list(ports(args.port).values()))
    if busy:
        raise SystemExit(f"ports {', '.join(map(str, busy))} are in use, by an earlier run "
                         f"most likely: stop it, or give another --port")
    dev, work = args.dev.resolve(), fresh(args.work)
    command = hub(dev, work, args.port)
    pages = ", ".join(f"{m['name']} {m['page']}" for m in members(dev, work, args.port))
    print(f"this run's state: {work}\nthe show: http://127.0.0.1:{args.port}/script, "
          f"GO at http://127.0.0.1:{args.port}/programmer   (Ctrl+C stops the show)\n"
          f"the members' pages: {pages}", flush=True)
    env = {key: value for key, value in {**os.environ, **CLEAN}.items() if value is not None}
    show = subprocess.Popen(command, cwd=work / "hub", env=env)
    while True:
        try:
            return show.wait()
        except KeyboardInterrupt:  # the console's Ctrl+C reaches ShowRunner too; let it stop
            continue


if __name__ == "__main__":
    sys.exit(main())
