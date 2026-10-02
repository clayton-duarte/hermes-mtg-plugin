"""Moxfield bulk text adapter (t_e5e51273).

Imports and exports conservative Moxfield bulk text without using any
Moxfield API or URL. Parsing tolerates (and normalizes away) provider-only
markers -- finish (`*F*`, `*E*`, ...), foil language variants, and the
`*CMDR*` board marker -- rather than treating them as canonical card-name
data. Explicit category tags (`#Category`) are preserved; cards without one
default to `Uncategorized`. Export reproduces Moxfield's bulk-import text
format and reports any information that format cannot carry (currently:
non-default categories), since Moxfield bulk text has no category/tag
column.

No network calls are made anywhere in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Quantity, name, optional trailing markers (set/collector, *MARKER*, #tag).
_ROW_RE = re.compile(r"^(\d+)\s+(.+)$")

# Provider-only finish/language markers Moxfield emits inline, e.g. `*F*`,
# `*Foil*`, `*E*` (etched), `*Japanese*`. These are normalized away from the
# card name -- never treated as canonical -- but the fact that a finish
# marker was present is reported via `warnings` so importers can see what
# was dropped.
_FINISH_MARKER_RE = re.compile(r"\*([A-Za-z]+)\*")

# The only board-shifting marker in Moxfield bulk text we treat specially.
_COMMANDER_MARKER = "CMDR"

# Explicit category/tag marker, e.g. `#Removal`.
_CATEGORY_RE = re.compile(r"#(\S+)")

# Trailing `(SET) 123` or `(SET) 123a` set/collector marker.
_SET_COLLECTOR_RE = re.compile(r"\(([A-Za-z0-9]+)\)\s+([A-Za-z0-9]+)\s*$")

_BOARD_HEADERS = {
    "sideboard": "sideboard",
    "maybeboard": "maybeboard",
    "mainboard": "mainboard",
    "deck": "mainboard",
    "commander": "commander",
}

UNCATEGORIZED = "Uncategorized"


@dataclass(frozen=True)
class Card:
    quantity: int
    name: str
    board: str = "mainboard"
    category: str = UNCATEGORIZED
    set_code: Optional[str] = None
    collector_number: Optional[str] = None
    finish: Optional[str] = None


@dataclass(frozen=True)
class ImportResult:
    cards: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass(frozen=True)
class ExportResult:
    text: str
    losses: list = field(default_factory=list)


def _strip_set_collector(body: str):
    match = _SET_COLLECTOR_RE.search(body)
    if not match:
        return body, None, None
    set_code, collector = match.group(1), match.group(2)
    return body[: match.start()].rstrip(), set_code, collector


def import_text(text: str) -> ImportResult:
    """Parse Moxfield bulk text into normalized Card rows.

    No network calls are made; this is pure text parsing.
    """

    cards: list = []
    warnings: list = []
    board = "mainboard"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header_key = line.lower()
        if header_key in _BOARD_HEADERS:
            board = _BOARD_HEADERS[header_key]
            continue

        match = _ROW_RE.match(line)
        if not match:
            continue

        quantity = int(match.group(1))
        body = match.group(2).strip()
        row_board = board

        category = UNCATEGORIZED
        cat_match = _CATEGORY_RE.search(body)
        if cat_match:
            category = cat_match.group(1)
            body = _CATEGORY_RE.sub("", body).strip()

        finish = None
        for marker_match in list(_FINISH_MARKER_RE.finditer(body)):
            marker = marker_match.group(1)
            if marker.upper() == _COMMANDER_MARKER:
                row_board = "commander"
            else:
                finish = marker
                warnings.append(f"dropped provider-only finish marker *{marker}* on {body!r}")
        body = _FINISH_MARKER_RE.sub("", body).strip()

        body, set_code, collector_number = _strip_set_collector(body)

        cards.append(
            Card(
                quantity=quantity,
                name=body.strip(),
                board=row_board,
                category=category,
                set_code=set_code,
                collector_number=collector_number,
                finish=finish,
            )
        )

    return ImportResult(cards=cards, warnings=warnings)


_BOARD_ORDER = ("commander", "mainboard", "maybeboard", "sideboard")
_BOARD_SECTION_HEADER = {
    "sideboard": "Sideboard",
    "maybeboard": "Maybeboard",
}


def export_cards(cards) -> ExportResult:
    """Render Cards as Moxfield bulk-import text.

    Reports (via `losses`) any information the bulk text format cannot
    carry -- currently, non-default categories, since Moxfield bulk text
    has no category/tag column. Commander board membership round-trips via
    the `*CMDR*` marker Moxfield itself accepts; mainboard/maybeboard/
    sideboard round-trip via section headers.
    """

    losses: list = []
    by_board: dict = {b: [] for b in _BOARD_ORDER}
    for card in cards:
        by_board.setdefault(card.board, []).append(card)
        if card.category and card.category != UNCATEGORIZED:
            losses.append(
                f"category {card.category!r} for {card.name!r} is not representable "
                "in Moxfield bulk text and will be lost on export"
            )

    lines: list = []
    for board in _BOARD_ORDER:
        rows = by_board.get(board, [])
        if not rows:
            continue
        if board in _BOARD_SECTION_HEADER:
            if lines:
                lines.append("")
            lines.append(_BOARD_SECTION_HEADER[board])
        for card in rows:
            name = card.name
            if board == "commander":
                name = f"{name} *CMDR*"
            lines.append(f"{card.quantity} {name}")

    return ExportResult(text="\n".join(lines) + ("\n" if lines else ""), losses=losses)
