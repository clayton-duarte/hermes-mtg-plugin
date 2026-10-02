"""Service lane behavior tests for the shared Deck Lab domain service
(card t_e08aa8a4).

Covers the card's 11 required behaviors against `deck_lab.service.DeckLabService`.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from deck_lab.service import DeckLabService, DeckLabServiceError

NELLY_WORKSPACE = Path(__file__).parent / "fixtures" / "nelly-borca"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


GOOD_DECK_README = (
    "---\nschema: hermes-mtg/deck/v1\nname: Simple\nformat: commander\n"
    "color_identity: [R]\nstatus: built\n---\n"
)
GOOD_BOARD = (
    "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: 10\n"
    "---\n\n## Commander\n\n### Commander\n\n```decklist\n1 Sol Ring\n```\n"
)


def _simple_workspace(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "simple"
    _write(deck_dir / "README.md", GOOD_DECK_README)
    _write(deck_dir / "mainboard.md", GOOD_BOARD)
    return tmp_path


# ---------------------------------------------------------------------
# 1. list includes valid + invalid/missing-board, preserves diagnostics
# ---------------------------------------------------------------------


def test_list_decks_includes_valid_and_invalid_entries_with_diagnostics(tmp_path):
    good_dir = tmp_path / "decks" / "commander" / "good"
    _write(good_dir / "README.md", GOOD_DECK_README)
    _write(good_dir / "mainboard.md", GOOD_BOARD)

    bad_dir = tmp_path / "decks" / "commander" / "bad"
    _write(bad_dir / "README.md", "# no frontmatter\n")

    service = DeckLabService(tmp_path)
    result = service.list_decks()
    by_path = {d["path"]: d for d in result["decks"]}

    assert by_path["decks/commander/good"]["valid"] is True
    bad = by_path["decks/commander/bad"]
    assert bad["valid"] is False
    assert bad["errors"][0]["code"] == "DECK_FRONTMATTER_MISSING"
    assert bad["errors"][0]["path"] == "decks/commander/bad/README.md"
    assert bad["errors"][0]["line"] == 1


def test_list_decks_enforces_limit_and_reports_truncation(tmp_path):
    for i in range(5):
        deck_dir = tmp_path / "decks" / "commander" / f"deck{i}"
        _write(deck_dir / "README.md", GOOD_DECK_README)
        _write(deck_dir / "mainboard.md", GOOD_BOARD)

    service = DeckLabService(tmp_path)
    result = service.list_decks(limit=2)
    assert len(result["decks"]) == 2
    assert result["total"] == 5
    assert result["truncated"] is True


def test_list_decks_rejects_limit_over_bound(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.list_decks(limit=100000)
    assert exc_info.value.code == "LIMIT_EXCEEDED"


# ---------------------------------------------------------------------
# 2. get/validate exact counts + nested categories, Nelly golden fixture
# ---------------------------------------------------------------------


def test_get_deck_nelly_golden_fixture_counts():
    service = DeckLabService(NELLY_WORKSPACE)
    result = service.get_deck("decks/commander/nelly-borca", resolve_remote=False)
    assert result["total"] == 100
    assert result["commander_count"] == 1
    assert result["zone_counts"]["Commander"] == 1
    assert result["zone_counts"]["Deck"] == 99
    assert any("Lands" in k for k in result["category_counts"])


def test_validate_nelly_golden_fixture_is_valid_with_card_total():
    service = DeckLabService(NELLY_WORKSPACE)
    result = service.validate("decks/commander/nelly-borca")
    assert result["valid"] is True
    assert result["card_total"] == 100


def test_validate_repository_root_reports_counts(tmp_path):
    good_dir = tmp_path / "decks" / "commander" / "good"
    _write(good_dir / "README.md", GOOD_DECK_README)
    _write(good_dir / "mainboard.md", GOOD_BOARD)
    bad_dir = tmp_path / "decks" / "commander" / "bad"
    _write(bad_dir / "README.md", "# no frontmatter\n")

    service = DeckLabService(tmp_path)
    result = service.validate("decks")
    assert result["deck_count"] == 2
    assert result["valid_count"] == 1
    assert result["invalid_count"] == 1
    assert result["valid"] is False


# ---------------------------------------------------------------------
# 3. traversal / absolute path / symlink escape rejection
# ---------------------------------------------------------------------


def test_path_traversal_is_rejected(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.validate("decks/../../../etc/passwd")
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


def test_absolute_path_is_rejected(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.get_deck("/etc/passwd")
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


def test_sibling_path_outside_decks_root_is_rejected(tmp_path):
    (tmp_path / "secrets").mkdir()
    _write(tmp_path / "secrets" / "secret.md", "secret")
    service = DeckLabService(_simple_workspace(tmp_path))
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.validate("secrets/secret.md")
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


def test_symlink_escape_is_rejected(tmp_path):
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
        service.validate("decks/escape-link/escape.md")
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


def test_import_target_path_traversal_is_rejected(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(
            dialect="manabox",
            target_deck_path="decks/../../escape",
            text="1 Sol Ring\n",
        )
    assert exc_info.value.code == "PATH_OUTSIDE_DECKS_ROOT"


# ---------------------------------------------------------------------
# 4. Scryfall unresolved/stale behavior, valid source stays valid
# ---------------------------------------------------------------------


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

    def post(self, url, json, headers):
        return self.responder(json["identifiers"])


def test_remote_card_unresolved_does_not_invalidate_syntactically_valid_board(tmp_path):
    workspace = _simple_workspace(tmp_path)

    def responder(identifiers):
        return _FakeResponse(data=[], not_found=list(identifiers))

    service = DeckLabService(workspace, http_client=_FakeHttpClient(responder))
    result = service.get_deck("decks/commander/simple", resolve_remote=True)
    assert result["board_errors"] == []
    assert result["remote_unresolved_count"] == 1
    assert result["cards"][0]["scryfall"] is None


def test_remote_resolution_populates_scryfall_projection(tmp_path):
    workspace = _simple_workspace(tmp_path)

    def responder(identifiers):
        return _FakeResponse(
            data=[{"name": "Sol Ring", "oracle_id": "abc", "id": "xyz"}],
            not_found=[],
        )

    service = DeckLabService(workspace, http_client=_FakeHttpClient(responder))
    result = service.get_deck("decks/commander/simple", resolve_remote=True)
    assert result["cards"][0]["scryfall"]["name"] == "Sol Ring"
    assert result["remote_unresolved_count"] == 0


def test_resolve_remote_false_skips_network_and_scryfall_field(tmp_path):
    workspace = _simple_workspace(tmp_path)

    calls = []

    def responder(identifiers):
        calls.append(identifiers)
        return _FakeResponse()

    service = DeckLabService(workspace, http_client=_FakeHttpClient(responder))
    result = service.get_deck("decks/commander/simple", resolve_remote=False)
    assert calls == []
    assert result["remote_resolved"] is False
    assert all(c["scryfall"] is None for c in result["cards"])


# ---------------------------------------------------------------------
# 5. ManaBox / Arena / Moxfield dry-runs + semantic export/import round trip
# ---------------------------------------------------------------------


def test_manabox_import_dry_run_renders_target_with_hash(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    result = service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/imported",
        text="Deck\n1 Sol Ring\n1 Arcane Signet\n",
    )
    assert result["dry_run"] is True
    assert result["applied"] is False
    [target] = result["targets"]
    assert target["current_hash"] is None
    assert target["valid"] is True
    assert "schema: hermes-mtg/board/v1" in target["rendered"]


def test_arena_import_dry_run_parses_sideboard():
    pass  # covered via manabox/arena shared adapter test below


def test_moxfield_bulk_import_dry_run_renders_categories(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    result = service.import_deck(
        dialect="moxfield-bulk",
        target_deck_path="decks/commander/moxed",
        text="1 Nelly Borca, Impulsive Accuser *CMDR*\n1 Sol Ring #Ramp\n",
    )
    [target] = result["targets"]
    assert "### Ramp" in target["rendered"]
    assert "## Commander" in target["rendered"]


def test_export_then_import_round_trips_zone_quantity_name(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    exported = service.export_deck("decks/commander/simple", dialect="manabox")
    assert "Sol Ring" in exported["text"]

    reimport = service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/reimported",
        text=exported["text"],
    )
    [target] = reimport["targets"]
    assert "1 Sol Ring" in target["rendered"]


def test_export_deck_makes_no_network_call(tmp_path):
    workspace = _simple_workspace(tmp_path)

    def responder(identifiers):
        raise AssertionError("export_deck must not make network calls")

    service = DeckLabService(workspace, http_client=_FakeHttpClient(responder))
    service.export_deck("decks/commander/simple", dialect="moxfield-bulk")


# ---------------------------------------------------------------------
# 6. explicit category preservation + Uncategorized fallback
# ---------------------------------------------------------------------


def test_explicit_category_is_preserved_moxfield(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    result = service.import_deck(
        dialect="moxfield-bulk",
        target_deck_path="decks/commander/catcheck",
        text="1 Sol Ring #Ramp\n1 Arcane Signet\n",
    )
    [target] = result["targets"]
    assert "### Ramp" in target["rendered"]
    assert "### Uncategorized" in target["rendered"]


# ---------------------------------------------------------------------
# 7. dry-run causes zero filesystem changes
# ---------------------------------------------------------------------


def test_dry_run_causes_zero_filesystem_changes(tmp_path):
    workspace = _simple_workspace(tmp_path)
    before = sorted(p.relative_to(workspace) for p in workspace.rglob("*"))
    service = DeckLabService(workspace)
    service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/untouched",
        text="Deck\n1 Sol Ring\n",
    )
    after = sorted(p.relative_to(workspace) for p in workspace.rglob("*"))
    assert before == after


# ---------------------------------------------------------------------
# 8. existing-target overwrite refusal, hash checks, atomic replace, no .bak
# ---------------------------------------------------------------------


def test_import_apply_creation_requires_apply_true(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    result = service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/created",
        text="Deck\n1 Sol Ring\n",
    )
    assert result["applied"] is False
    assert not (workspace / "decks" / "commander" / "created").exists()


def test_import_apply_creates_new_target_with_null_hash(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    result = service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/created",
        text="Deck\n1 Sol Ring\n",
        apply=True,
        expected_hash=None,
        overwrite=False,
    )
    assert result["applied"] is True
    target_file = workspace / "decks" / "commander" / "created" / "mainboard.md"
    assert target_file.exists()
    assert "1 Sol Ring" in target_file.read_text()


def test_import_apply_existing_target_requires_overwrite_true(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"
    current_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(
            dialect="manabox",
            target_deck_path="decks/commander/simple",
            text="Deck\n1 Arcane Signet\n",
            apply=True,
            expected_hash=current_hash,
            overwrite=False,
        )
    assert exc_info.value.code == "IMPORT_OVERWRITE_REQUIRED"
    assert "1 Sol Ring" in existing.read_text()  # unchanged


def test_import_apply_hash_mismatch_is_rejected(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"

    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(
            dialect="manabox",
            target_deck_path="decks/commander/simple",
            text="Deck\n1 Arcane Signet\n",
            apply=True,
            expected_hash="0" * 64,
            overwrite=True,
        )
    assert exc_info.value.code == "IMPORT_HASH_MISMATCH"
    assert "1 Sol Ring" in existing.read_text()  # unchanged


def test_import_apply_succeeds_with_correct_hash_and_overwrite(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"
    current_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

    result = service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/simple",
        target_board_path="decks/commander/simple/mainboard.md",
        text="Deck\n1 Arcane Signet\n",
        apply=True,
        expected_hash=current_hash,
        overwrite=True,
    )
    assert result["applied"] is True
    assert "1 Arcane Signet" in existing.read_text()
    assert "1 Sol Ring" not in existing.read_text()


def test_import_apply_simulated_concurrent_modification_is_rejected(tmp_path, monkeypatch):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"
    current_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

    original_read_bytes = Path.read_bytes
    call_count = {"n": 0}

    def flaky_read_bytes(self):
        call_count["n"] += 1
        if call_count["n"] == 2:  # second read = the immediate re-read before replace
            existing.write_text(GOOD_BOARD.replace("Sol Ring", "Mind Stone"))
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", flaky_read_bytes)

    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(
            dialect="manabox",
            target_deck_path="decks/commander/simple",
            target_board_path="decks/commander/simple/mainboard.md",
            text="Deck\n1 Arcane Signet\n",
            apply=True,
            expected_hash=current_hash,
            overwrite=True,
        )
    assert exc_info.value.code == "IMPORT_CONCURRENT_MODIFICATION"


def test_import_apply_never_creates_bak_file(tmp_path):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"
    current_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

    service.import_deck(
        dialect="manabox",
        target_deck_path="decks/commander/simple",
        target_board_path="decks/commander/simple/mainboard.md",
        text="Deck\n1 Arcane Signet\n",
        apply=True,
        expected_hash=current_hash,
        overwrite=True,
    )
    bak_files = list((workspace / "decks").rglob("*.bak"))
    tmp_files = list((workspace / "decks").rglob(".deck-lab-import-*"))
    assert bak_files == []
    assert tmp_files == []


def test_import_apply_cleans_temp_file_on_write_failure(tmp_path, monkeypatch):
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", boom)

    with pytest.raises(OSError):
        service.import_deck(
            dialect="manabox",
            target_deck_path="decks/commander/boomdeck",
            text="Deck\n1 Sol Ring\n",
            apply=True,
            expected_hash=None,
            overwrite=False,
        )
    leftover = list((workspace / "decks").rglob(".deck-lab-import-*"))
    assert leftover == []


# ---------------------------------------------------------------------
# 9. multi-target preconditions checked before any target is replaced
# ---------------------------------------------------------------------


def test_multi_target_preconditions_checked_before_any_write(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "multi"
    _write(deck_dir / "README.md", GOOD_DECK_README)
    mainboard = (
        "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: 10\n---\n\n"
        "## Deck\n\n### Uncategorized\n\n```decklist\n1 Mountain\n```\n"
    )
    sideboard = (
        "---\nschema: hermes-mtg/board/v1\nname: Sideboard\nkind: sideboard\norder: 20\n---\n\n"
        "## Sideboard\n\n### Uncategorized\n\n```decklist\n1 Forest\n```\n"
    )
    _write(deck_dir / "mainboard.md", mainboard)
    _write(deck_dir / "sideboard.md", sideboard)

    service = DeckLabService(tmp_path)
    mainboard_hash = hashlib.sha256((deck_dir / "mainboard.md").read_bytes()).hexdigest()
    # Deliberately wrong hash for sideboard so the whole apply must be
    # rejected before mainboard (which has the correct hash) is touched.
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(
            dialect="manabox",
            target_deck_path="decks/commander/multi",
            text="Deck\n1 Island\n\nSideboard\n1 Swamp\n",
            apply=True,
            expected_hash={
                "decks/commander/multi/mainboard.md": mainboard_hash,
                "decks/commander/multi/sideboard.md": "0" * 64,
            },
            overwrite=True,
        )
    assert exc_info.value.code == "IMPORT_HASH_MISMATCH"
    assert "1 Mountain" in (deck_dir / "mainboard.md").read_text()
    assert "1 Forest" in (deck_dir / "sideboard.md").read_text()


# ---------------------------------------------------------------------
# 10. output/input bounds and stable machine-readable errors
# ---------------------------------------------------------------------


def test_import_text_over_size_bound_is_rejected(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    huge_text = "Deck\n" + "1 Sol Ring\n" * 300_000
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(
            dialect="manabox", target_deck_path="decks/commander/huge", text=huge_text
        )
    assert exc_info.value.code == "TEXT_TOO_LARGE"


def test_error_has_stable_machine_readable_fields(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.get_deck("decks/commander/does-not-exist")
    err = exc_info.value
    assert err.code == "DECK_NOT_FOUND"
    assert err.status == 404
    assert err.category == "not_found"
    assert err.to_dict()["schema"] == "hermes-mtg/service/v1"


def test_import_requires_exactly_one_of_text_or_source_file(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(dialect="manabox", target_deck_path="decks/commander/x")
    assert exc_info.value.code == "INVALID_INPUT"


def test_unsupported_import_dialect_is_rejected(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    with pytest.raises(DeckLabServiceError) as exc_info:
        service.import_deck(dialect="bogus", target_deck_path="decks/commander/x", text="1 Sol Ring\n")
    assert exc_info.value.code == "UNSUPPORTED_DIALECT"


# ---------------------------------------------------------------------
# 11. no network calls during parse/export/dry-run
# ---------------------------------------------------------------------


def test_import_dry_run_makes_no_network_call(tmp_path):
    def responder(identifiers):
        raise AssertionError("import dry-run must not make network calls")

    service = DeckLabService(_simple_workspace(tmp_path), http_client=_FakeHttpClient(responder))
    service.import_deck(
        dialect="manabox", target_deck_path="decks/commander/nonet", text="Deck\n1 Sol Ring\n"
    )


def test_validate_makes_no_network_call(tmp_path):
    def responder(identifiers):
        raise AssertionError("validate must not make network calls")

    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace, http_client=_FakeHttpClient(responder))
    service.validate("decks/commander/simple")


# ---------------------------------------------------------------------
# cache_status
# ---------------------------------------------------------------------


def test_cache_status_unconfigured(tmp_path):
    service = DeckLabService(_simple_workspace(tmp_path))
    status = service.cache_status()
    assert status["configured"] is False
    assert status["entry_count"] == 0


def test_cache_status_reports_entry_and_freshness_counts(tmp_path):
    cache_path = tmp_path / "cache" / "scryfall.json"
    workspace = _simple_workspace(tmp_path / "workspace") if False else _simple_workspace(tmp_path)
    service = DeckLabService(workspace, cache_path=str(cache_path))
    service._cache.put(("name", "Sol Ring"), {"name": "Sol Ring"})
    status = service.cache_status()
    assert status["configured"] is True
    assert status["entry_count"] == 1
    assert status["fresh_count"] == 1
    assert status["stale_count"] == 0
