"""Strict parser/validator for deck README frontmatter and board Markdown
(contract: hermes-mtg/deck/v1, hermes-mtg/board/v1).

Frontmatter is parsed with PyYAML's safe loader (the project's declared
runtime dependency) so any valid YAML scalar/sequence/mapping value is
supported; every required field is then validated against its exact
type/value rules from the normative file contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import yaml

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

# A card row is "<qty> <rest>" where <rest> is either a bare card name, or a
# card name followed by an exact " (SET) collector" printing annotation.
CARD_ROW_RE = re.compile(r"^(?P<qty>\d+) (?P<rest>.+)$")

# Recognizes a *candidate* trailing printing annotation: "<name> (CODE)" with
# an optional " <collector>". CODE is intentionally permissive here (any
# alnum run of 2-5 chars) so we can tell the difference between "a real
# printing annotation (possibly malformed/lowercase)" and "a card name that
# simply happens to contain parentheses" (e.g. "B.F.M. (Big Furry Monster)",
# whose parenthetical content contains spaces and is therefore never treated
# as a printing annotation at all).
PRINTING_SUFFIX_RE = re.compile(
    r"^(?P<name>.+) \((?P<set>[A-Za-z0-9]{2,5})\)(?: (?P<collector>\S+))?$"
)
SET_CODE_RE = re.compile(r"^[A-Za-z0-9]{2,5}$")

FENCE_LINE_RE = re.compile(r"^```(\S*)$")
HEADING_RE = re.compile(r"^(#{1,6}) (.+)$")


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


def _frontmatter_key_lines(raw_fm_lines: list, start_line: int) -> dict:
    """Map top-level YAML keys to their 1-indexed source file line."""
    key_lines: dict = {}
    for i, line in enumerate(raw_fm_lines):
        match = re.match(r"^([A-Za-z0-9_-]+):", line)
        if match:
            key_lines.setdefault(match.group(1), start_line + i)
    return key_lines


def _split_frontmatter(text: str, path: str):
    """Return (frontmatter_dict_or_None, body, fm_error, key_lines, body_start_line).

    fm_error is None, "MISSING", or a ("INVALID", line) tuple for malformed
    YAML that successfully located an opening fence but failed to parse.
    """
    file_lines = text.split("\n")
    if not file_lines or file_lines[0] != "---":
        return None, text, "MISSING", {}, 1

    closing_idx = None
    for i in range(1, len(file_lines)):
        if file_lines[i] == "---":
            closing_idx = i
            break

    if closing_idx is None:
        return None, text, "MISSING", {}, 1

    raw_fm_lines = file_lines[1:closing_idx]
    raw_fm = "\n".join(raw_fm_lines)
    body = "\n".join(file_lines[closing_idx + 1 :])
    body_start_line = closing_idx + 2  # 1-indexed line following closing ---

    try:
        fm = yaml.safe_load(raw_fm)
    except yaml.YAMLError as exc:
        line = 2
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            line = mark.line + 2  # +1 for opening '---' line, +1 for 0-index
        return None, body, ("INVALID", line), {}, body_start_line

    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        return None, body, ("INVALID", 2), {}, body_start_line

    key_lines = _frontmatter_key_lines(raw_fm_lines, start_line=2)
    return fm, body, None, key_lines, body_start_line


def parse_deck_readme(text: str, path: str) -> ParseResult:
    """Validate a deck README's frontmatter (contract section 2)."""
    errors: list = []
    fm, _body, fm_error, key_lines, body_start_line = _split_frontmatter(text, path)

    if fm_error == "MISSING" or fm is None or "schema" not in fm:
        errors.append(
            ValidationError(
                code="DECK_FRONTMATTER_MISSING",
                message="Deck README missing required frontmatter/schema field",
                path=path,
                line=1 if fm_error == "MISSING" else key_lines.get("schema", body_start_line),
            )
        )
        return ParseResult(cards=[], errors=errors)

    if isinstance(fm_error, tuple) and fm_error[0] == "INVALID":
        errors.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message="Deck frontmatter is not valid YAML",
                path=path,
                line=fm_error[1],
            )
        )
        return ParseResult(cards=[], errors=errors)

    if fm.get("schema") != DECK_SCHEMA_V1:
        errors.append(
            ValidationError(
                code="DECK_SCHEMA_UNSUPPORTED",
                message=f"Unsupported deck schema: {fm.get('schema')!r}",
                path=path,
                line=key_lines.get("schema", body_start_line),
            )
        )
        return ParseResult(cards=[], errors=errors)

    error = _validate_deck_fields(fm, key_lines, path, body_start_line)
    if error is not None:
        errors.append(error)
        return ParseResult(cards=[], errors=errors)

    return ParseResult(cards=[], errors=errors)


def _field_line(key_lines: dict, name: str, fallback: int) -> int:
    return key_lines.get(name, fallback)


def _validate_deck_fields(
    fm: dict, key_lines: dict, path: str, fallback_line: int
) -> Optional[ValidationError]:
    required = ("name", "format", "color_identity", "status")
    missing = [f for f in required if f not in fm]
    if missing:
        return ValidationError(
            code="DECK_FRONTMATTER_INVALID",
            message=f"Deck frontmatter missing required fields: {missing}",
            path=path,
            line=fallback_line,
        )

    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        return ValidationError(
            code="DECK_FRONTMATTER_INVALID",
            message=f"Invalid name: {name!r}",
            path=path,
            line=_field_line(key_lines, "name", fallback_line),
        )

    fmt = fm.get("format")
    if not isinstance(fmt, str) or not fmt.strip() or fmt != fmt.lower():
        return ValidationError(
            code="DECK_FRONTMATTER_INVALID",
            message=f"Invalid format: {fmt!r}",
            path=path,
            line=_field_line(key_lines, "format", fallback_line),
        )

    status = fm.get("status")
    if not isinstance(status, str) or not status.strip() or status != status.lower():
        return ValidationError(
            code="DECK_FRONTMATTER_INVALID",
            message=f"Invalid status: {status!r}",
            path=path,
            line=_field_line(key_lines, "status", fallback_line),
        )

    color_identity = fm.get("color_identity")
    if (
        not isinstance(color_identity, list)
        or any(c not in COLOR_IDENTITY_VALUES for c in color_identity)
        or len(set(color_identity)) != len(color_identity)
    ):
        return ValidationError(
            code="DECK_FRONTMATTER_INVALID",
            message=f"Invalid color_identity: {color_identity!r}",
            path=path,
            line=_field_line(key_lines, "color_identity", fallback_line),
        )

    return None


def parse_board(text: str, path: str) -> ParseResult:
    """Parse and validate a board Markdown file (contract sections 3-8.4)."""
    errors: list = []
    cards: list = []

    fm, body, fm_error, key_lines, body_start_line = _split_frontmatter(text, path)

    if fm_error == "MISSING" or fm is None or "schema" not in fm:
        errors.append(
            ValidationError(
                code="BOARD_FRONTMATTER_MISSING",
                message="Board file missing required frontmatter/schema field",
                path=path,
                line=1 if fm_error == "MISSING" else key_lines.get("schema", body_start_line),
            )
        )
        return ParseResult(cards=[], errors=errors)

    if isinstance(fm_error, tuple) and fm_error[0] == "INVALID":
        errors.append(
            ValidationError(
                code="BOARD_FRONTMATTER_INVALID",
                message="Board frontmatter is not valid YAML",
                path=path,
                line=fm_error[1],
            )
        )
        return ParseResult(cards=[], errors=errors)

    if fm.get("schema") != BOARD_SCHEMA_V1:
        errors.append(
            ValidationError(
                code="BOARD_SCHEMA_UNSUPPORTED",
                message=f"Unsupported board schema: {fm.get('schema')!r}",
                path=path,
                line=key_lines.get("schema", body_start_line),
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
                line=body_start_line,
            )
        )
        return ParseResult(cards=[], errors=errors)

    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(
            ValidationError(
                code="BOARD_FRONTMATTER_INVALID",
                message=f"Invalid name: {name!r}",
                path=path,
                line=_field_line(key_lines, "name", body_start_line),
            )
        )
        return ParseResult(cards=[], errors=errors)

    kind = fm.get("kind")
    if not isinstance(kind, str) or kind != kind.lower() or kind not in BOARD_KINDS:
        errors.append(
            ValidationError(
                code="BOARD_KIND_INVALID",
                message=f"Invalid board kind: {kind!r}",
                path=path,
                line=_field_line(key_lines, "kind", body_start_line),
            )
        )
        return ParseResult(cards=[], errors=errors)

    order = fm.get("order")
    if isinstance(order, bool) or not isinstance(order, int):
        errors.append(
            ValidationError(
                code="BOARD_FRONTMATTER_INVALID",
                message=f"Invalid order: {order!r}",
                path=path,
                line=_field_line(key_lines, "order", body_start_line),
            )
        )
        return ParseResult(cards=[], errors=errors)

    allowed_zones = ZONES_BY_KIND[kind]

    lines = body.split("\n")
    seen_zones: set = set()
    current_zone: Optional[str] = None
    category_path: tuple = ()
    last_heading_level: Optional[int] = None
    h1_count = 0
    in_fence = False
    fence_valid = False

    for idx, raw_line in enumerate(lines):
        line_no = body_start_line + idx
        stripped = raw_line.strip()

        if in_fence:
            if stripped == "```":
                in_fence = False
                fence_valid = False
                continue
            if stripped.startswith("```"):
                errors.append(
                    ValidationError(
                        code="DECKLIST_FENCE_INVALID",
                        message=f"Malformed or nested fence marker: {stripped!r}",
                        path=path,
                        line=line_no,
                        context=stripped,
                    )
                )
                continue
            if not stripped:
                continue
            if fence_valid:
                effective_category = category_path if category_path else ("Uncategorized",)
                _parse_card_row(
                    raw_line,
                    line_no,
                    path,
                    current_zone,
                    effective_category,
                    cards,
                    errors,
                )
            continue

        if stripped.startswith("```"):
            in_fence = True
            fence_match = FENCE_LINE_RE.match(stripped)
            fence_valid = bool(fence_match) and fence_match.group(1) == "decklist"
            if current_zone is None:
                errors.append(
                    ValidationError(
                        code="CARD_OUTSIDE_DECKLIST",
                        message="Decklist fence found before the first zone",
                        path=path,
                        line=line_no,
                        context=stripped,
                    )
                )
                fence_valid = False
            elif not fence_valid:
                errors.append(
                    ValidationError(
                        code="DECKLIST_FENCE_INVALID",
                        message=f"Expected ```decklist fence, found {stripped!r}",
                        path=path,
                        line=line_no,
                        context=stripped,
                    )
                )
            continue

        if not stripped:
            continue

        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            hashes, title = heading_match.groups()
            level = len(hashes)
            title = title.strip()

            if level == 1:
                h1_count += 1
                if h1_count > 1 or current_zone is not None:
                    errors.append(
                        ValidationError(
                            code="CARD_OUTSIDE_DECKLIST",
                            message="At most one H1 is allowed, before the first zone",
                            path=path,
                            line=line_no,
                            context=stripped,
                        )
                    )
                continue

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

        # Any other non-blank content outside a fence: prose, bullets,
        # links, annotations, or card rows that escaped a fence. This
        # also covers content appearing before the first zone.
        errors.append(
            ValidationError(
                code="CARD_OUTSIDE_DECKLIST",
                message="Card-like or prose content found outside a ```decklist fence",
                path=path,
                line=line_no,
                context=stripped,
            )
        )

    if in_fence:
        errors.append(
            ValidationError(
                code="DECKLIST_FENCE_INVALID",
                message="Reached end of file with an unclosed ```decklist fence",
                path=path,
                line=body_start_line + len(lines) - 1,
            )
        )

    return ParseResult(cards=cards, errors=errors)


def _parse_card_row(
    raw_line: str,
    line_no: int,
    path: str,
    zone: Optional[str],
    category_path: tuple,
    cards: list,
    errors: list,
) -> None:
    if raw_line != raw_line.strip():
        errors.append(
            ValidationError(
                code="CARD_ROW_INVALID",
                message="Card rows must not have leading/trailing whitespace",
                path=path,
                line=line_no,
                context=raw_line,
            )
        )
        return

    row = raw_line
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
    rest = match.group("rest")
    name = rest
    set_code = None
    collector = None

    printing_match = PRINTING_SUFFIX_RE.match(rest)
    if printing_match and SET_CODE_RE.match(printing_match.group("set")):
        maybe_set = printing_match.group("set")
        maybe_collector = printing_match.group("collector")

        if maybe_set != maybe_set.upper():
            errors.append(
                ValidationError(
                    code="CARD_ROW_INVALID",
                    message=f"Set code must be uppercase: {maybe_set!r}",
                    path=path,
                    line=line_no,
                    context=row,
                )
            )
            return

        if maybe_collector is None:
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

        name = printing_match.group("name")
        set_code = maybe_set
        collector = maybe_collector

    if not name or name != name.strip():
        errors.append(
            ValidationError(
                code="CARD_ROW_INVALID",
                message="Card name must be non-empty with no stray whitespace",
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
