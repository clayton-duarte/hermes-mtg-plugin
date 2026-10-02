"""Guards that desktop/plugin.js's inline FIXTURE literal never silently
drifts from deck_lab.ui.fixture.FIXTURE (t_d80e077c architect review).

Regenerate with: python scripts/gen_deck_lab_fixture_js.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_plugin_js_fixture_literal_matches_python_source():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_deck_lab_fixture_js.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "desktop/plugin.js FIXTURE literal is out of sync with "
        "deck_lab.ui.fixture.FIXTURE; run "
        "`python scripts/gen_deck_lab_fixture_js.py` to regenerate.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
