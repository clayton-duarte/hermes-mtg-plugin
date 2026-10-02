"""Corrected contract tests for the strict parser/validator lane.

These tests invoke `parse_board`/`parse_deck_readme` directly on every
malformed fixture and assert the exact stable error code, path, and line,
plus additional cases the architect correction called out explicitly:
valid optional YAML, required field type/value rules, punctuation/parens in
card names, DFCs, annotations/links, missing categories, prose, H1 count,
pre-zone rows, whitespace, uppercase set codes, and fence balance.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deck_lab.parser import parse_board, parse_deck_readme

FIXTURES = Path(__file__).parent / "fixtures"
MALFORMED = FIXTURES / "malformed"
NELLY_ROOT = FIXTURES / "nelly-borca" / "decks" / "commander" / "nelly-borca"


def _only_error(result):
    errors = [e for e in result.errors if e.severity == "error"]
    assert len(errors) == 1, f"expected exactly one error, got {errors}"
    return errors[0]


# ---------------------------------------------------------------------------
# Board malformed fixtures: exact code + path + line
# ---------------------------------------------------------------------------


def test_board_frontmatter_missing_fixture():
    path = MALFORMED / "board_frontmatter_missing.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "BOARD_FRONTMATTER_MISSING"
    assert err.path == str(path)
    assert err.line == 1
    assert result.cards == []


def test_board_frontmatter_invalid_missing_order_fixture():
    path = MALFORMED / "board_frontmatter_invalid_missing_order.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "BOARD_FRONTMATTER_INVALID"
    assert err.path == str(path)
    assert result.cards == []


def test_board_schema_unsupported_fixture():
    path = MALFORMED / "board_schema_unsupported.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "BOARD_SCHEMA_UNSUPPORTED"
    assert err.line == 2  # the `schema:` key line


def test_board_kind_invalid_fixture():
    path = MALFORMED / "board_kind_invalid.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "BOARD_KIND_INVALID"
    assert err.line == 4  # the `kind:` key line


def test_zone_invalid_for_board_fixture():
    path = MALFORMED / "zone_invalid_for_board.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "ZONE_INVALID_FOR_BOARD"
    assert err.line == 8  # `## Sideboard` line in a mainboard file


def test_zone_duplicate_fixture():
    path = MALFORMED / "zone_duplicate.md"
    result = parse_board(path.read_text(), path=str(path))
    errors = [e.code for e in result.errors]
    assert "ZONE_DUPLICATE" in errors
    dup = next(e for e in result.errors if e.code == "ZONE_DUPLICATE")
    assert dup.line == 16  # second `## Deck`


def test_category_level_skipped_fixture():
    path = MALFORMED / "category_level_skipped.md"
    result = parse_board(path.read_text(), path=str(path))
    errors = [e.code for e in result.errors]
    assert "CATEGORY_LEVEL_SKIPPED" in errors
    skip = next(e for e in result.errors if e.code == "CATEGORY_LEVEL_SKIPPED")
    assert skip.line == 10  # `##### Removal` with no H3/H4 before it


def test_decklist_fence_invalid_fixture():
    path = MALFORMED / "decklist_fence_invalid.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "DECKLIST_FENCE_INVALID"
    assert err.line == 12  # ```text opener


def test_card_outside_decklist_fixture():
    path = MALFORMED / "card_outside_decklist.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "CARD_OUTSIDE_DECKLIST"
    assert err.line == 12  # bare `1 Sol Ring` row, no fence


def test_card_row_invalid_bullet_fixture():
    path = MALFORMED / "card_row_invalid_bullet.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "CARD_ROW_INVALID"
    assert err.line == 13  # `- 1 Sol Ring`


def test_card_row_invalid_quantity_suffix_fixture():
    path = MALFORMED / "card_row_invalid_quantity_suffix.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "CARD_ROW_INVALID"
    assert err.line == 13  # `1x Sol Ring`


def test_card_quantity_invalid_zero_fixture():
    path = MALFORMED / "card_quantity_invalid_zero.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "CARD_QUANTITY_INVALID"
    assert err.line == 13  # `0 Sol Ring`


def test_card_printing_incomplete_fixture():
    path = MALFORMED / "card_printing_incomplete.md"
    result = parse_board(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "CARD_PRINTING_INCOMPLETE"
    assert err.line == 13  # `1 Nelly Borca, Impulsive Accuser (MKM)` - no collector


# ---------------------------------------------------------------------------
# Deck README malformed fixtures: exact code + path + line
# ---------------------------------------------------------------------------


def test_deck_frontmatter_missing_schema_fixture():
    path = MALFORMED / "deck_frontmatter_missing_schema.md"
    result = parse_deck_readme(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "DECK_FRONTMATTER_MISSING"


def test_deck_schema_unsupported_fixture():
    path = MALFORMED / "deck_schema_unsupported.md"
    result = parse_deck_readme(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "DECK_SCHEMA_UNSUPPORTED"
    assert err.line == 2


def test_deck_frontmatter_invalid_color_identity_fixture():
    path = MALFORMED / "deck_frontmatter_invalid_color_identity.md"
    result = parse_deck_readme(path.read_text(), path=str(path))
    err = _only_error(result)
    assert err.code == "DECK_FRONTMATTER_INVALID"
    assert err.line == 5  # `color_identity:` key line


# ---------------------------------------------------------------------------
# Valid optional YAML (safe YAML dependency, not scalar-only reader)
# ---------------------------------------------------------------------------


def test_board_accepts_valid_optional_yaml_values():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
description: "A quoted string: with a colon"
tags: [alpha, beta]
notes: null
---

## Deck

### Veggies

```decklist
1 Sol Ring
```
"""
    result = parse_board(text, path="valid.md")
    assert result.errors == []
    assert result.card_count == 1


def test_deck_readme_accepts_valid_optional_yaml_values():
    text = """---
schema: hermes-mtg/deck/v1
name: Nelly Borca
format: commander
color_identity: [R, W]
status: built
tags:
  - politics
  - goad
---

# Nelly Borca
"""
    result = parse_deck_readme(text, path="valid-deck.md")
    assert result.errors == []


# ---------------------------------------------------------------------------
# Required field type/value errors
# ---------------------------------------------------------------------------


def test_board_rejects_non_lowercase_kind():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: Mainboard
order: 10
---

## Deck

### Veggies

```decklist
1 Sol Ring
```
"""
    result = parse_board(text, path="bad-kind.md")
    err = _only_error(result)
    assert err.code == "BOARD_KIND_INVALID"


def test_board_rejects_boolean_order():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: true
---

## Deck

### Veggies

```decklist
1 Sol Ring
```
"""
    result = parse_board(text, path="bool-order.md")
    err = _only_error(result)
    assert err.code == "BOARD_FRONTMATTER_INVALID"


def test_board_rejects_empty_name():
    text = """---
schema: hermes-mtg/board/v1
name: ""
kind: mainboard
order: 10
---

## Deck

### Veggies

```decklist
1 Sol Ring
```
"""
    result = parse_board(text, path="empty-name.md")
    err = _only_error(result)
    assert err.code == "BOARD_FRONTMATTER_INVALID"


def test_deck_readme_rejects_non_lowercase_status():
    text = """---
schema: hermes-mtg/deck/v1
name: Nelly Borca
format: commander
color_identity: [R, W]
status: Built
---

# Nelly Borca
"""
    result = parse_deck_readme(text, path="bad-status.md")
    err = _only_error(result)
    assert err.code == "DECK_FRONTMATTER_INVALID"


def test_deck_readme_rejects_duplicate_color_identity():
    text = """---
schema: hermes-mtg/deck/v1
name: Nelly Borca
format: commander
color_identity: [R, R]
status: built
---

# Nelly Borca
"""
    result = parse_deck_readme(text, path="dup-colors.md")
    err = _only_error(result)
    assert err.code == "DECK_FRONTMATTER_INVALID"


# ---------------------------------------------------------------------------
# Punctuation, parentheses, DFCs
# ---------------------------------------------------------------------------


def test_card_row_with_punctuation_and_parentheses_parses():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

```decklist
1 B.F.M. (Big Furry Monster)
```
"""
    result = parse_board(text, path="bfm.md")
    assert result.errors == []
    assert len(result.cards) == 1
    assert result.cards[0].name == "B.F.M. (Big Furry Monster)"
    assert result.cards[0].set_code is None


def test_card_row_dfc_name_parses():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

```decklist
1 Joined Researchers // Secret Rendezvous
```
"""
    result = parse_board(text, path="dfc.md")
    assert result.errors == []
    assert result.cards[0].name == "Joined Researchers // Secret Rendezvous"


def test_card_row_with_printing_coordinates_parses():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

```decklist
1 Sol Ring (LTC) 50
```
"""
    result = parse_board(text, path="printing.md")
    assert result.errors == []
    entry = result.cards[0]
    assert entry.name == "Sol Ring"
    assert entry.set_code == "LTC"
    assert entry.collector_number == "50"


def test_card_row_rejects_lowercase_set_code():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

```decklist
1 Sol Ring (ltc) 50
```
"""
    result = parse_board(text, path="lowercase-set.md")
    err = _only_error(result)
    assert err.code == "CARD_ROW_INVALID"


# ---------------------------------------------------------------------------
# Annotations / links / prose rejected outside fences
# ---------------------------------------------------------------------------


def test_markdown_link_outside_fence_rejected():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

[Sol Ring](https://scryfall.com/card/ltc/50)

```decklist
1 Sol Ring
```
"""
    result = parse_board(text, path="link.md")
    codes = [e.code for e in result.errors]
    assert "CARD_OUTSIDE_DECKLIST" in codes


def test_prose_outside_fence_rejected():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

This deck leans into goad and politics.

```decklist
1 Sol Ring
```
"""
    result = parse_board(text, path="prose.md")
    codes = [e.code for e in result.errors]
    assert "CARD_OUTSIDE_DECKLIST" in codes


def test_bullet_outside_fence_rejected():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

- Sol Ring

```decklist
1 Sol Ring
```
"""
    result = parse_board(text, path="bullet.md")
    codes = [e.code for e in result.errors]
    assert "CARD_OUTSIDE_DECKLIST" in codes


def test_row_before_first_zone_rejected():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

```decklist
1 Sol Ring
```

## Deck

### Veggies

```decklist
1 Mind Stone
```
"""
    result = parse_board(text, path="pre-zone.md")
    codes = [e.code for e in result.errors]
    assert "CARD_OUTSIDE_DECKLIST" in codes


def test_h1_count_limited_to_one():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

# Primary Title

## Deck

### Veggies

```decklist
1 Sol Ring
```

# Second Title
"""
    result = parse_board(text, path="two-h1.md")
    codes = [e.code for e in result.errors]
    assert "CARD_OUTSIDE_DECKLIST" in codes


# ---------------------------------------------------------------------------
# Missing categories -> Uncategorized
# ---------------------------------------------------------------------------


def test_fence_without_category_renders_uncategorized():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

```decklist
1 Sol Ring
```
"""
    result = parse_board(text, path="no-category.md")
    assert result.errors == []
    assert result.cards[0].category_path == ("Uncategorized",)


# ---------------------------------------------------------------------------
# Whitespace
# ---------------------------------------------------------------------------


def test_card_row_with_trailing_whitespace_rejected():
    text = (
        "---\n"
        "schema: hermes-mtg/board/v1\n"
        "name: Mainboard\n"
        "kind: mainboard\n"
        "order: 10\n"
        "---\n"
        "\n"
        "## Deck\n"
        "\n"
        "### Veggies\n"
        "\n"
        "```decklist\n"
        "1 Sol Ring   \n"
        "```\n"
    )
    result = parse_board(text, path="trailing-ws.md")
    err = _only_error(result)
    assert err.code == "CARD_ROW_INVALID"


def test_card_row_with_leading_whitespace_rejected():
    text = (
        "---\n"
        "schema: hermes-mtg/board/v1\n"
        "name: Mainboard\n"
        "kind: mainboard\n"
        "order: 10\n"
        "---\n"
        "\n"
        "## Deck\n"
        "\n"
        "### Veggies\n"
        "\n"
        "```decklist\n"
        "  1 Sol Ring\n"
        "```\n"
    )
    result = parse_board(text, path="leading-ws.md")
    err = _only_error(result)
    assert err.code == "CARD_ROW_INVALID"


# ---------------------------------------------------------------------------
# Unclosed / mismatched fences
# ---------------------------------------------------------------------------


def test_unclosed_fence_rejected_at_eof():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

```decklist
1 Sol Ring
"""
    result = parse_board(text, path="unclosed.md")
    codes = [e.code for e in result.errors]
    assert "DECKLIST_FENCE_INVALID" in codes


def test_nested_fence_rejected():
    text = """---
schema: hermes-mtg/board/v1
name: Mainboard
kind: mainboard
order: 10
---

## Deck

### Veggies

```decklist
1 Sol Ring
```decklist
1 Mind Stone
```
```
"""
    result = parse_board(text, path="nested.md")
    codes = [e.code for e in result.errors]
    assert "DECKLIST_FENCE_INVALID" in codes


def test_nelly_card_count_unaffected_by_fixes():
    text = (NELLY_ROOT / "mainboard.md").read_text()
    result = parse_board(text, path=str(NELLY_ROOT / "mainboard.md"))
    assert result.card_count == 100
    assert result.errors == []
