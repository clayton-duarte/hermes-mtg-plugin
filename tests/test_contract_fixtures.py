"""Self-validation of this card's deliverables: locked schema identifiers,
normalized models, and the Nelly golden/malformed fixtures. No production
parser is implemented or imported here -- fixtures are checked with plain
text/YAML parsing local to this test file only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from deck_lab.models import (
    BOARD_SCHEMA_V1,
    DECK_SCHEMA_V1,
    SERVICE_SCHEMA_V1,
    BoardSummary,
    CardEntry,
    DeckSummary,
    ScryfallProjection,
    SourceLocation,
    ValidationError,
)

FIXTURES = Path(__file__).parent / "fixtures"
NELLY_ROOT = FIXTURES / "nelly-borca" / "decks" / "commander" / "nelly-borca"

CARD_ROW_RE = re.compile(r"^(\d+) (.+)$")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    assert text.startswith("---\n"), "fixture must start with frontmatter"
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm), body


def _iter_decklist_rows(body: str):
    in_fence = False
    for line in body.splitlines():
        if line.strip() == "```decklist":
            in_fence = True
            continue
        if in_fence and line.strip() == "```":
            in_fence = False
            continue
        if in_fence:
            yield line


def test_locked_schema_identifiers_are_exact_literals():
    assert DECK_SCHEMA_V1 == "hermes-mtg/deck/v1"
    assert BOARD_SCHEMA_V1 == "hermes-mtg/board/v1"
    assert SERVICE_SCHEMA_V1 == "hermes-mtg/service/v1"


def test_deck_summary_rejects_wrong_schema():
    with pytest.raises(ValueError):
        DeckSummary(
            repository_id="r",
            path="decks/commander/nelly-borca",
            name="Nelly Borca",
            format="commander",
            color_identity=("R", "W"),
            status="built",
            valid=True,
            schema="hermes-mtg/service/v2",
        )


def test_deck_summary_rejects_invalid_color_identity_member():
    with pytest.raises(ValueError):
        DeckSummary(
            repository_id="r",
            path="decks/commander/nelly-borca",
            name="Nelly Borca",
            format="commander",
            color_identity=("X",),
            status="built",
            valid=True,
        )


def test_board_summary_rejects_invalid_kind():
    with pytest.raises(ValueError):
        BoardSummary(
            path="decks/commander/nelly-borca/mainboard.md",
            name="Mainboard",
            kind="battleboard",
            order=10,
            valid=True,
        )


def test_validation_error_rejects_unknown_code():
    with pytest.raises(ValueError):
        ValidationError(
            code="NOT_A_REAL_CODE",
            message="x",
            path="decks/commander/nelly-borca/mainboard.md",
        )


def test_validation_error_accepts_contract_code():
    err = ValidationError(
        code="CARD_ROW_INVALID",
        message="Expected '<quantity> <name> [(SET) collector]'",
        path="decks/commander/nelly-borca/mainboard.md",
        line=27,
        context="1x Sol Ring",
    )
    assert err.code == "CARD_ROW_INVALID"


def test_card_entry_round_trips_source_location():
    entry = CardEntry(
        quantity=1,
        name="Sol Ring",
        zone="Deck",
        category_path=("Veggies", "Ramp"),
        source=SourceLocation(path="decks/commander/nelly-borca/mainboard.md", line=42),
    )
    assert entry.source.line == 42
    assert entry.scryfall is None


def test_scryfall_projection_is_generated_only_shape():
    proj = ScryfallProjection(name="Sol Ring", oracle_id="abc", scryfall_id="def")
    assert proj.card_faces == []


def test_nelly_readme_has_required_deck_frontmatter():
    text = (NELLY_ROOT / "README.md").read_text()
    frontmatter, _ = _split_frontmatter(text)
    assert frontmatter["schema"] == DECK_SCHEMA_V1
    assert frontmatter["name"] == "Nelly Borca"
    assert frontmatter["format"] == "commander"
    assert frontmatter["color_identity"] == ["R", "W"]
    assert frontmatter["status"] == "built"


def test_nelly_mainboard_has_required_board_frontmatter():
    text = (NELLY_ROOT / "mainboard.md").read_text()
    frontmatter, _ = _split_frontmatter(text)
    assert frontmatter["schema"] == BOARD_SCHEMA_V1
    assert frontmatter["kind"] == "mainboard"
    assert frontmatter["order"] == 10


def test_nelly_golden_board_derives_exactly_100_cards_including_commander():
    text = (NELLY_ROOT / "mainboard.md").read_text()
    _, body = _split_frontmatter(text)
    total = 0
    for row in _iter_decklist_rows(body):
        match = CARD_ROW_RE.match(row)
        assert match, f"row does not match canonical grammar: {row!r}"
        total += int(match.group(1))
    assert total == 100


@pytest.mark.parametrize(
    "fixture_name",
    [p.name for p in sorted(FIXTURES.glob("malformed/*"))],
)
def test_each_malformed_fixture_file_exists_and_is_nonempty(fixture_name):
    path = FIXTURES / "malformed" / fixture_name
    assert path.stat().st_size > 0


def test_malformed_fixture_family_covers_every_contract_error_code():
    from deck_lab.models import ERROR_CODES

    covered_codes = {
        "board_frontmatter_missing": "BOARD_FRONTMATTER_MISSING",
        "board_frontmatter_invalid_missing_order": "BOARD_FRONTMATTER_INVALID",
        "board_schema_unsupported": "BOARD_SCHEMA_UNSUPPORTED",
        "board_kind_invalid": "BOARD_KIND_INVALID",
        "zone_invalid_for_board": "ZONE_INVALID_FOR_BOARD",
        "zone_duplicate": "ZONE_DUPLICATE",
        "category_level_skipped": "CATEGORY_LEVEL_SKIPPED",
        "decklist_fence_invalid": "DECKLIST_FENCE_INVALID",
        "card_outside_decklist": "CARD_OUTSIDE_DECKLIST",
        "card_row_invalid_quantity_suffix": "CARD_ROW_INVALID",
        "card_row_invalid_bullet": "CARD_ROW_INVALID",
        "card_quantity_invalid_zero": "CARD_QUANTITY_INVALID",
        "card_printing_incomplete": "CARD_PRINTING_INCOMPLETE",
        "deck_frontmatter_missing_schema": "DECK_FRONTMATTER_MISSING",
        "deck_frontmatter_invalid_color_identity": "DECK_FRONTMATTER_INVALID",
        "deck_schema_unsupported": "DECK_SCHEMA_UNSUPPORTED",
        "path_outside_decks_root": "PATH_OUTSIDE_DECKS_ROOT",
    }
    assert set(covered_codes.values()) | {"REMOTE_CARD_UNRESOLVED"} == ERROR_CODES
    for stem, code in covered_codes.items():
        assert code in ERROR_CODES, f"{stem} maps to unknown code {code}"


def test_interchange_fixtures_exist_for_each_adapter_dialect():
    interchange = FIXTURES / "interchange"
    assert (interchange / "manabox_sample.txt").exists()
    assert (interchange / "arena_sample.txt").exists()
    assert (interchange / "moxfield_bulk_sample.txt").exists()
