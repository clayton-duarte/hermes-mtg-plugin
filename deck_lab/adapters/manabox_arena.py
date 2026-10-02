"""ManaBox/Arena interchange adapter (t_21314a59).

Parses ManaBox/Arena-style plain text decklists into a normalized card row
model, can normalize that model into strict board Markdown (validated via
the shared `deck_lab.parser.parse_board`), and can export conservative
sectioned plain text with no Markdown/frontmatter. All operations here are
pure string transforms -- no filesystem mutation, no provider URL access.
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


def import_text(text: str, dialect: str) -> ImportResult:
    """Parse ManaBox/Arena-style plain text into normalized card rows.

    Recognizes Commander/Deck/Sideboard/Maybeboard section headers. Rows
    outside any recognized section are ignored (no implicit default zone).
    Category is always `Uncategorized` because this plain text format
    carries no explicit, unambiguous category information.
    """

    cards = []
    zone = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = _SECTION_HEADERS.get(line.lower())
        if header is not None:
            zone = header
            continue
        match = _ROW_RE.match(line)
        if not match or zone is None:
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


def _zones_in_order(result: ImportResult):
    seen = []
    for card in result.cards:
        if card.zone not in seen:
            seen.append(card.zone)
    return seen


def to_board_markdown(result: ImportResult, *, board_name: str = "Imported", order: int = 10):
    """Normalize parsed cards into strict board Markdown grouped by zone,
    then validate the normalized text by calling the shared parser
    (`deck_lab.parser.parse_board`). Pure function: builds and returns a
    string plus the parser's validation result -- no filesystem mutation.
    """

    zones_present = _zones_in_order(result)
    kinds = {_ZONE_TO_BOARD_KIND.get(z, "mainboard") for z in zones_present}
    kind = kinds.pop() if len(kinds) == 1 else "mainboard"

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
        lines.append(f"## {zone}")
        lines.append("")
        lines.append(f"### {zone}")
        lines.append("")
        lines.append("```decklist")
        for card in result.cards:
            if card.zone != zone:
                continue
            row = f"{card.quantity} {card.name}"
            if card.set_code and card.collector_number:
                row += f" ({card.set_code}) {card.collector_number}"
            lines.append(row)
        lines.append("```")
        lines.append("")

    markdown = "\n".join(lines).rstrip() + "\n"
    parse_result = _parser.parse_board(markdown, path="<imported>")
    return markdown, parse_result


def export_text(result: ImportResult, dialect: str) -> str:
    """Export normalized card rows as conservative sectioned plain text
    (ManaBox/Arena style): zone header lines, "qty name" rows, no
    Markdown syntax and no frontmatter. Pure function: returns a string,
    performs no filesystem mutation.
    """

    zones_present = _zones_in_order(result)
    sections = []
    for zone in zones_present:
        block = [zone]
        for card in result.cards:
            if card.zone != zone:
                continue
            row = f"{card.quantity} {card.name}"
            if card.set_code and card.collector_number:
                row += f" ({card.set_code}) {card.collector_number}"
            block.append(row)
        sections.append("\n".join(block))
    return "\n\n".join(sections) + "\n" if sections else ""
