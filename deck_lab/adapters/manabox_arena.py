"""ManaBox/Arena interchange adapter (t_21314a59, corrected per t_dc4a853e).

Parses ManaBox/Arena-style plain text decklists into a normalized card row
model, can normalize that model into one or more strict board Markdown
documents (one per board kind, each validated via the shared
`deck_lab.parser.parse_board`), and can export conservative sectioned plain
text with no Markdown/frontmatter. All operations here are pure string
transforms -- no filesystem mutation, no provider URL access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from deck_lab import parser as _parser

# Quantity + name, with an optional trailing "(SET) collector" printing
# coordinate, e.g. "1 Sol Ring (CMR) 123".
_ROW_RE = re.compile(
    r"^(?P<qty>\d+)\s+(?P<name>.+?)(?:\s+\((?P<set>[^)]+)\)\s+(?P<collector>\S+))?$"
)

# Recognized section headers (case-insensitive), mapped to their canonical
# zone name per the V1 file contract.
_SECTION_HEADERS = {
    "commander": "Commander",
    "deck": "Deck",
    "sideboard": "Sideboard",
    "maybeboard": "Maybeboard",
}

# Canonical zone -> board kind, per contract section 4.2 (ZONES_BY_KIND).
_ZONE_TO_BOARD_KIND = {
    "Commander": "mainboard",
    "Deck": "mainboard",
    "Sideboard": "sideboard",
    "Maybeboard": "maybeboard",
}

# Board kind -> its allowed zones, in canonical rendering order.
_ZONES_BY_KIND = {
    "mainboard": ("Commander", "Deck"),
    "sideboard": ("Sideboard",),
    "maybeboard": ("Maybeboard",),
}

# Default zone for ordinary unsectioned quantity/name rows that appear
# before any recognized section header. Plain "qty name" decklist text is
# ordinary Deck-zone content, not sideboard/maybeboard/commander content.
_DEFAULT_ZONE = "Deck"


@dataclass(frozen=True)
class CardRow:
    """A single parsed interchange card row."""

    quantity: int
    name: str
    zone: str
    category: str = "Uncategorized"
    set_code: Optional[str] = None
    collector_number: Optional[str] = None


@dataclass(frozen=True)
class ImportResult:
    cards: list = field(default_factory=list)


@dataclass(frozen=True)
class BoardDocument:
    """One strict board Markdown document plus its shared-parser validation
    result, for a single board kind (mainboard/sideboard/maybeboard)."""

    kind: str
    markdown: str
    parse_result: object


def import_text(text: str, dialect: str) -> ImportResult:
    """Parse ManaBox/Arena-style plain text into normalized card rows.

    Recognizes Commander/Deck/Sideboard/Maybeboard section headers.
    Ordinary quantity/name rows that appear before any recognized section
    header are treated as Deck-zone input (this plain text format is
    overwhelmingly single-zone decklist text with no section header at
    all), rather than being silently dropped. Category is always
    `Uncategorized` because this plain text format carries no explicit,
    unambiguous category information.
    """

    cards = []
    zone = _DEFAULT_ZONE
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = _SECTION_HEADERS.get(line.lower())
        if header is not None:
            zone = header
            continue
        match = _ROW_RE.match(line)
        if not match:
            continue
        cards.append(
            CardRow(
                quantity=int(match.group("qty")),
                name=match.group("name").strip(),
                zone=zone,
                set_code=match.group("set"),
                collector_number=match.group("collector"),
            )
        )
    return ImportResult(cards=cards)


def _zones_in_order(cards):
    seen = []
    for card in cards:
        if card.zone not in seen:
            seen.append(card.zone)
    return seen


def _categories_in_order(cards):
    seen = []
    for card in cards:
        if card.category not in seen:
            seen.append(card.category)
    return seen


def _render_card_row(card: CardRow) -> str:
    row = f"{card.quantity} {card.name}"
    if card.set_code and card.collector_number:
        row += f" ({card.set_code}) {card.collector_number}"
    return row


def _render_board_markdown(kind: str, kind_cards: list, *, board_name: str, order: int) -> str:
    zones_present = [z for z in _ZONES_BY_KIND[kind] if any(c.zone == z for c in kind_cards)]

    lines = [
        "---",
        "schema: hermes-mtg/board/v1",
        f"name: {board_name}",
        f"kind: {kind}",
        f"order: {order}",
        "---",
        "",
        f"# {board_name}",
        "",
    ]
    for zone in zones_present:
        zone_cards = [c for c in kind_cards if c.zone == zone]
        lines.append(f"## {zone}")
        lines.append("")
        for category in _categories_in_order(zone_cards):
            lines.append(f"### {category}")
            lines.append("")
            lines.append("```decklist")
            for card in zone_cards:
                if card.category != category:
                    continue
                lines.append(_render_card_row(card))
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def to_board_markdown(result: ImportResult, *, board_name: str = "Imported", order: int = 10):
    """Normalize parsed cards into one strict board Markdown document per
    board kind present (mainboard/sideboard/maybeboard), each validated by
    calling the shared parser (`deck_lab.parser.parse_board`). Mixed-zone
    input (e.g. Deck + Sideboard rows) is never collapsed into a single,
    incorrectly-kinded document -- it is rendered as separate, independently
    valid documents, one per kind. Pure function: builds and returns data,
    no filesystem mutation.

    Returns a tuple of `BoardDocument`, ordered mainboard, sideboard,
    maybeboard (only kinds actually present in `result.cards` are
    returned).
    """

    by_kind: dict = {}
    for card in result.cards:
        kind = _ZONE_TO_BOARD_KIND.get(card.zone)
        if kind is None:
            continue
        by_kind.setdefault(kind, []).append(card)

    documents = []
    for kind in ("mainboard", "sideboard", "maybeboard"):
        kind_cards = by_kind.get(kind)
        if not kind_cards:
            continue
        markdown = _render_board_markdown(kind, kind_cards, board_name=board_name, order=order)
        parse_result = _parser.parse_board(markdown, path="<imported>")
        documents.append(BoardDocument(kind=kind, markdown=markdown, parse_result=parse_result))

    return tuple(documents)


def export_text(result: ImportResult, dialect: str) -> str:
    """Export normalized card rows as conservative sectioned plain text
    (ManaBox/Arena style): zone header lines, "qty name" rows, no
    Markdown syntax and no frontmatter. Pure function: returns a string,
    performs no filesystem mutation.
    """

    zones_present = _zones_in_order(result.cards)
    sections = []
    for zone in zones_present:
        block = [zone]
        for card in result.cards:
            if card.zone != zone:
                continue
            block.append(_render_card_row(card))
        sections.append("\n".join(block))
    return "\n\n".join(sections) + "\n" if sections else ""
