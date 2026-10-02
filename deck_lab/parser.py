"""Strict parser/validator for deck README frontmatter and board Markdown
(contract: hermes-mtg/deck/v1, hermes-mtg/board/v1).

Pure Python, no third-party dependencies for parsing itself (frontmatter is
parsed with a minimal safe YAML-scalar-subset reader so this module has no
runtime dependency beyond stdlib).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from deck_lab.models import (
    BOARD_KINDS,
    BOARD_SCHEMA_V1,
    COLOR_IDENTITY_VALUES,
    DECK_SCHEMA_V1,
    ZONES_BY_KIND,
    CardEntry,
    SourceLocation,
    ValidationError,
)

CARD_ROW_RE = re.compile(
    r"^(?P<qty>\d+) (?P<name>[^(]+?)(?: \((?P<set>[A-Za-z0-9]+)\)(?: (?P<collector>\S+))?)?$"
)


@dataclass(frozen=True)
class ParseResult:
    cards: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(e.severity == "error" for e in self.errors)

    @property
    def zone_counts(self) -> dict:
        counts: dict = {}
        for entry in self.cards:
            counts[entry.zone] = counts.get(entry.zone, 0) + entry.quantity
        return counts

    @property
    def category_counts(self) -> dict:
        counts: dict = {}
        for entry in self.cards:
            key = (entry.zone,) + entry.category_path
            counts[key] = counts.get(key, 0) + entry.quantity
        return counts

    @property
    def card_count(self) -> int:
        return sum(e.quantity for e in self.cards)

    @property
    def commander_count(self) -> int:
        return sum(e.quantity for e in self.cards if e.zone == "Commander")


def _split_frontmatter(text: str, path: str):
    """Return (frontmatter_dict_or_None, body, error_or_None)."""
    if not text.startswith("---\n"):
        return None, text, "MISSING"
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None, text, "MISSING"
    _, raw_fm, body = parts
    fm: dict = {}
    for line in raw_fm.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            return None, body, "INVALID"
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        fm[key] = _parse_scalar(value)
    return fm, body, None


def _parse_scalar(value: str):
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [v.strip() for v in inner.split(",")]
    if value.isdigit():
        return int(value)
    return value


def parse_deck_readme(text: str, path: str) -> ParseResult:
    """Validate a deck README's frontmatter (contract section 2)."""
    errors: list = []
    fm, _body, fm_error = _split_frontmatter(text, path)

    if fm_error == "MISSING" or fm is None or "schema" not in fm:
        errors.append(
            ValidationError(
                code="DECK_FRONTMATTER_MISSING",
                message="Deck README missing required frontmatter/schema field",
                path=path,
                line=1,
            )
        )
        return ParseResult(cards=[], errors=errors)

    if fm.get("schema") != DECK_SCHEMA_V1:
        errors.append(
            ValidationError(
                code="DECK_SCHEMA_UNSUPPORTED",
                message=f"Unsupported deck schema: {fm.get('schema')!r}",
                path=path,
                line=1,
            )
        )
        return ParseResult(cards=[], errors=errors)

    required = ("name", "format", "color_identity", "status")
    missing = [f for f in required if f not in fm]
    if missing:
        errors.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message=f"Deck frontmatter missing required fields: {missing}",
                path=path,
                line=1,
            )
        )
        return ParseResult(cards=[], errors=errors)

    color_identity = fm.get("color_identity") or []
    if not isinstance(color_identity, list) or any(
        c not in COLOR_IDENTITY_VALUES for c in color_identity
    ):
        errors.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message=f"Invalid color_identity: {color_identity!r}",
                path=path,
                line=1,
            )
        )
        return ParseResult(cards=[], errors=errors)

    return ParseResult(cards=[], errors=errors)


def parse_board(text: str, path: str) -> ParseResult:
    """Parse and validate a board Markdown file (contract sections 3-8.4)."""
    errors: list = []
    cards: list = []

    fm, body, fm_error = _split_frontmatter(text, path)

    if fm_error == "MISSING" or fm is None or "schema" not in fm:
        errors.append(
            ValidationError(
                code="BOARD_FRONTMATTER_MISSING",
                message="Board file missing required frontmatter/schema field",
                path=path,
                line=1,
            )
        )
        return ParseResult(cards=[], errors=errors)

    if fm.get("schema") != BOARD_SCHEMA_V1:
        errors.append(
            ValidationError(
                code="BOARD_SCHEMA_UNSUPPORTED",
                message=f"Unsupported board schema: {fm.get('schema')!r}",
                path=path,
                line=1,
            )
        )
        return ParseResult(cards=[], errors=errors)

    required = ("name", "kind", "order")
    missing = [f for f in required if f not in fm]
    if missing:
        errors.append(
            ValidationError(
                code="BOARD_FRONTMATTER_INVALID",
                message=f"Board frontmatter missing required fields: {missing}",
                path=path,
                line=1,
            )
        )
        return ParseResult(cards=[], errors=errors)

    kind = fm.get("kind")
    if kind not in BOARD_KINDS:
        errors.append(
            ValidationError(
                code="BOARD_KIND_INVALID",
                message=f"Invalid board kind: {kind!r}",
                path=path,
                line=1,
            )
        )
        return ParseResult(cards=[], errors=errors)

    allowed_zones = ZONES_BY_KIND[kind]

    # Offset: frontmatter occupies lines 1..N (opening ---, fields, closing ---)
    fm_line_count = text[: text.index("---\n", 4) + 4].count("\n")

    lines = body.splitlines()
    seen_zones: set = set()
    current_zone: Optional[str] = None
    category_path: tuple = ()
    last_heading_level: Optional[int] = None
    in_fence = False
    fence_valid = False

    for idx, raw_line in enumerate(lines):
        line_no = fm_line_count + idx + 1
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_valid = stripped == "```decklist"
                if not fence_valid:
                    errors.append(
                        ValidationError(
                            code="DECKLIST_FENCE_INVALID",
                            message=f"Expected ```decklist fence, found {stripped!r}",
                            path=path,
                            line=line_no,
                            context=stripped,
                        )
                    )
            else:
                in_fence = False
                fence_valid = False
            continue

        if in_fence:
            if not fence_valid:
                continue
            if not stripped:
                continue
            _parse_card_row(
                stripped, line_no, path, current_zone, category_path, cards, errors
            )
            continue

        heading_match = re.match(r"^(#{2,6}) (.+)$", stripped)
        if heading_match:
            hashes, title = heading_match.groups()
            level = len(hashes)
            title = title.strip()

            if level == 2:
                if title not in allowed_zones:
                    errors.append(
                        ValidationError(
                            code="ZONE_INVALID_FOR_BOARD",
                            message=f"Zone {title!r} not valid for board kind {kind!r}",
                            path=path,
                            line=line_no,
                        )
                    )
                elif title in seen_zones:
                    errors.append(
                        ValidationError(
                            code="ZONE_DUPLICATE",
                            message=f"Zone {title!r} declared more than once",
                            path=path,
                            line=line_no,
                        )
                    )
                else:
                    seen_zones.add(title)
                current_zone = title
                category_path = ()
                last_heading_level = 2
            else:
                if last_heading_level is None or level > last_heading_level + 1:
                    errors.append(
                        ValidationError(
                            code="CATEGORY_LEVEL_SKIPPED",
                            message=f"Heading level {level} skips an intervening level",
                            path=path,
                            line=line_no,
                        )
                    )
                depth = level - 3
                category_path = category_path[:depth] + (title,)
                last_heading_level = level
            continue

        if stripped and current_zone is not None and re.match(r"^\d", stripped):
            errors.append(
                ValidationError(
                    code="CARD_OUTSIDE_DECKLIST",
                    message="Card row found outside a ```decklist fence",
                    path=path,
                    line=line_no,
                    context=stripped,
                )
            )

    return ParseResult(cards=cards, errors=errors)


def _parse_card_row(
    row: str,
    line_no: int,
    path: str,
    zone: Optional[str],
    category_path: tuple,
    cards: list,
    errors: list,
) -> None:
    match = CARD_ROW_RE.match(row)
    if not match:
        errors.append(
            ValidationError(
                code="CARD_ROW_INVALID",
                message="Expected '<quantity> <name> [(SET) collector]'",
                path=path,
                line=line_no,
                context=row,
            )
        )
        return

    qty = int(match.group("qty"))
    name = match.group("name").strip()
    set_code = match.group("set")
    collector = match.group("collector")

    if (set_code is None) != (collector is None):
        errors.append(
            ValidationError(
                code="CARD_PRINTING_INCOMPLETE",
                message="Printing coordinates require both set and collector number",
                path=path,
                line=line_no,
                context=row,
            )
        )
        return

    if qty <= 0:
        errors.append(
            ValidationError(
                code="CARD_QUANTITY_INVALID",
                message=f"Card quantity must be a positive integer, got {qty}",
                path=path,
                line=line_no,
                context=row,
            )
        )
        return

    cards.append(
        CardEntry(
            quantity=qty,
            name=name,
            zone=zone or "",
            category_path=category_path,
            source=SourceLocation(path=path, line=line_no),
            set_code=set_code,
            collector_number=collector,
        )
    )
