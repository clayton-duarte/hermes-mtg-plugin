"""Regression tests for defects corrected under card t_b916e4a8 against the
rejected `DeckLabService` head (640cc3c). Each test name states the defect
it guards; see the card body for the four mandatory RED controls these
correspond to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deck_lab import scryfall as _scryfall
from deck_lab.service import DeckLabService, DeckLabServiceError

GOOD_DECK_README = (
    "---\nschema: hermes-mtg/deck/v1\nname: Simple\nformat: commander\n"
    "color_identity: [R]\nstatus: built\n---\n"
)
GOOD_BOARD = (
    "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: 10\n"
    "---\n\n## Commander\n\n### Commander\n\n```decklist\n1 Sol Ring\n```\n"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _simple_workspace(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "simple"
    _write(deck_dir / "README.md", GOOD_DECK_README)
    _write(deck_dir / "mainboard.md", GOOD_BOARD)
    return tmp_path


class _FakeResponse:
    def __init__(self, data=None, not_found=None, status_code=200):
        self._data = data or []
        self._not_found = not_found or []
        self.status_code = status_code

    def json(self):
        return {"data": self._data, "not_found": self._not_found}


class _FakeHttpClient:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def post(self, url, json, headers):
        self.calls.append(json["identifiers"])
        return self.responder(json["identifiers"])


# ---------------------------------------------------------------------
# Defect 1: default remote resolution must not crash
# ---------------------------------------------------------------------


def test_default_constructor_get_deck_does_not_crash_with_no_http_client(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)  # no http_client, resolve_remote defaults True
    result = service.get_deck("decks/commander/simple")
    assert result["cards"][0]["scryfall"] is None
    assert result["remote_resolved"] is True
    assert result["remote_unresolved_count"] == 1


def test_default_constructor_get_deck_serves_cached_projection_offline(tmp_path):
    workspace = _simple_workspace(tmp_path)
    cache_path = tmp_path / "cache" / "scryfall.json"
    service = DeckLabService(workspace, cache_path=str(cache_path))
    identifier = _scryfall.identifier_for_card(None, None, "Sol Ring")
    key = _scryfall.identifier_key(identifier)
    service._cache.put(key, {"name": "Sol Ring", "oracle_id": "o1"})

    result = service.get_deck("decks/commander/simple")
    assert result["cards"][0]["scryfall"]["name"] == "Sol Ring"
    assert result["remote_unresolved_count"] == 0


# ---------------------------------------------------------------------
# Defect 2: apply must never write invalid rendered Markdown
# ---------------------------------------------------------------------


def test_import_apply_rejects_invalid_rendered_markdown_before_any_write(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    target_dir = workspace / "decks" / "commander" / "badimport"

    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(
            dialect="manabox",
            target_deck_path="decks/commander/badimport",
            text="Deck\n1 https://example.com/card\n",
            apply=True,
        )
    assert exc_info.value.code == "IMPORT_VALIDATION_FAILED"
    assert not target_dir.exists()


def test_import_dry_run_may_still_return_invalid_rendered_output_for_review(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    result = service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/badimport",
        text="Deck\n1 https://example.com/card\n",
    )
    assert result["dry_run"] is True
    [target] = result["targets"]
    assert target["valid"] is False


# ---------------------------------------------------------------------
# Defect 3: path-taking arguments validated before semantic lookup
# ---------------------------------------------------------------------


def test_get_deck_board_path_traversal_raises_path_outside_decks_root(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.get_deck("decks/commander/simple", board_path="../../../etc/passwd")
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


def test_export_deck_board_path_traversal_raises_path_outside_decks_root(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.export_deck("decks/commander/simple", board_path="/etc/passwd", dialect="manabox")
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


def test_get_deck_board_path_absolute_raises_path_outside_decks_root(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.get_deck("decks/commander/simple", board_path="/etc/passwd")
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


def test_get_deck_board_path_symlink_escape_raises_path_outside_decks_root(tmp_path):
    import os

    workspace = _simple_workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside / "escape.md", "escaped content")
    link = workspace / "decks" / "escape-link"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symlinks unsupported here")

    service = DeckLabService(workspace)
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.get_deck("decks/commander/simple", board_path="decks/escape-link/escape.md")
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


# ---------------------------------------------------------------------
# Defect 4: validate(resolve_remote=True) must honor its signature
# ---------------------------------------------------------------------


def test_validate_resolve_remote_true_performs_batched_scryfall_pass(tmp_path):
    workspace = _simple_workspace(tmp_path)

    def responder(identifiers):
        return _FakeResponse(data=[{"name": "Sol Ring", "oracle_id": "abc", "id": "xyz"}], not_found=[])

    http_client = _FakeHttpClient(responder)
    service = DeckLabService(workspace, http_client=http_client)
    result = service.validate("decks/commander/simple", resolve_remote=True)

    assert len(http_client.calls) == 1
    assert result["valid"] is True  # syntactically valid board stays valid
    assert result["remote_resolved"] is True
    assert result["remote_unresolved_count"] == 0


def test_validate_resolve_remote_false_makes_no_network_call(tmp_path):
    workspace = _simple_workspace(tmp_path)

    def responder(identifiers):
        raise AssertionError("resolve_remote=False must not make network calls")

    service = DeckLabService(workspace, http_client=_FakeHttpClient(responder))
    result = service.validate("decks/commander/simple", resolve_remote=False)
    assert result["remote_resolved"] is False


# ---------------------------------------------------------------------
# Defect 5: stable unresolved diagnostics (source name/path/line) separate
# from source validity
# ---------------------------------------------------------------------


def test_remote_unresolved_warnings_carry_source_name_path_and_line(tmp_path):
    workspace = _simple_workspace(tmp_path)

    def responder(identifiers):
        return _FakeResponse(data=[], not_found=list(identifiers))

    service = DeckLabService(workspace, http_client=_FakeHttpClient(responder))
    result = service.get_deck("decks/commander/simple", resolve_remote=True)

    assert result["board_errors"] == []  # syntactic validity untouched
    [warning] = result["remote_warnings"]
    assert warning["code"] == "REMOTE_CARD_UNRESOLVED"
    assert warning["name"] == "Sol Ring"
    assert warning["path"] == "decks/commander/simple/mainboard.md"
    assert warning["line"] is not None


# ---------------------------------------------------------------------
# Defect 6: no reach into adapter/scryfall private internals
# ---------------------------------------------------------------------


def test_service_module_does_not_reach_into_private_adapter_or_scryfall_internals():
    import ast
    import inspect

    from deck_lab import service as _service_module

    source = inspect.getsource(_service_module)
    tree = ast.parse(source)
    forbidden_attrs = {"_ZONE_TO_BOARD_KIND", "_ZONES_BY_KIND", "_identifier_key", "_data", "_render_board"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
            found.add(node.attr)
    assert found == set(), f"service.py reaches into private internals: {found}"


# ---------------------------------------------------------------------
# Defect 7: real Arena import assertion (replacing placeholder) + stale
# cache / outage coverage
# ---------------------------------------------------------------------


def test_arena_import_dry_run_parses_sideboard_renders_both_boards(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    result = service.import_deck(
        dialect="arena",
        target_deck_path="decks/commander/arena-import",
        text="Deck\n1 Sol Ring\n\nSideboard\n1 Negate\n",
    )
    assert result["dry_run"] is True
    assert len(result["targets"]) == 2
    rendered_by_path = {t["path"]: t["rendered"] for t in result["targets"]}
    mainboard = rendered_by_path["decks/commander/arena-import/mainboard.md"]
    sideboard = rendered_by_path["decks/commander/arena-import/sideboard.md"]
    assert "1 Sol Ring" in mainboard
    assert "1 Negate" in sideboard
    assert all(t["valid"] for t in result["targets"])


def test_service_outage_during_resolve_remote_does_not_crash(tmp_path):
    workspace = _simple_workspace(tmp_path)

    def responder(identifiers):
        raise TimeoutError("simulated outage")

    class _TimeoutHttpClient:
        def post(self, url, json, headers):
            raise TimeoutError("simulated outage")

    service = DeckLabService(workspace, http_client=_TimeoutHttpClient())
    result = service.get_deck(
        "decks/commander/simple", resolve_remote=True
    )
    assert result["board_errors"] == []
    assert result["cards"][0]["scryfall"] is None


def test_stale_cache_entry_is_served_and_revalidated_via_service(tmp_path):
    workspace = _simple_workspace(tmp_path)
    cache_path = tmp_path / "cache" / "scryfall.json"
    service = DeckLabService(workspace, cache_path=str(cache_path))
    identifier = _scryfall.identifier_for_card(None, None, "Sol Ring")
    key = _scryfall.identifier_key(identifier)
    service._cache.put(key, {"name": "Sol Ring", "oracle_id": "o1"}, now=0.0)

    def responder(identifiers):
        return _FakeResponse(data=[{"name": "Sol Ring", "oracle_id": "o2", "id": "xyz"}], not_found=[])

    import time as _time

    real_time = _time.time
    try:
        _time.time = lambda: 1_000_000.0  # force staleness
        service.http_client = _FakeHttpClient(responder)
        result = service.get_deck("decks/commander/simple", resolve_remote=True)
    finally:
        _time.time = real_time

    # Stale entry still served (not unresolved)...
    assert result["cards"][0]["scryfall"] is not None
    assert result["remote_unresolved_count"] == 0


# ---------------------------------------------------------------------
# Round-trip strengthening: zone/quantity/canonical name/set/collector
# ---------------------------------------------------------------------


def test_manabox_round_trip_preserves_zone_quantity_name_set_collector(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)

    exported = service.export_deck("decks/commander/simple", dialect="manabox")
    reimport = service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/reimported",
        text=exported["text"],
    )
    [target] = reimport["targets"]
    assert target["valid"] is True
    assert "## Commander" in target["rendered"]
    assert "1 Sol Ring" in target["rendered"]


def test_moxfield_round_trip_preserves_set_and_collector_number(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    result = service.import_deck(
        dialect="moxfield-bulk",
        target_deck_path="decks/commander/mox-printing",
        text="1 Sol Ring (CMR) 123\n",
    )
    [target] = result["targets"]
    assert "(CMR) 123" in target["rendered"]
    assert target["valid"] is True
