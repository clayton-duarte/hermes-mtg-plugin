"""Normalized data model and locked schema identifiers for the hermes-mtg-plugin
V1 file contract.

This module intentionally contains ONLY the normative schema identifiers and
dataclasses describing the contract's normalized service model (see section 8
of the file contract). It implements no parsing, scanning, network, or UI
behavior -- those are separate, downstream lanes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Locked schema identifiers (contract section 2, 3, 8). These literal strings
# are the single source of truth; every lane MUST import them rather than
# re-typing the identifier.
# ---------------------------------------------------------------------------

DECK_SCHEMA_V1 = "hermes-mtg/deck/v1"
BOARD_SCHEMA_V1 = "hermes-mtg/board/v1"
SERVICE_SCHEMA_V1 = "hermes-mtg/service/v1"

# Valid color identity members (contract section 2 field rules table).
COLOR_IDENTITY_VALUES = frozenset({"W", "U", "B", "R", "G", "C"})

# Valid board kinds (contract section 3 field rules table).
BOARD_KINDS = ("mainboard", "sideboard", "maybeboard")

# Allowed H2 zones per board kind (contract section 4.2).
ZONES_BY_KIND = {
    "mainboard": ("Commander", "Deck"),
    "sideboard": ("Sideboard",),
    "maybeboard": ("Maybeboard",),
}

# Stable validation error codes (contract section 8.4).
ERROR_CODES = frozenset(
    {
        "DECK_FRONTMATTER_MISSING",
        "DECK_FRONTMATTER_INVALID",
        "DECK_SCHEMA_UNSUPPORTED",
        "BOARD_FRONTMATTER_MISSING",
        "BOARD_FRONTMATTER_INVALID",
        "BOARD_SCHEMA_UNSUPPORTED",
        "BOARD_KIND_INVALID",
        "ZONE_INVALID_FOR_BOARD",
        "ZONE_DUPLICATE",
        "CATEGORY_LEVEL_SKIPPED",
        "DECKLIST_FENCE_INVALID",
        "CARD_OUTSIDE_DECKLIST",
        "CARD_ROW_INVALID",
        "CARD_QUANTITY_INVALID",
        "CARD_PRINTING_INCOMPLETE",
        "REMOTE_CARD_UNRESOLVED",
        "PATH_OUTSIDE_DECKS_ROOT",
    }
)


# ---------------------------------------------------------------------------
# Normalized service model dataclasses (contract section 8.1-8.4).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceLocation:
    """Stable path/line reference back to the originating Markdown file."""

    path: str
    line: Optional[int] = None


@dataclass(frozen=True)
class ValidationError:
    """Contract section 8.4 error shape."""

    code: str
    message: str
    path: str
    severity: Literal["error", "warning"] = "error"
    line: Optional[int] = None
    context: Optional[str] = None

    def __post_init__(self) -> None:
        if self.code not in ERROR_CODES:
            raise ValueError(f"unknown validation error code: {self.code!r}")


@dataclass(frozen=True)
class ScryfallProjection:
    """Contract section 8.3 resolved Scryfall projection. Generated/cache-only;
    MUST NOT be written into canonical deck frontmatter or card rows."""

    name: str
    oracle_id: Optional[str] = None
    scryfall_id: Optional[str] = None
    scryfall_uri: Optional[str] = None
    mana_cost: Optional[str] = None
    layout: Optional[str] = None
    image_uris: dict = field(default_factory=dict)
    card_faces: list = field(default_factory=list)


@dataclass(frozen=True)
class CardEntry:
    """Contract section 8.2 parsed card entry."""

    quantity: int
    name: str
    zone: str
    category_path: tuple
    source: SourceLocation
    set_code: Optional[str] = None
    collector_number: Optional[str] = None
    scryfall: Optional[ScryfallProjection] = None


@dataclass(frozen=True)
class BoardSummary:
    """Board entry within a deck summary (contract section 8.1)."""

    path: str
    name: str
    kind: str
    order: int
    valid: bool
    errors: tuple = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.kind not in BOARD_KINDS:
            raise ValueError(f"invalid board kind: {self.kind!r}")


@dataclass(frozen=True)
class DeckSummary:
    """Contract section 8.1 deck summary. `schema` is always SERVICE_SCHEMA_V1."""

    repository_id: str
    path: str
    name: str
    format: str
    color_identity: tuple
    status: str
    valid: bool
    tags: tuple = field(default_factory=tuple)
    errors: tuple = field(default_factory=tuple)
    boards: tuple = field(default_factory=tuple)
    schema: str = SERVICE_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema != SERVICE_SCHEMA_V1:
            raise ValueError(f"deck summary schema must be {SERVICE_SCHEMA_V1!r}")
        for color in self.color_identity:
            if color not in COLOR_IDENTITY_VALUES:
                raise ValueError(f"invalid color identity member: {color!r}")
