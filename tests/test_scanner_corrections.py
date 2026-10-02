"""Focused tests for the scanner correction card (t_8bef6d29).

Covers: invalid-but-returned deck metadata, structured diagnostics,
missing/duplicate colors, invalid board name/order (including bool order),
relative and symlinked root inputs, symlink swap/read containment,
relevant-path-only revision behavior, and pruned traversal over a large
excluded cache/images tree.
"""

from __future__ import annotations

import os
from pathlib import Path

from deck_lab.models import ValidationError
from deck_lab.scanner import compute_revision, scan_repository

GOOD_BOARD = (
    "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: 10\n"
    "---\n\n## Commander\n"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_invalid_deck_metadata_is_returned_not_raised_with_duplicate_colors(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "dup-colors"
    _write(
        deck_dir / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Dup\nformat: commander\n"
        "color_identity: [R, R]\nstatus: built\n---\n",
    )
    _write(deck_dir / "mainboard.md", GOOD_BOARD)

    decks = scan_repository(tmp_path / "decks")
    match = next(d for d in decks if d.path == "decks/commander/dup-colors")
    assert match.valid is False
    assert all(isinstance(e, ValidationError) for e in match.errors)
    assert any(e.code == "DECK_FRONTMATTER_INVALID" for e in match.errors)


def test_invalid_deck_metadata_missing_colors_is_returned(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "no-colors"
    _write(
        deck_dir / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: NoColors\nformat: commander\n"
        "color_identity: []\nstatus: built\n---\n",
    )
    _write(deck_dir / "mainboard.md", GOOD_BOARD)

    decks = scan_repository(tmp_path / "decks")
    match = next(d for d in decks if d.path == "decks/commander/no-colors")
    assert match.valid is False
    assert any(e.code == "DECK_FRONTMATTER_INVALID" for e in match.errors)


def test_invalid_deck_uppercase_format_or_status_is_returned(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "upper-case"
    _write(
        deck_dir / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Upper\nformat: Commander\n"
        "color_identity: [R]\nstatus: Built\n---\n",
    )
    _write(deck_dir / "mainboard.md", GOOD_BOARD)

    decks = scan_repository(tmp_path / "decks")
    match = next(d for d in decks if d.path == "decks/commander/upper-case")
    assert match.valid is False
    codes = [e.code for e in match.errors]
    assert codes.count("DECK_FRONTMATTER_INVALID") >= 2


def test_diagnostics_carry_code_message_path_line_severity(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "broken"
    _write(deck_dir / "README.md", "# no frontmatter\n")

    decks = scan_repository(tmp_path / "decks")
    match = next(d for d in decks if d.path == "decks/commander/broken")
    diag = match.errors[0]
    assert diag.code == "DECK_FRONTMATTER_MISSING"
    assert diag.message
    assert diag.path == "decks/commander/broken"
    assert diag.severity == "error"
    assert hasattr(diag, "line")


def test_invalid_board_order_boolean_is_rejected(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "bool-order"
    _write(
        deck_dir / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: X\nformat: commander\n"
        "color_identity: [R]\nstatus: built\n---\n",
    )
    _write(
        deck_dir / "mainboard.md",
        "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: true\n---\n\n## Commander\n",
    )

    decks = scan_repository(tmp_path / "decks")
    match = next(d for d in decks if d.path == "decks/commander/bool-order")
    assert match.boards == ()
    assert match.valid is False


def test_invalid_board_missing_name_is_rejected(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "no-name-board"
    _write(
        deck_dir / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: X\nformat: commander\n"
        "color_identity: [R]\nstatus: built\n---\n",
    )
    _write(
        deck_dir / "mainboard.md",
        "---\nschema: hermes-mtg/board/v1\nname: ''\nkind: mainboard\norder: 10\n---\n\n## Commander\n",
    )

    decks = scan_repository(tmp_path / "decks")
    match = next(d for d in decks if d.path == "decks/commander/no-name-board")
    assert match.boards == ()


def test_scan_repository_accepts_relative_root_input(tmp_path, monkeypatch):
    deck_dir = tmp_path / "decks" / "commander" / "nelly"
    _write(
        deck_dir / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Nelly\nformat: commander\n"
        "color_identity: [R]\nstatus: built\n---\n",
    )
    _write(deck_dir / "mainboard.md", GOOD_BOARD)

    monkeypatch.chdir(tmp_path)
    decks = scan_repository(Path("decks"))
    assert any(d.path == "decks/commander/nelly" and d.valid for d in decks)


def test_scan_repository_accepts_symlinked_root_input(tmp_path):
    real_root = tmp_path / "real-decks"
    deck_dir = real_root / "commander" / "nelly"
    _write(
        deck_dir / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Nelly\nformat: commander\n"
        "color_identity: [R]\nstatus: built\n---\n",
    )
    _write(deck_dir / "mainboard.md", GOOD_BOARD)

    symlink_root = tmp_path / "decks-link"
    try:
        os.symlink(real_root, symlink_root)
    except OSError:
        return  # symlinks unsupported here

    decks = scan_repository(symlink_root)
    assert any(d.path == "decks/commander/nelly" and d.valid for d in decks)


def test_scan_repository_reads_resolved_path_not_symlink_after_swap(tmp_path):
    """Check/use: after containment check, the resolved target must be read,
    not the original symlink path -- so a swap after resolution still reads
    whatever the symlink currently (validly) points to, never escaped data."""

    decks_root = tmp_path / "decks"
    deck_dir = decks_root / "commander" / "swap-deck"
    deck_dir.mkdir(parents=True)

    real_a = decks_root / "real-a.md"
    _write(
        real_a,
        "---\nschema: hermes-mtg/deck/v1\nname: RealA\nformat: commander\n"
        "color_identity: [R]\nstatus: built\n---\n",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside / "escape.md", "escaped content should never be read")

    symlink_path = deck_dir / "README.md"
    try:
        os.symlink(real_a, symlink_path)
    except OSError:
        return

    decks = scan_repository(decks_root)
    match = next((d for d in decks if d.path == "decks/commander/swap-deck"), None)
    assert match is not None
    assert match.name == "RealA"


def test_compute_revision_only_includes_relevant_paths(tmp_path):
    decks_root = tmp_path / "decks"
    _write(
        decks_root / "commander" / "nelly" / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Nelly\n---\n",
    )
    before = compute_revision(decks_root)

    # Arbitrary nested markdown deeper than deck dir must not affect revision.
    _write(decks_root / "commander" / "nelly" / "notes" / "deep.md", "irrelevant")
    after = compute_revision(decks_root)
    assert before == after


def test_compute_revision_prunes_large_excluded_cache_and_images_tree(tmp_path):
    decks_root = tmp_path / "decks"
    _write(
        decks_root / "commander" / "nelly" / "README.md",
        "---\nschema: hermes-mtg/deck/v1\nname: Nelly\n---\n",
    )
    before = compute_revision(decks_root)

    for i in range(200):
        _write(decks_root / "cache" / f"c{i}" / "x.md", "ignored" * 50)
        _write(decks_root / "commander" / "nelly" / "images" / f"i{i}.md", "ignored" * 50)
        _write(decks_root / "research" / f"r{i}.md", "ignored" * 50)

    after = compute_revision(decks_root)
    assert before == after
