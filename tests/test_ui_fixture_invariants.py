"""Executable invariants for the Deck Lab fixture (t_e9b37fbc architect review).

Guards against the fabrication defects called out in review: exact golden
quantity/name multiset, no invented board/card, recursive category depth,
quantity-summed counts, valid current Scryfall hosts/ids.
"""

from __future__ import annotations

from deck_lab.ui.fixture import FIXTURE, golden_totals


def test_golden_totals_match_mainboard_md():
    # tests/fixtures/nelly-borca/.../mainboard.md: 100 cards, 78 unique names.
    total, unique = golden_totals()
    assert total == 100
    assert unique == 78


def test_nelly_has_only_mainboard_no_invented_sideboard():
    nelly = next(d for d in FIXTURE["decks"] if d["name"] == "Nelly Borca")
    assert [b["kind"] for b in nelly["boards"]] == ["mainboard"]


def test_nelly_tags_are_real():
    nelly = next(d for d in FIXTURE["decks"] if d["name"] == "Nelly Borca")
    assert nelly["tags"] == ["politics", "goad"]


def test_no_invented_decks_beyond_nelly_and_projected_malformed():
    names = {d["name"] for d in FIXTURE["decks"]}
    assert names == {"Nelly Borca", "malformed/card_quantity_invalid_zero.md (projected)"}


def test_invalid_deck_cites_its_real_malformed_source():
    invalid = next(d for d in FIXTURE["decks"] if not d["valid"])
    assert invalid["errors"][0]["path"] == "tests/fixtures/malformed/card_quantity_invalid_zero.md"


def test_recursive_category_depth_preserved():
    mainboard = FIXTURE["decks"][0]["boards"][0]
    deck = next(c for c in mainboard["categories"] if c["name"] == "Deck")
    veggies = next(c for c in deck["subcategories"] if c["name"] == "Veggies")
    interaction = next(c for c in veggies["subcategories"] if c["name"] == "Interaction")
    removal = next(c for c in interaction["subcategories"] if c["name"] == "Removal")
    assert removal["path"] == ["Deck", "Veggies", "Interaction", "Removal"]
    assert any(c["name"] == "Path to Exile" for c in removal["cards"])


def test_scryfall_ids_and_hosts_are_real_and_current():
    mainboard = FIXTURE["decks"][0]["boards"][0]

    def iter_cards(categories):
        for cat in categories:
            yield from cat.get("cards", [])
            yield from iter_cards(cat.get("subcategories", []))

    resolved = {c["name"]: c["scryfall"] for c in iter_cards(mainboard["categories"]) if "scryfall" in c}
    nelly = resolved["Nelly Borca, Impulsive Accuser"]
    assert nelly["scryfall_id"] == "2ef59aa9-f5e1-413a-869b-d287db95efd0"
    assert nelly["scryfall_uri"].startswith("https://scryfall.com/card/")
    sol_ring = resolved["Sol Ring"]
    assert sol_ring["scryfall_id"] == "8ee443cc-e17a-493b-9c93-1f9e141a30e4"
    joined = resolved["Joined Researchers // Secret Rendezvous"]
    assert joined["layout"] == "prepare"
    assert len(joined["card_faces"]) == 2
    for card in resolved.values():
        if card.get("state") == "cached":
            for uri in card.get("image_uris", {}).values():
                assert uri.startswith("https://cards.scryfall.io/")
