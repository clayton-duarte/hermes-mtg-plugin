"""Behavior tests for the Moxfield bulk text adapter (t_e5e51273).

Covers: quantity/name parsing, set/collector capture, board mapping
(commander/mainboard/maybeboard/sideboard), category preservation vs.
Uncategorized default, stripping provider-only finish/language markers,
golden semantic round-trip, explicit export loss reporting, and a
no-network guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from deck_lab.adapters.moxfield_bulk import (
    Card,
    export_cards,
    import_text,
)

SAMPLE = Path(__file__).parent / "fixtures" / "interchange" / "moxfield_bulk_sample.txt"
ADAPTER_SOURCE = Path(__file__).parent.parent / "deck_lab" / "adapters" / "moxfield_bulk.py"


def _by_name_prefix(cards, prefix):
    return next(c for c in cards if c.name.startswith(prefix))


def test_parses_quantity_and_name():
    result = import_text(SAMPLE.read_text())
    plains = _by_name_prefix(result.cards, "Plains")
    assert plains.quantity == 13
    assert plains.name == "Plains"


def test_strips_provider_only_finish_marker_from_name():
    result = import_text(SAMPLE.read_text())
    arcane_signet = _by_name_prefix(result.cards, "Arcane Signet")
    assert "*F*" not in arcane_signet.name
    assert arcane_signet.name == "Arcane Signet"


def test_finish_marker_is_not_canonical_but_reported():
    result = import_text(SAMPLE.read_text())
    arcane_signet = _by_name_prefix(result.cards, "Arcane Signet")
    assert "*F*" not in arcane_signet.name
    assert any("Arcane Signet" in w and "*F*" in w for w in result.warnings)


def test_cmdr_marker_maps_to_commander_board():
    result = import_text(SAMPLE.read_text())
    commander = _by_name_prefix(result.cards, "Nelly Borca")
    assert commander.board == "commander"
    assert "*CMDR*" not in commander.name


def test_default_board_is_mainboard():
    result = import_text(SAMPLE.read_text())
    sol_ring = _by_name_prefix(result.cards, "Sol Ring")
    assert sol_ring.board == "mainboard"


def test_explicit_category_tag_preserved():
    result = import_text(SAMPLE.read_text())
    swords = _by_name_prefix(result.cards, "Swords to Plowshares")
    assert swords.category == "Removal"
    assert "#Removal" not in swords.name


def test_default_category_is_uncategorized():
    result = import_text(SAMPLE.read_text())
    sol_ring = _by_name_prefix(result.cards, "Sol Ring")
    assert sol_ring.category == "Uncategorized"


def test_tolerated_set_collector_marker_is_captured():
    text = "1 Lightning Bolt (2X2) 117\n"
    result = import_text(text)
    bolt = result.cards[0]
    assert bolt.name == "Lightning Bolt"
    assert bolt.set_code == "2X2"
    assert bolt.collector_number == "117"


def test_sideboard_header_sets_board_context():
    text = "1 Sol Ring\n\nSideboard\n1 Rest in Peace\n"
    result = import_text(text)
    ring = _by_name_prefix(result.cards, "Sol Ring")
    rip = _by_name_prefix(result.cards, "Rest in Peace")
    assert ring.board == "mainboard"
    assert rip.board == "sideboard"


def test_maybeboard_header_sets_board_context():
    text = "Maybeboard\n1 Rest in Peace\n"
    result = import_text(text)
    rip = result.cards[0]
    assert rip.board == "maybeboard"


def test_golden_semantic_round_trip():
    result = import_text(SAMPLE.read_text())
    export = export_cards(result.cards)
    reimported = import_text(export.text)

    def key(card):
        return (card.board, card.quantity, card.name, card.set_code, card.collector_number)

    assert sorted(map(key, reimported.cards)) == sorted(map(key, result.cards))


def test_export_reports_category_loss():
    cards = [Card(quantity=1, name="Swords to Plowshares", board="mainboard", category="Removal")]
    export = export_cards(cards)
    assert any("category" in loss.lower() and "Removal" in loss for loss in export.losses)
    assert "#Removal" not in export.text


def test_export_omits_loss_for_uncategorized():
    cards = [Card(quantity=1, name="Sol Ring", board="mainboard", category="Uncategorized")]
    export = export_cards(cards)
    assert export.losses == []


def test_export_text_is_moxfield_bulk_importable():
    cards = [
        Card(quantity=1, name="Nelly Borca, Impulsive Accuser", board="commander"),
        Card(quantity=1, name="Sol Ring", board="mainboard"),
        Card(quantity=1, name="Rest in Peace", board="sideboard"),
    ]
    export = export_cards(cards)
    reimported = import_text(export.text)
    boards = {c.name: c.board for c in reimported.cards}
    assert boards["Nelly Borca, Impulsive Accuser"] == "commander"
    assert boards["Sol Ring"] == "mainboard"
    assert boards["Rest in Peace"] == "sideboard"


def test_no_network_imports_in_adapter_module():
    tree = ast.parse(ADAPTER_SOURCE.read_text())
    banned = {"requests", "urllib", "http", "httpx", "socket", "aiohttp"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & banned)


def test_no_network_call_at_runtime(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr("socket.socket.connect", _boom, raising=False)
    import_text(SAMPLE.read_text())
    export_cards([Card(quantity=1, name="Sol Ring")])
