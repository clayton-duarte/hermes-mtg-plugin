"""Repository scanner and revision model (t_eb91eeab).

Discovers deck repositories laid out as `<decks_root>/<format>/<deck>/README.md`,
classifies each deck as valid / invalid / missing-board, and provides a cheap
revision fingerprint (path + mtime + size only -- no decklist parsing) for the
desktop poller's two-second check.

This module never imports `deck_lab.parser`: board markdown is recognized by
its frontmatter only (schema/kind/order), never by parsing its decklist body.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import yaml

from deck_lab.models import (
    BOARD_KINDS,
    BOARD_SCHEMA_V1,
    DECK_SCHEMA_V1,
    COLOR_IDENTITY_VALUES,
    BoardSummary,
    DeckSummary,
)

README_NAME = "README.md"

# Directories excluded from both board discovery and the revision fingerprint.
EXCLUDED_DIR_NAMES = frozenset({"cache", "images", ".git"})


def _split_frontmatter(text: str) -> tuple[Optional[dict], str]:
    """Split a leading YAML frontmatter block from the remaining body.

    Returns (None, text) if there is no well-formed frontmatter block, so
    callers can treat the content as having no recognizable schema.
    """

    if not text.startswith("---\n"):
        return None, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None, text
    _, raw_fm, body = parts
    try:
        data = yaml.safe_load(raw_fm)
    except yaml.YAMLError:
        return None, body
    if not isinstance(data, dict):
        return None, body
    return data, body


def _resolve_within(root: Path, candidate: Path) -> Optional[Path]:
    """Resolve `candidate` and return it only if it stays within `root` after
    symlink/`..` resolution. Returns None on traversal or symlink escape."""

    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _is_board_markdown(path: Path) -> Optional[dict]:
    """Return the frontmatter dict if `path` is recognized as strict board
    schema markdown, else None. Reads only the file's frontmatter region by
    parsing the whole file but never touches the decklist parser -- no card
    rows are parsed here."""

    try:
        text = path.read_text()
    except OSError:
        return None
    frontmatter, _ = _split_frontmatter(text)
    if frontmatter is None:
        return None
    if frontmatter.get("schema") != BOARD_SCHEMA_V1:
        return None
    if frontmatter.get("kind") not in BOARD_KINDS:
        return None
    if not isinstance(frontmatter.get("order"), int):
        return None
    return frontmatter


def _deck_frontmatter_errors(frontmatter: Optional[dict]) -> list[str]:
    if frontmatter is None:
        return ["DECK_FRONTMATTER_MISSING"]
    if frontmatter.get("schema") != DECK_SCHEMA_V1:
        return ["DECK_SCHEMA_UNSUPPORTED"]
    errors = []
    for field in ("name", "format", "status"):
        if not frontmatter.get(field):
            errors.append("DECK_FRONTMATTER_INVALID")
            break
    color_identity = frontmatter.get("color_identity") or []
    if not isinstance(color_identity, list) or any(
        c not in COLOR_IDENTITY_VALUES for c in color_identity
    ):
        errors.append("DECK_FRONTMATTER_INVALID")
    return errors


def scan_repository(decks_root: Path) -> list[DeckSummary]:
    """Scan `<decks_root>/<format>/<deck>/README.md` only. Returns valid,
    invalid, and missing-board decks together. Rejects traversal and symlink
    escape after path resolution (such entries are skipped, not raised)."""

    decks_root = Path(decks_root)
    try:
        root_resolved = decks_root.resolve(strict=False)
    except OSError:
        return []
    if not root_resolved.is_dir():
        return []

    summaries: list[DeckSummary] = []

    for format_dir in sorted(p for p in root_resolved.iterdir() if p.is_dir()):
        if _resolve_within(root_resolved, format_dir) is None:
            continue
        format_name = format_dir.name

        for deck_dir in sorted(p for p in format_dir.iterdir() if p.is_dir()):
            if deck_dir.name in EXCLUDED_DIR_NAMES:
                continue
            deck_resolved = _resolve_within(root_resolved, deck_dir)
            if deck_resolved is None:
                continue  # traversal or symlink escape -- skip silently

            readme_path = deck_dir / README_NAME
            if not readme_path.is_file():
                continue
            if _resolve_within(root_resolved, readme_path) is None:
                continue

            rel_path = f"decks/{deck_dir.relative_to(decks_root).as_posix()}"

            try:
                readme_text = readme_path.read_text()
            except OSError:
                readme_text = ""
            deck_frontmatter, _ = _split_frontmatter(readme_text)
            deck_errors = _deck_frontmatter_errors(deck_frontmatter)

            boards: list[BoardSummary] = []
            for candidate in sorted(deck_dir.glob("*.md")):
                if candidate.name == README_NAME:
                    continue
                if _resolve_within(root_resolved, candidate) is None:
                    continue
                board_fm = _is_board_markdown(candidate)
                if board_fm is None:
                    continue
                board_rel = f"decks/{candidate.relative_to(decks_root).as_posix()}"
                boards.append(
                    BoardSummary(
                        path=board_rel,
                        name=board_fm.get("name", candidate.stem),
                        kind=board_fm["kind"],
                        order=board_fm["order"],
                        valid=True,
                    )
                )

            deck_errors_tuple = list(deck_errors)
            if not boards:
                deck_errors_tuple.append("BOARD_FRONTMATTER_MISSING")

            valid = not deck_errors_tuple

            summaries.append(
                DeckSummary(
                    repository_id=str(root_resolved),
                    path=rel_path,
                    name=(deck_frontmatter or {}).get("name", deck_dir.name),
                    format=(deck_frontmatter or {}).get("format", format_name),
                    color_identity=tuple((deck_frontmatter or {}).get("color_identity") or ()),
                    status=(deck_frontmatter or {}).get("status", "unknown"),
                    valid=valid,
                    errors=tuple(deck_errors_tuple),
                    boards=tuple(boards),
                )
            )

    return summaries


def _iter_revision_files(decks_root: Path):
    """Yield README/board markdown paths under decks_root, excluding
    cache/image directories, without parsing any decklist content."""

    decks_root = Path(decks_root)
    try:
        root_resolved = decks_root.resolve(strict=False)
    except OSError:
        return
    if not root_resolved.is_dir():
        return

    for path in sorted(root_resolved.rglob("*.md")):
        if any(part in EXCLUDED_DIR_NAMES for part in path.relative_to(root_resolved).parts):
            continue
        if _resolve_within(root_resolved, path) is None:
            continue
        yield path


def compute_revision(decks_root: Path) -> str:
    """Cheap revision fingerprint: hashes (relative path, mtime_ns, size) for
    every relevant README/board markdown file. Never reads file content or
    parses cards, so this stays sub-two-second even on large repositories."""

    decks_root = Path(decks_root)
    root_resolved = decks_root.resolve(strict=False) if decks_root.exists() else decks_root

    digest = hashlib.sha256()
    for path in _iter_revision_files(decks_root):
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(root_resolved).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))

    return digest.hexdigest()


def revision_cache_key(
    *, connection: str, profile: str, cwd: str, repository_id: str
) -> str:
    """Cache identity for the revision check: includes connection, profile,
    cwd, and repository context so unrelated repos/profiles never collide."""

    raw = "\x00".join([connection, profile, cwd, repository_id])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
