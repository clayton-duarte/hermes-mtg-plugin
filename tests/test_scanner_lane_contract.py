"""RED contract test for the repository scanner lane (t_eb91eeab).

Fails at import time: `deck_lab.scanner` does not exist yet. That is the
intended RED signal for this contract card.
"""

from pathlib import Path

from deck_lab.scanner import scan_repository  # noqa: F401

NELLY_WORKSPACE = Path(__file__).parent / "fixtures" / "nelly-borca"


def test_scan_repository_discovers_nelly_deck_as_valid():
    decks = scan_repository(NELLY_WORKSPACE / "decks")
    assert any(d.path == "decks/commander/nelly-borca" and d.valid for d in decks)
