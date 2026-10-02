"""Normal-suite wrapper around the live CDP interaction proof (t_1e429f1c).

scripts/check_deck_lab_interactions.mjs drives the real running Hermes
desktop Deck Lab plugin over Chrome DevTools Protocol -- it is not a unit
test and requires a live app with its debug port open. This wrapper lets the
normal pytest suite pick it up (and fail CI if it silently bit-rots) while
still being skippable in environments with no live app to drive.

Enable with the explicit live switch:

    DECK_LAB_LIVE_CDP=1 pytest tests/test_ui_interactions.py -v

With the switch set, this test shells out to the live script, requires
rc == 0, parses its JSON results, and asserts every named check passed.
Without the switch (the default -- e.g. plain `pytest tests/`), it skips
with an explicit reason instead of silently no-opping.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_deck_lab_interactions.mjs"

LIVE_CDP_ENV = "DECK_LAB_LIVE_CDP"


@pytest.mark.skipif(
    os.environ.get(LIVE_CDP_ENV) != "1",
    reason=(
        f"Live CDP interaction proof skipped: set {LIVE_CDP_ENV}=1 with the "
        "Hermes desktop Deck Lab plugin running (debug port 127.0.0.1:9333) "
        "to execute it."
    ),
)
def test_live_interaction_script_all_checks_pass():
    assert SCRIPT.is_file(), f"missing live interaction script: {SCRIPT}"

    proc = subprocess.run(
        ["node", str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert proc.returncode == 0, (
        f"check_deck_lab_interactions.mjs exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        raise AssertionError(
            f"could not parse JSON from check_deck_lab_interactions.mjs stdout: {exc}\n"
            f"stdout:\n{proc.stdout}"
        ) from exc

    results = payload.get("results", {})
    assert results, f"no named results in payload: {payload}"

    failed = {name: r for name, r in results.items() if not r.get("pass")}
    assert not failed, (
        f"{len(failed)} live interaction check(s) failed: "
        f"{json.dumps(failed, indent=2)}"
    )
    assert payload.get("failures") == 0, payload
