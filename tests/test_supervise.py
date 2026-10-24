"""The supervisor brings a member back when it stops, and a restart is a new instance."""

from __future__ import annotations

import sys
import textwrap
import time

import httpx

from hearth import testing
from hearth.supervise import Spec, Supervisor, companion_backoff

MEMBER = textwrap.dedent('''
    import os, sys
    import uvicorn
    import hearth
    from hearth import web

    class Fragile(hearth.Member):
        name, family, verbs = "fragile", "show-control", ("clock",)
        def understand(self, action):
            return lambda: os._exit(9)  # a crash on any cue
        def state(self):
            return {}

    uvicorn.run(web.app(Fragile()), host="127.0.0.1", port=int(sys.argv[1]), log_level="error")
''')


def test_companion_s_backoff():
    assert [companion_backoff(n) for n in range(1, 10)] == [1, 1, 1, 2, 4, 8, 16, 32, 60]


def test_a_member_that_crashes_is_brought_back_as_a_new_instance(tmp_path):
    script = tmp_path / "fragile.py"
    script.write_text(MEMBER, encoding="utf-8")
    port = testing.free_port()
    url = f"http://127.0.0.1:{port}"
    said: list[str] = []
    supervisor = Supervisor([Spec("fragile", [sys.executable, str(script), str(port)], url)],
                            logs=tmp_path / "logs", log=said.append, backoff=lambda n: 0.2)
    supervisor.start()
    try:
        assert supervisor.wait_up(60), said
        first = supervisor.status()["fragile"]["instance"]
        try:
            httpx.post(f"{url}/family/cue", json={"cue": {"number": "1"},
                                                  "action": {"clock": "lap"}}, timeout=5)
        except httpx.HTTPError:
            pass  # it died answering
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            now = supervisor.status()["fragile"]
            if now["state"] == "up" and now["instance"] not in (None, first):
                break
            time.sleep(0.1)
        now = supervisor.status()["fragile"]
        assert now["state"] == "up" and now["instance"] != first, (now, said)
        assert now["exits"] == [9] and now["restarts"] == 1
        assert any("stopped (exit 9)" in line for line in said)
    finally:
        supervisor.stop()
    assert supervisor.status()["fragile"]["state"] == "stopped"
