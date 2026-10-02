"""RED contract test for the Moxfield bulk adapter lane (t_e5e51273).

Fails at import time: `deck_lab.adapters.moxfield_bulk` does not exist yet.
That is the intended RED signal for this contract card.
"""

from pathlib import Path

from deck_lab.adapters.moxfield_bulk import import_text  # noqa: F401

SAMPLE = Path(__file__).parent / "fixtures" / "interchange" / "moxfield_bulk_sample.txt"


def test_import_text_strips_provider_only_finish_markers():
    result = import_text(SAMPLE.read_text())
    arcane_signet = next(c for c in result.cards if c.name == "Arcane Signet")
    assert "*F*" not in arcane_signet.name
