"""Deterministic fixture data for the Deck Lab desktop pane (t_e9b37fbc).

This is FIXTURE/MOCK data only, conforming to the `hermes-mtg/service/v1`
schema (see deck_lab.models.SERVICE_SCHEMA_V1). It is a faithful, non-fabricated
transform of the landed golden Nelly Borca fixture
(tests/fixtures/nelly-borca/decks/commander/nelly-borca/{README,mainboard}.md):
exact quantity/name multiset (100 cards total, 78 unique names), real tags
(`politics`, `goad`), a single real `mainboard` board (Nelly has no
sideboard), and recursive category structure preserved to its real depth
(e.g. `Deck > Veggies > Interaction > Removal`). It is NOT read from Markdown
at runtime and does NOT call any backend lane -- it is a static,
in-repository dict the plugin.js pane mirrors by hand.

Scryfall projection data is only attached where it is a verified, real
Scryfall record fetched 2026-10-01 (ids/uris/images below are real). Cards
without a verified record carry no `scryfall` key (rendered as an unresolved
placeholder), except for two real in-deck names used to deterministically
exercise the `loading` and `error` projection states -- no deck/card name is
invented anywhere in this fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "hermes-mtg/service/v1"


def _card(quantity: int, name: str, scryfall: dict | None = None) -> dict:
    row = {"quantity": quantity, "name": name}
    if scryfall is not None:
        row["scryfall"] = scryfall
    return row


# Real, verified Scryfall records (fetched 2026-10-01, required headers used).
NELLY_SCRYFALL = {
    "state": "cached",
    "name": "Nelly Borca, Impulsive Accuser",
    "oracle_id": "7ef5b2b6-86da-4e4a-9456-dcbb878936c4",
    "scryfall_id": "2ef59aa9-f5e1-413a-869b-d287db95efd0",
    "scryfall_uri": "https://scryfall.com/card/mkc/4/nelly-borca-impulsive-accuser?utm_source=api",
    "mana_cost": "{2}{R}{W}",
    "layout": "normal",
    "image_uris": {
        "normal": "https://cards.scryfall.io/normal/front/2/e/2ef59aa9-f5e1-413a-869b-d287db95efd0.jpg?1783913057"
    },
    "card_faces": [],
}

SOL_RING_SCRYFALL = {
    "state": "cached",
    "name": "Sol Ring",
    "oracle_id": "6ad8011d-3471-4369-9d68-b264cc027487",
    "scryfall_id": "8ee443cc-e17a-493b-9c93-1f9e141a30e4",
    "scryfall_uri": "https://scryfall.com/card/frc/21/sol-ring?utm_source=api",
    "mana_cost": "{1}",
    "layout": "normal",
    "image_uris": {
        "normal": "https://cards.scryfall.io/normal/front/8/e/8ee443cc-e17a-493b-9c93-1f9e141a30e4.jpg?1789644446"
    },
    "card_faces": [],
}

# Real double-faced ("prepare" layout) in-deck card used for the face-toggle
# interaction. Face images are absent (real Scryfall records for `prepare`
# layout cards do not carry per-face images); the combined top-level image is
# retained and shown for both faces per architect correction.
JOINED_RESEARCHERS_SCRYFALL = {
    "state": "cached",
    "name": "Joined Researchers // Secret Rendezvous",
    "oracle_id": "ec744a2d-4a33-4807-bce0-d95cd5277b1f",
    "scryfall_id": "1ebaafe0-3a9a-424c-8698-d26e7be45343",
    "scryfall_uri": "https://scryfall.com/card/sos/23/joined-researchers-secret-rendezvous?utm_source=api",
    "mana_cost": "{1}",
    "layout": "prepare",
    "image_uris": {
        "normal": "https://cards.scryfall.io/normal/front/1/e/1ebaafe0-3a9a-424c-8698-d26e7be45343.jpg?1783903702"
    },
    "card_faces": [
        {"name": "Joined Researchers", "mana_cost": "{1}", "image_uris": {}},
        {"name": "Secret Rendezvous", "mana_cost": "{1}{W}", "image_uris": {}},
    ],
}

# Deterministic fixture-only projection states, applied to real in-deck card
# names (never an invented name/code).
LOADING_SCRYFALL = {"state": "loading", "name": "Agrus Kos, Spirit of Justice"}
ERROR_SCRYFALL = {
    "state": "error",
    "name": "Thought Vessel",
    "error": "REMOTE_CARD_UNRESOLVED",
}


def _resolve(name: str) -> dict | None:
    if name == "Nelly Borca, Impulsive Accuser":
        return NELLY_SCRYFALL
    if name == "Sol Ring":
        return SOL_RING_SCRYFALL
    if name == "Joined Researchers // Secret Rendezvous":
        return JOINED_RESEARCHERS_SCRYFALL
    if name == "Agrus Kos, Spirit of Justice":
        return LOADING_SCRYFALL
    if name == "Thought Vessel":
        return ERROR_SCRYFALL
    return None


def _cards(names_and_qty: list[tuple[int, str]]) -> list[dict]:
    return [_card(q, n, _resolve(n)) for q, n in names_and_qty]


# Exact quantity/name multiset transcribed from
# tests/fixtures/nelly-borca/decks/commander/nelly-borca/mainboard.md
# (100 cards total, 78 unique names) -- verified against that file.
COMMANDER_CARDS = [(1, "Nelly Borca, Impulsive Accuser")]

LANDS_CARDS = [
    (11, "Mountain"),
    (13, "Plains"),
    (1, "Battlefield Forge"),
    (1, "Boros Garrison"),
    (1, "Clifftop Retreat"),
    (1, "Command Tower"),
    (1, "Exotic Orchard"),
    (1, "Furycalm Snarl"),
    (1, "Rugged Prairie"),
    (1, "Sacred Peaks"),
    (1, "Sunscorched Divide"),
    (1, "Labyrinth of Skophos"),
    (1, "Rogue's Passage"),
    (1, "Reliquary Tower"),
]

RAMP_CARDS = [
    (1, "Sol Ring"),
    (1, "Arcane Signet"),
    (1, "Boros Signet"),
    (1, "Talisman of Conviction"),
    (1, "Fellwar Stone"),
    (1, "Everflowing Chalice"),
    (1, "Liquimetal Torque"),
    (1, "Thought Vessel"),
    (1, "Wayfarer's Bauble"),
    (1, "Knight of the White Orchid"),
    (1, "Loyal Warhound"),
    (1, "Keeper of the Accord"),
]

CARD_ADVANTAGE_CARDS = [
    (1, "Cut a Deal"),
    (1, "Secret Rendezvous"),
    (1, "Joined Researchers // Secret Rendezvous"),
    (1, "Tenuous Truce"),
    (1, "Key to the City"),
    (1, "Mangara, the Diplomat"),
]

REMOVAL_CARDS = [
    (1, "Path to Exile"),
    (1, "Swords to Plowshares"),
    (1, "Erode"),
    (1, "Generous Gift"),
    (1, "Chaos Warp"),
    (1, "Loran of the Third Path"),
    (1, "Requisition Raid"),
]

WIPES_CARDS = [
    (1, "Blasphemous Act"),
    (1, "Chain Reaction"),
    (1, "Promise of Loyalty"),
]

PROTECTION_CARDS = [
    (1, "Comeuppance"),
    (1, "Deflecting Palm"),
    (1, "Take the Bait"),
    (1, "Selfless Squire"),
    (1, "Your Temple Is Under Attack"),
    (1, "Redirect Lightning"),
    (1, "Reconnaissance"),
    (1, "Lightning Greaves"),
    (1, "Swiftfoot Boots"),
    (1, "Brotherhood Regalia"),
]

THEME_CARDS = [
    (1, "Agitator Ant"),
    (1, "Agrus Kos, Spirit of Justice"),
    (1, "Alexios, Deimos of Kosmos"),
    (1, "Bloodthirsty Blade"),
    (1, "Disrupt Decorum"),
    (1, "Geode Rager"),
    (1, "Hot Pursuit"),
    (1, "Martial Impetus"),
    (1, "Shiny Impetus"),
    (1, "Taunt from the Rampart"),
    (1, "The Sound of Drums"),
    (1, "Vengeful Ancestor"),
]

ENABLERS_CARDS = [
    (1, "Kazuul, Tyrant of the Cliffs"),
    (1, "Nils, Discipline Enforcer"),
    (1, "Noble Heritage"),
    (1, "War Cadence"),
    (1, "Duelist's Heritage"),
    (1, "Curse of Opulence"),
]

PAYOFFS_CARDS = [
    (1, "Brash Taunter"),
    (1, "Stuffy Doll"),
    (1, "Truefire Captain"),
    (1, "Arcbond"),
    (1, "Gisela, Blade of Goldnight"),
    (1, "Aurelia, the Law Above"),
    (1, "Insurrection"),
]


def _category(name: str, path: list[str], cards: list[dict] | None = None, subcategories: list[dict] | None = None) -> dict:
    out = {"name": name, "path": path, "cards": cards or []}
    if subcategories:
        out["subcategories"] = subcategories
    return out


MAINBOARD_CATEGORIES = [
    _category("Commander", ["Commander"], _cards(COMMANDER_CARDS)),
    _category(
        "Deck",
        ["Deck"],
        cards=[],
        subcategories=[
            _category(
                "Veggies",
                ["Deck", "Veggies"],
                cards=[],
                subcategories=[
                    _category("Lands", ["Deck", "Veggies", "Lands"], _cards(LANDS_CARDS)),
                    _category("Ramp", ["Deck", "Veggies", "Ramp"], _cards(RAMP_CARDS)),
                    _category("Card Advantage", ["Deck", "Veggies", "Card Advantage"], _cards(CARD_ADVANTAGE_CARDS)),
                    _category(
                        "Interaction",
                        ["Deck", "Veggies", "Interaction"],
                        cards=[],
                        subcategories=[
                            _category("Removal", ["Deck", "Veggies", "Interaction", "Removal"], _cards(REMOVAL_CARDS)),
                            _category("Wipes", ["Deck", "Veggies", "Interaction", "Wipes"], _cards(WIPES_CARDS)),
                            _category(
                                "Protection & Reflection",
                                ["Deck", "Veggies", "Interaction", "Protection & Reflection"],
                                _cards(PROTECTION_CARDS),
                            ),
                        ],
                    ),
                ],
            ),
            _category(
                "Gameplan",
                ["Deck", "Gameplan"],
                cards=[],
                subcategories=[
                    _category(
                        "Theme — Goad & Suspect",
                        ["Deck", "Gameplan", "Theme — Goad & Suspect"],
                        _cards(THEME_CARDS),
                    ),
                    _category(
                        "Enablers — The Funnel",
                        ["Deck", "Gameplan", "Enablers — The Funnel"],
                        _cards(ENABLERS_CARDS),
                    ),
                    _category(
                        "Payoffs — Damage Conversion & Finishers",
                        ["Deck", "Gameplan", "Payoffs — Damage Conversion & Finishers"],
                        _cards(PAYOFFS_CARDS),
                    ),
                ],
            ),
        ],
    ),
]

# Invalid-candidate: projected from the existing malformed golden fixture
# tests/fixtures/malformed/card_quantity_invalid_zero.md ("0 Sol Ring" under
# Deck > Veggies). Visibly identified as its source; not an invented deck.
INVALID_DECK = {
    "path": "tests/fixtures/malformed/card_quantity_invalid_zero",
    "name": "malformed/card_quantity_invalid_zero.md (projected)",
    "format": "commander",
    "color_identity": [],
    "status": "draft",
    "tags": [],
    "valid": False,
    "errors": [
        {
            "code": "CARD_QUANTITY_INVALID",
            "message": "Quantity must be a positive integer",
            "path": "tests/fixtures/malformed/card_quantity_invalid_zero.md",
            "severity": "error",
            "line": 13,
            "context": "0 Sol Ring",
        }
    ],
    "boards": [],
}

FIXTURE = {
    "schema": SCHEMA,
    "repository_id": "fixture-repo",
    "decks": [
        {
            "path": "decks/commander/nelly-borca",
            "name": "Nelly Borca",
            "format": "commander",
            "color_identity": ["R", "W"],
            "status": "built",
            "tags": ["politics", "goad"],
            "valid": True,
            "errors": [],
            "boards": [
                {
                    "path": "decks/commander/nelly-borca/mainboard.md",
                    "name": "Mainboard",
                    "kind": "mainboard",
                    "order": 10,
                    "valid": True,
                    "errors": [],
                    "categories": MAINBOARD_CATEGORIES,
                }
            ],
        },
        INVALID_DECK,
    ],
}


def _total_and_unique(categories: list[dict]) -> tuple[int, set]:
    total = 0
    names: set = set()
    for cat in categories:
        for card in cat.get("cards", []):
            total += card["quantity"]
            names.add(card["name"])
        total_sub, names_sub = _total_and_unique(cat.get("subcategories", []))
        total += total_sub
        names |= names_sub
    return total, names


def golden_totals() -> tuple[int, int]:
    """Return (total card count, unique name count) for the mainboard."""
    total, names = _total_and_unique(MAINBOARD_CATEGORIES)
    return total, len(names)


def load_fixture() -> dict:
    """Return a deep-ish copy of the static fixture dict (safe to mutate)."""
    return json.loads(json.dumps(FIXTURE))


def write_fixture_json(path: Path) -> Path:
    """Write the fixture to `path` as JSON (used to feed desktop/plugin.js)."""
    path.write_text(json.dumps(FIXTURE, indent=2) + "\n")
    return path


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("fixture.json")
    write_fixture_json(out)
    print(f"wrote {out}")
