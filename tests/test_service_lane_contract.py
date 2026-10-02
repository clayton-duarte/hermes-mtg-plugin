"""RED contract test for the shared Deck Lab domain service.

This currently fails at import time because `deck_lab.service` does not
exist yet. That is the intended RED signal for this contract card. Once a
minimal, importable `DeckLabService` skeleton exists, this test must fail on
the named assertion below (wrong deck path) until the service lane's real
`list_decks` orchestration makes it pass for real.
"""

from pathlib import Path

from deck_lab.service import DeckLabService  # noqa: F401 -- lane module

WORKSPACE_ROOT = Path(__file__).parent / "fixtures" / "nelly-borca"


def test_list_decks_discovers_nelly_as_first_entry():
    service = DeckLabService(WORKSPACE_ROOT)
    result = service.list_decks()
    assert result["decks"][0]["path"] == "decks/commander/nelly-borca"
