"""Deterministic Python -> JS literal generator for the Deck Lab fixture.

Renders `deck_lab.ui.fixture.FIXTURE` as a JS `const FIXTURE = {...}` literal
and splices it into `desktop/plugin.js` between the
`// --- FIXTURE_GENERATED_START ---` / `// --- FIXTURE_GENERATED_END ---`
markers. This is the committed source of truth for how the Python dict
becomes the JS literal the pane renders; `tests/test_ui_fixture_js_parity.py`
fails whenever the two drift.

Usage: python scripts/gen_deck_lab_fixture_js.py [--check]
  --check: don't write; exit nonzero if the on-disk plugin.js literal differs
           from what regeneration would produce.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JS = ROOT / "desktop" / "plugin.js"

START_MARKER = "// --- FIXTURE_GENERATED_START ---"
END_MARKER = "// --- FIXTURE_GENERATED_END ---"


def _js_str(s: str) -> str:
    return json.dumps(s)


def to_js(obj, indent: int = 0) -> str:
    pad = "  " * indent
    pad2 = "  " * (indent + 1)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = []
        for k, v in obj.items():
            key = k if k.isidentifier() else _js_str(k)
            items.append(f"{pad2}{key}: {to_js(v, indent + 1)}")
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        items = [f"{pad2}{to_js(v, indent + 1)}" for v in obj]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    if isinstance(obj, str):
        return _js_str(obj)
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if obj is None:
        return "null"
    return str(obj)


def render_fixture_literal() -> str:
    sys.path.insert(0, str(ROOT))
    from deck_lab.ui.fixture import FIXTURE  # noqa: E402

    return f"const FIXTURE = {to_js(FIXTURE)}"


def splice(js_source: str, literal: str) -> str:
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL
    )
    if not pattern.search(js_source):
        raise RuntimeError(
            f"markers {START_MARKER!r}/{END_MARKER!r} not found in {PLUGIN_JS}"
        )
    replacement = f"{START_MARKER}\n{literal}\n{END_MARKER}"
    return pattern.sub(lambda _m: replacement, js_source)


def main() -> int:
    check = "--check" in sys.argv
    literal = render_fixture_literal()
    current = PLUGIN_JS.read_text()
    updated = splice(current, literal)
    if check:
        if updated != current:
            print("desktop/plugin.js fixture literal is stale; run without --check")
            return 1
        print("desktop/plugin.js fixture literal matches deck_lab.ui.fixture.FIXTURE")
        return 0
    PLUGIN_JS.write_text(updated)
    print(f"wrote {PLUGIN_JS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
