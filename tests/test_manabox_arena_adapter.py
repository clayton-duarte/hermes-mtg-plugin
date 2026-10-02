"""Additional adapter behavior tests for the ManaBox/Arena interchange lane
(t_21314a59), beyond the promoted RED contract test.
"""

from __future__ import annotations

import os
from pathlib import Path

from deck_lab.adapters.manabox_arena import (
    export_text,
    import_text,
    to_board_markdown,
)

MANABOX_SAMPLE = Path(__file__).parent / "fixtures" / "interchange" / "manabox_sample.txt"
ARENA_SAMPLE = Path(__file__).parent / "fixtures" / "interchange" / "arena_sample.txt"


def test_arena_sideboard_section_is_recognized():
    result = import_text(ARENA_SAMPLE.read_text(), dialect="arena")
    sideboard_rows = [c for c in result.cards if c.zone == "Sideboard"]
    assert len(sideboard_rows) == 1
    assert sideboard_rows[0].name == "Path to Exile"
    assert sideboard_rows[0].quantity == 1


def test_unambiguous_section_rows_default_to_uncategorized_category():
    result = import_text(MANABOX_SAMPLE.read_text(), dialect="manabox")
    assert all(c.category == "Uncategorized" for c in result.cards)


def test_printing_coordinate_is_parsed_when_present():
    text = "Deck\n1 Sol Ring (CMR) 123\n"
    result = import_text(text, dialect="manabox")
    [card] = result.cards
    assert card.set_code == "CMR"
    assert card.collector_number == "123"
    assert card.name == "Sol Ring"


def test_to_board_markdown_normalizes_and_validates_via_shared_parser():
    result = import_text(MANABOX_SAMPLE.read_text(), dialect="manabox")
    markdown, parse_result = to_board_markdown(result, board_name="Imported Deck")
    assert "schema: hermes-mtg/board/v1" in markdown
    assert "## Commander" in markdown
    assert "## Deck" in markdown
    # The shared parser lane (deck_lab.parser) is a separate, independently
    # developed contract; this adapter only needs to call it and surface its
    # result without raising, not assert on that lane's own behavior.
    assert not parse_result.errors


def test_export_text_is_conservative_plain_text_no_markdown_no_frontmatter():
    result = import_text(MANABOX_SAMPLE.read_text(), dialect="manabox")
    exported = export_text(result, dialect="manabox")
    assert "---" not in exported
    assert "```" not in exported
    assert "#" not in exported
    assert "Commander" in exported
    assert "1 Nelly Borca, Impulsive Accuser" in exported


def test_export_then_import_round_trips_zone_quantity_and_name():
    original = import_text(MANABOX_SAMPLE.read_text(), dialect="manabox")
    exported = export_text(original, dialect="manabox")
    reimported = import_text(exported, dialect="manabox")

    def key(card):
        return (card.zone, card.quantity, card.name)

    assert sorted(map(key, reimported.cards)) == sorted(map(key, original.cards))


def test_import_and_export_perform_no_filesystem_mutation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sorted(tmp_path.iterdir())
    result = import_text(MANABOX_SAMPLE.read_text(), dialect="manabox")
    to_board_markdown(result)
    export_text(result, dialect="manabox")
    after = sorted(tmp_path.iterdir())
    assert before == after == []
