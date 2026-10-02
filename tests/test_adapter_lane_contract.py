"""RED contract test for the ManaBox/Arena interchange adapter lane (t_21314a59).

Fails at import time: `deck_lab.adapters.manabox_arena` does not exist yet.
That is the intended RED signal for this contract card.
"""

from pathlib import Path

from deck_lab.adapters.manabox_arena import import_text  # noqa: F401

SAMPLE = Path(__file__).parent / "fixtures" / "interchange" / "manabox_sample.txt"


def test_import_text_preserves_zone_quantity_and_name_round_trip():
    result = import_text(SAMPLE.read_text(), dialect="manabox")
    commander_rows = [c for c in result.cards if c.zone == "Commander"]
    assert len(commander_rows) == 1
    assert commander_rows[0].name == "Nelly Borca, Impulsive Accuser"
