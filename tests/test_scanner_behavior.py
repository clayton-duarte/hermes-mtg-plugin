"""Scanner lane behavior tests beyond the promoted RED contract test (t_eb91eeab).

Covers invalid decks, missing-board decks, traversal/symlink rejection, lazy
large-repo revision behavior, and revision change/no-change semantics.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from deck_lab.scanner import compute_revision, revision_cache_key, scan_repository

FIXTURES = Path(__file__).parent / "fixtures"
NELLY_WORKSPACE = FIXTURES / "nelly-borca"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_scan_repository_reports_invalid_deck_with_bad_frontmatter(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "broken-deck"
    _write(deck_dir / "README.md", "# No frontmatter at all\n")
    _write(
        deck_dir / "mainboard.md",
        "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: 10\n---\n\n## Commander\n",
    )

    decks = scan_repository(tmp_path / "decks")
    match = next(d for d in decks if d.path == "decks/commander/broken-deck")
    assert match.valid is False
    assert "DECK_FRONTMATTER_MISSING" in [e.code for e in match.errors]
    diag = next(e for e in match.errors if e.code == "DECK_FRONTMATTER_MISSING")
    assert diag.path == "decks/commander/broken-deck"
    assert diag.severity == "error"


def test_scan_repository_reports_missing_board_deck(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "no-board-deck"
    _write(
        deck_dir / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: No Board\nformat: commander\n"
        "color_identity: [R]\nstatus: built\n---\n",
    )

    decks = scan_repository(tmp_path / "decks")
    match = next(d for d in decks if d.path == "decks/commander/no-board-deck")
    assert match.valid is False
    assert "BOARD_FRONTMATTER_MISSING" in [e.code for e in match.errors]
    assert match.boards == ()


def test_scan_repository_rejects_traversal_escape(tmp_path):
    decks_root = tmp_path / "decks"
    deck_dir = decks_root / "commander" / "traversal-deck"
    _write(deck_dir / "README.md", "---\nschema: hermes-mtg/deck/v1\nname: X\n---\n")

    outside = tmp_path / "outside-decks-root"
    outside.mkdir()
    _write(outside / "escape.md", "escaped content")

    # Craft a directory entry name containing literal '..' components is not
    # possible via mkdir; instead verify that a path which resolves outside
    # decks_root (simulated via a crafted Path) is rejected by the internal
    # resolver used by scan_repository.
    from deck_lab.scanner import _resolve_within

    traversal_path = decks_root / "commander" / ".." / ".." / "outside-decks-root" / "escape.md"
    assert _resolve_within(decks_root.resolve(), traversal_path) is None

    # Normal scan still succeeds and does not include anything from outside.
    decks = scan_repository(decks_root)
    assert all("outside-decks-root" not in d.path for d in decks)


def test_scan_repository_rejects_symlink_escape(tmp_path):
    decks_root = tmp_path / "decks"
    deck_dir = decks_root / "commander" / "symlinked-deck"
    deck_dir.mkdir(parents=True)

    outside = tmp_path / "outside-decks-root"
    outside.mkdir()
    _write(outside / "README.md", "---\nschema: hermes-mtg/deck/v1\nname: Escaped\n---\n")

    symlink_path = deck_dir / "README.md"
    try:
        os.symlink(outside / "README.md", symlink_path)
    except OSError:
        return  # symlinks unsupported on this filesystem; skip

    decks = scan_repository(decks_root)
    # The symlinked README resolves outside decks_root, so it must not be
    # treated as a readable deck entry pointing at the escaped content.
    match = next((d for d in decks if d.path == "decks/commander/symlinked-deck"), None)
    if match is not None:
        assert match.name != "Escaped"


def test_compute_revision_changes_when_board_file_mtime_changes(tmp_path):
    decks_root = tmp_path / "decks"
    mainboard = decks_root / "commander" / "nelly-borca" / "mainboard.md"
    _write(
        mainboard,
        "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: 10\n---\n\n## Commander\n",
    )
    _write(
        decks_root / "commander" / "nelly-borca" / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Nelly\n---\n",
    )

    before = compute_revision(decks_root)
    time.sleep(0.01)
    os.utime(mainboard, None)
    after = compute_revision(decks_root)

    assert before != after


def test_compute_revision_is_stable_with_no_changes(tmp_path):
    decks_root = tmp_path / "decks"
    _write(
        decks_root / "commander" / "nelly-borca" / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Nelly\n---\n",
    )

    first = compute_revision(decks_root)
    second = compute_revision(decks_root)
    assert first == second


def test_compute_revision_excludes_cache_and_images_dirs(tmp_path):
    decks_root = tmp_path / "decks"
    _write(
        decks_root / "commander" / "nelly-borca" / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Nelly\n---\n",
    )
    before = compute_revision(decks_root)

    _write(decks_root / "cache" / "stale.md", "ignored")
    _write(decks_root / "commander" / "nelly-borca" / "images" / "art.md", "ignored")

    after = compute_revision(decks_root)
    assert before == after


def test_revision_cache_key_differs_by_context():
    key_a = revision_cache_key(
        connection="local", profile="builder", cwd="/repo-a", repository_id="r1"
    )
    key_b = revision_cache_key(
        connection="local", profile="builder", cwd="/repo-b", repository_id="r1"
    )
    assert key_a != key_b


def test_scan_repository_does_not_parse_decklist_cards(tmp_path, monkeypatch):
    """Lazy parsing: scan_repository must never call the decklist parser."""

    import deck_lab.parser as parser_module

    calls = []
    monkeypatch.setattr(
        parser_module,
        "parse_board",
        lambda *a, **k: calls.append(1) or parser_module.ParseResult(),
    )

    decks_root = NELLY_WORKSPACE / "decks"
    scan_repository(decks_root)
    assert calls == []
