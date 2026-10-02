"""Additional adapter behavior tests for the ManaBox/Arena interchange lane
(t_21314a59, corrected per t_dc4a853e).
"""

from __future__ import annotations

from pathlib import Path

from deck_lab.adapters.manabox_arena import (
    export_text,
    import_text,
    to_board_markdown,
)
from deck_lab.parser import parse_board

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


def test_unsectioned_rows_are_treated_as_deck_zone_not_dropped():
    text = "1 Sol Ring\n1 Arcane Signet\n"
    result = import_text(text, dialect="manabox")
    assert len(result.cards) == 2
    assert all(c.zone == "Deck" for c in result.cards)


def test_unsectioned_rows_before_a_later_section_header_default_to_deck():
    text = "1 Sol Ring\nSideboard\n1 Path to Exile\n"
    result = import_text(text, dialect="manabox")
    by_name = {c.name: c.zone for c in result.cards}
    assert by_name["Sol Ring"] == "Deck"
    assert by_name["Path to Exile"] == "Sideboard"


def test_to_board_markdown_normalizes_and_validates_via_shared_parser():
    result = import_text(MANABOX_SAMPLE.read_text(), dialect="manabox")
    documents = to_board_markdown(result, board_name="Imported Deck")
    assert len(documents) == 1
    mainboard = documents[0]
    assert mainboard.kind == "mainboard"
    assert "schema: hermes-mtg/board/v1" in mainboard.markdown
    assert "kind: mainboard" in mainboard.markdown
    assert "## Commander" in mainboard.markdown
    assert "## Deck" in mainboard.markdown
    # The shared parser lane (deck_lab.parser) is independently developed;
    # call it directly here (not just trust the adapter's own
    # parse_result) so this test fails if the rendered document is
    # actually invalid strict board Markdown, not merely if the adapter
    # forgot to call the parser.
    independent = parse_board(mainboard.markdown, path="<test>")
    assert not independent.errors
    assert not mainboard.parse_result.errors


def test_mixed_zone_input_renders_one_validated_document_per_board_kind():
    text = "Deck\n1 Sol Ring\n\nSideboard\n1 Path to Exile\n"
    result = import_text(text, dialect="manabox")
    documents = to_board_markdown(result, board_name="Mixed")
    kinds = {doc.kind for doc in documents}
    assert kinds == {"mainboard", "sideboard"}

    for doc in documents:
        # Every emitted document must be independently valid: a mainboard
        # document never contains a Sideboard zone, and vice versa.
        assert not doc.parse_result.errors
        independent = parse_board(doc.markdown, path="<test>")
        assert not independent.errors
        if doc.kind == "mainboard":
            assert "## Sideboard" not in doc.markdown
            assert "## Deck" in doc.markdown
        if doc.kind == "sideboard":
            assert "## Deck" not in doc.markdown
            assert "## Sideboard" in doc.markdown
        assert f"kind: {doc.kind}" in doc.markdown


def test_missing_category_renders_uncategorized_heading():
    text = "Deck\n1 Sol Ring\n"
    result = import_text(text, dialect="manabox")
    [doc] = to_board_markdown(result, board_name="Imported")
    assert "### Uncategorized" in doc.markdown
    # The zone name itself must never be substituted as a fake category.
    assert "### Deck" not in doc.markdown


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


def test_export_then_import_round_trips_printing_coordinates():
    text = "Deck\n1 Sol Ring (CMR) 123\n\nSideboard\n1 Path to Exile (2XM) 45\n"
    original = import_text(text, dialect="manabox")
    exported = export_text(original, dialect="manabox")
    reimported = import_text(exported, dialect="manabox")

    def key(card):
        return (card.zone, card.quantity, card.name, card.set_code, card.collector_number)

    assert sorted(map(key, reimported.cards)) == sorted(map(key, original.cards))


def test_import_and_export_perform_no_filesystem_mutation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sorted(tmp_path.iterdir())
    result = import_text(MANABOX_SAMPLE.read_text(), dialect="manabox")
    to_board_markdown(result)
    export_text(result, dialect="manabox")
    after = sorted(tmp_path.iterdir())
    assert before == after == []
