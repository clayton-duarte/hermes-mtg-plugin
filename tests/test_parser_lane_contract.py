"""RED contract test for the parser/validator lane (t_09bc9ceb).

This currently fails at import time because `deck_lab.parser` does not exist.
That is the intended RED signal for this contract card. Once the parser lane
implements `deck_lab.parser.parse_board`, this test must fail on the
assertion (wrong parsed card count) until the lane's own implementation makes
it pass for real.
"""

from pathlib import Path

from deck_lab.parser import parse_board  # noqa: F401 -- lane module, not yet implemented

NELLY_BOARD = (
    Path(__file__).parent
    / "fixtures"
    / "nelly-borca"
    / "decks"
    / "commander"
    / "nelly-borca"
    / "mainboard.md"
)


def test_parse_board_derives_100_cards_from_nelly_golden_fixture():
    result = parse_board(NELLY_BOARD.read_text(), path=str(NELLY_BOARD))
    total = sum(entry.quantity for entry in result.cards)
    assert total == 100
