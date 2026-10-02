"""RED contract test for the Moxfield bulk adapter lane (t_e5e51273).

Imports successfully and executes against the skeleton adapter. The adapter
intentionally does not yet normalize provider-only finish markers (e.g.
`*F*`) out of card names, so this test fails at its named assertion
(`"*F*" not in arcane_signet.name`), not at import or lookup time.
"""

from pathlib import Path

from deck_lab.adapters.moxfield_bulk import import_text  # noqa: F401

SAMPLE = Path(__file__).parent / "fixtures" / "interchange" / "moxfield_bulk_sample.txt"


def test_import_text_strips_provider_only_finish_markers():
    result = import_text(SAMPLE.read_text())
    arcane_signet = next(c for c in result.cards if c.name.startswith("Arcane Signet"))
    assert "*F*" not in arcane_signet.name
