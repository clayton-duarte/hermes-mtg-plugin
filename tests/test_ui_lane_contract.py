"""RED contract test for the Deck Lab desktop pane lane (t_e9b37fbc).

Fails at import time: `deck_lab.ui.pane_contract` does not exist yet. That is
the intended RED signal for this contract card.
"""

from deck_lab.ui.pane_contract import PANE_COLUMN_COUNT  # noqa: F401


def test_pane_has_exactly_two_equal_columns():
    assert PANE_COLUMN_COUNT == 2
