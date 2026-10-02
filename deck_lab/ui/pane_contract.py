"""Desktop pane lane contract constants (t_e9b37fbc).

This module is deliberately tiny: it carries the single locked constant the
contract test asserts on, plus the registration shape the real
desktop/plugin.js mirrors. No parsing, scanning, network, or rendering code
lives here -- that is explicitly out of scope for this lane.
"""

from __future__ import annotations

# Exactly two equal plugin columns inside the plugin's own ~40vw right pane:
# the decklist (left) and the reserved card preview (right). This is NOT the
# five-region whole-window geometry (Hermes rail / chat / decklist / preview)
# -- it is the plugin's own internal column count.
PANE_COLUMN_COUNT = 2

# Mirrors the registration literally used in desktop/plugin.js's register().
PANE_AREA = "panes"
PANE_PLACEMENT = "right"
PANE_DOCK = {"pane": "workspace", "pos": "right"}
PANE_WIDTH = "40vw"
