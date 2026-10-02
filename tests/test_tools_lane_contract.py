"""Behavior tests for the five thin Hermes tool wrappers (card t_b5b4148d).

These call `deck_lab.tools` handler functions directly (bypassing the Hermes
plugin loader, which isn't importable from this standalone test env) and
assert the exact JSON contract: bounded, machine-readable, path/line
diagnostics preserved, deck_import's dry-run/hash/overwrite/concurrent-
modification semantics, and manifest/registration parity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

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
# manifest / registration parity
# ---------------------------------------------------------------------


def test_tools_module_registers_exactly_the_five_manifest_tools():
    from deck_lab import tools as deck_tools

    class _FakeCtx:
        def __init__(self):
            self.registered = []

        def register_tool(self, name, **kwargs):
            self.registered.append(name)

    ctx = _FakeCtx()
    deck_tools.register_tools(ctx)

    import yaml

    manifest = yaml.safe_load((Path(__file__).parent.parent / "plugin.yaml").read_text())
    assert sorted(ctx.registered) == sorted(manifest["tools"])
    assert sorted(ctx.registered) == [
        "deck_export",
        "deck_get",
        "deck_import",
        "deck_list",
        "deck_validate",
    ]


# ---------------------------------------------------------------------
# deck_list / deck_get / deck_validate / deck_export are thin + bounded
# ---------------------------------------------------------------------


def test_deck_list_returns_bounded_json_with_decks(tmp_path):
    from deck_lab.tools import handle_deck_list

    raw = handle_deck_list({"workspace_root": str(_simple_workspace(tmp_path))})
    data = json.loads(raw)
    assert data["decks"][0]["path"] == "decks/commander/simple"
    assert "error" not in data


def test_deck_get_returns_board_errors_with_source_path_line(tmp_path):
    from deck_lab.tools import handle_deck_get

    workspace = tmp_path
    bad_dir = workspace / "decks" / "commander" / "bad"
    _write(bad_dir / "README.md", GOOD_DECK_README)
    _write(bad_dir / "mainboard.md", "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: 10\n---\n\nnot a decklist\n")

    raw = handle_deck_get({
        "workspace_root": str(workspace),
        "deck_path": "decks/commander/bad",
        "resolve_remote": False,
    })
    data = json.loads(raw)
    assert data["board_errors"], "expected at least one board error"
    err = data["board_errors"][0]
    assert err.get("path")
    assert "line" in err


def test_deck_validate_not_found_maps_to_tool_error(tmp_path):
    from deck_lab.tools import handle_deck_validate

    raw = handle_deck_validate({
        "workspace_root": str(_simple_workspace(tmp_path)),
        "target_path": "decks/commander/does-not-exist",
    })
    data = json.loads(raw)
    assert data["error"]
    assert data.get("code") == "PATH_OUTSIDE_DECKS_ROOT"


def test_deck_export_returns_text_and_losses(tmp_path):
    from deck_lab.tools import handle_deck_export

    raw = handle_deck_export({
        "workspace_root": str(_simple_workspace(tmp_path)),
        "deck_path": "decks/commander/simple",
        "dialect": "manabox",
    })
    data = json.loads(raw)
    assert "Sol Ring" in data["text"]
    assert isinstance(data["losses"], list)


# ---------------------------------------------------------------------
# deck_import: dry-run default, hash mismatch, overwrite refusal,
# atomic apply, no .bak, concurrent modification abort.
# ---------------------------------------------------------------------


def test_deck_import_defaults_to_dry_run(tmp_path):
    from deck_lab.tools import handle_deck_import

    workspace = _simple_workspace(tmp_path)
    raw = handle_deck_import({
        "workspace_root": str(workspace),
        "dialect": "manabox",
        "target_deck_path": "decks/commander/created",
        "text": "Deck\n1 Sol Ring\n",
    })
    data = json.loads(raw)
    assert data["dry_run"] is True
    assert data["applied"] is False
    assert not (workspace / "decks" / "commander" / "created").exists()


def test_deck_import_apply_existing_target_requires_overwrite(tmp_path):
    from deck_lab.tools import handle_deck_import

    workspace = _simple_workspace(tmp_path)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"
    current_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

    raw = handle_deck_import({
        "workspace_root": str(workspace),
        "dialect": "manabox",
        "target_deck_path": "decks/commander/simple",
        "text": "Deck\n1 Arcane Signet\n",
        "apply": True,
        "expected_hash": current_hash,
        "overwrite": False,
    })
    data = json.loads(raw)
    assert data["error"]
    assert data.get("code") == "IMPORT_OVERWRITE_REQUIRED"
    assert "1 Sol Ring" in existing.read_text()  # unchanged


def test_deck_import_apply_hash_mismatch_rejected(tmp_path):
    from deck_lab.tools import handle_deck_import

    workspace = _simple_workspace(tmp_path)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"

    raw = handle_deck_import({
        "workspace_root": str(workspace),
        "dialect": "manabox",
        "target_deck_path": "decks/commander/simple",
        "text": "Deck\n1 Arcane Signet\n",
        "apply": True,
        "expected_hash": "0" * 64,
        "overwrite": True,
    })
    data = json.loads(raw)
    assert data["error"]
    assert data.get("code") == "IMPORT_HASH_MISMATCH"
    assert "1 Sol Ring" in existing.read_text()  # unchanged


def test_deck_import_apply_succeeds_atomically_with_correct_hash(tmp_path):
    from deck_lab.tools import handle_deck_import

    workspace = _simple_workspace(tmp_path)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"
    current_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

    raw = handle_deck_import({
        "workspace_root": str(workspace),
        "dialect": "manabox",
        "target_deck_path": "decks/commander/simple",
        "text": "Deck\n1 Arcane Signet\n",
        "apply": True,
        "expected_hash": current_hash,
        "overwrite": True,
    })
    data = json.loads(raw)
    assert data["applied"] is True
    assert "Arcane Signet" in existing.read_text()

    bak_files = list((workspace / "decks").rglob("*.bak"))
    assert bak_files == []


def test_deck_import_concurrent_modification_aborts(tmp_path, monkeypatch):
    from deck_lab import service as service_module
    from deck_lab.tools import handle_deck_import

    workspace = _simple_workspace(tmp_path)
    existing = workspace / "decks" / "commander" / "simple" / "mainboard.md"
    current_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

    original_resolve = service_module.DeckLabService._resolve_repo_path
    call_count = {"n": 0}

    def flaky_resolve(self, rel_path, **kwargs):
        resolved = original_resolve(self, rel_path, **kwargs)
        if rel_path == "decks/commander/simple/mainboard.md":
            call_count["n"] += 1
            if call_count["n"] == 2:
                existing.write_text("concurrently changed\n")
        return resolved

    monkeypatch.setattr(service_module.DeckLabService, "_resolve_repo_path", flaky_resolve)

    raw = handle_deck_import({
        "workspace_root": str(workspace),
        "dialect": "manabox",
        "target_deck_path": "decks/commander/simple",
        "text": "Deck\n1 Arcane Signet\n",
        "apply": True,
        "expected_hash": current_hash,
        "overwrite": True,
    })
    data = json.loads(raw)
    assert data["error"]
    assert data.get("code") == "IMPORT_CONCURRENT_MODIFICATION"
