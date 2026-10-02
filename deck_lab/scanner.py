"""Repository scanner and revision model (t_eb91eeab, corrected t_8bef6d29).

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
    ValidationError,
)

README_NAME = "README.md"

# Directories excluded from both board discovery and the revision fingerprint.
EXCLUDED_DIR_NAMES = frozenset({"cache", "images", "research", ".git"})


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


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _frontmatter_field_line(text: str, key: str) -> Optional[int]:
    """Best-effort 1-indexed line number of `key:` within the leading
    frontmatter block of `text`. Returns None if not found (e.g. missing
    frontmatter, or the field is absent)."""

    if not text.startswith("---\n"):
        return None
    lines = text.splitlines()
    for idx, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            break
        if line.split(":", 1)[0].strip() == key:
            return idx
    return None


def _is_strict_int(value: object) -> bool:
    """True for a real int, excluding bool (bool is an int subclass)."""

    return isinstance(value, int) and not isinstance(value, bool)


def _board_diagnostics(path: Path, rel_path: str, frontmatter: Optional[dict]) -> list[ValidationError]:
    """Validate strict board frontmatter. Returns a list of diagnostics; an
    empty list means the board is valid."""

    if frontmatter is None:
        return [
            ValidationError(
                code="BOARD_FRONTMATTER_MISSING",
                message="Board markdown has no recognizable frontmatter block.",
                path=rel_path,
            )
        ]
    diagnostics: list[ValidationError] = []
    if frontmatter.get("schema") != BOARD_SCHEMA_V1:
        diagnostics.append(
            ValidationError(
                code="BOARD_SCHEMA_UNSUPPORTED",
                message=f"Board schema must be {BOARD_SCHEMA_V1!r}.",
                path=rel_path,
            )
        )
        return diagnostics
    if not _is_nonempty_str(frontmatter.get("name")):
        diagnostics.append(
            ValidationError(
                code="BOARD_FRONTMATTER_INVALID",
                message="Board frontmatter 'name' must be a non-empty string.",
                path=rel_path,
            )
        )
    if frontmatter.get("kind") not in BOARD_KINDS:
        diagnostics.append(
            ValidationError(
                code="BOARD_KIND_INVALID",
                message=f"Board 'kind' must be one of {BOARD_KINDS!r}.",
                path=rel_path,
            )
        )
    if not _is_strict_int(frontmatter.get("order")):
        diagnostics.append(
            ValidationError(
                code="BOARD_FRONTMATTER_INVALID",
                message="Board frontmatter 'order' must be an integer (not a boolean).",
                path=rel_path,
            )
        )
    return diagnostics


def _is_board_markdown(path: Path, rel_path: str) -> tuple[Optional[dict], list[ValidationError]]:
    """Return (frontmatter, diagnostics) for a board markdown candidate.
    frontmatter is the parsed dict only when valid (diagnostics empty);
    on any validation failure frontmatter is None and diagnostics holds the
    board file's own structured errors (path/line of the board file itself)."""

    try:
        text = path.read_text()
    except OSError:
        return None, [
            ValidationError(
                code="BOARD_FRONTMATTER_MISSING",
                message="Board markdown could not be read.",
                path=rel_path,
            )
        ]
    frontmatter, _ = _split_frontmatter(text)
    diagnostics = _board_diagnostics(path, rel_path, frontmatter)
    if diagnostics:
        diagnostics = [
            ValidationError(
                code=d.code,
                message=d.message,
                path=d.path,
                severity=d.severity,
                line=_frontmatter_field_line(
                    text,
                    {
                        "BOARD_SCHEMA_UNSUPPORTED": "schema",
                        "BOARD_KIND_INVALID": "kind",
                    }.get(d.code, "name" if "name" in d.message else "order"),
                ),
                context=d.context,
            )
            for d in diagnostics
        ]
        return None, diagnostics
    return frontmatter, []


def _deck_frontmatter_diagnostics(
    rel_path: str,
    frontmatter: Optional[dict],
    raw_text: str = "",
    field_path: Optional[str] = None,
) -> tuple[list[ValidationError], dict]:
    """Validate deck frontmatter. Returns (diagnostics, sanitized_fields) where
    sanitized_fields always holds values safe to pass into DeckSummary (never
    raises from DeckSummary construction, even when the source is invalid)."""

    sanitized = {
        "name": "",
        "format": "unknown",
        "color_identity": (),
        "status": "unknown",
    }

    err_path = field_path or rel_path

    if frontmatter is None:
        return (
            [
                ValidationError(
                    code="DECK_FRONTMATTER_MISSING",
                    message="Deck README has no recognizable frontmatter block.",
                    path=err_path,
                    line=1,
                )
            ],
            sanitized,
        )

    if frontmatter.get("schema") != DECK_SCHEMA_V1:
        return (
            [
                ValidationError(
                    code="DECK_SCHEMA_UNSUPPORTED",
                    message=f"Deck schema must be {DECK_SCHEMA_V1!r}.",
                    path=err_path,
                    line=_frontmatter_field_line(raw_text, "schema"),
                )
            ],
            sanitized,
        )

    diagnostics: list[ValidationError] = []

    name = frontmatter.get("name")
    if _is_nonempty_str(name):
        sanitized["name"] = name
    else:
        diagnostics.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message="Deck frontmatter 'name' must be a non-empty string.",
                path=err_path,
                line=_frontmatter_field_line(raw_text, "name"),
            )
        )

    fmt = frontmatter.get("format")
    if _is_nonempty_str(fmt) and fmt == fmt.lower():  # type: ignore[union-attr]
        sanitized["format"] = fmt
    else:
        diagnostics.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message="Deck frontmatter 'format' must be a non-empty lowercase string.",
                path=err_path,
                line=_frontmatter_field_line(raw_text, "format"),
            )
        )

    status = frontmatter.get("status")
    if _is_nonempty_str(status):
        sanitized["status"] = status
    else:
        diagnostics.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message="Deck frontmatter 'status' must be a non-empty string.",
                path=err_path,
                line=_frontmatter_field_line(raw_text, "status"),
            )
        )

    color_identity = frontmatter.get("color_identity")
    if not isinstance(color_identity, list):
        diagnostics.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message="Deck frontmatter 'color_identity' must be a list.",
                path=err_path,
                line=_frontmatter_field_line(raw_text, "color_identity"),
            )
        )
    elif any(c not in COLOR_IDENTITY_VALUES for c in color_identity):
        diagnostics.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message=f"Deck 'color_identity' members must be one of {sorted(COLOR_IDENTITY_VALUES)!r}.",
                path=err_path,
                line=_frontmatter_field_line(raw_text, "color_identity"),
            )
        )
    elif len(set(color_identity)) != len(color_identity):
        diagnostics.append(
            ValidationError(
                code="DECK_FRONTMATTER_INVALID",
                message="Deck 'color_identity' must not contain duplicate colors.",
                path=err_path,
                line=_frontmatter_field_line(raw_text, "color_identity"),
            )
        )
    else:
        sanitized["color_identity"] = tuple(color_identity)

    return diagnostics, sanitized


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
        if format_dir.name in EXCLUDED_DIR_NAMES:
            continue
        format_resolved = _resolve_within(root_resolved, format_dir)
        if format_resolved is None:
            continue
        format_name = format_resolved.name

        for deck_dir in sorted(p for p in format_resolved.iterdir() if p.is_dir()):
            if deck_dir.name in EXCLUDED_DIR_NAMES:
                continue
            deck_resolved = _resolve_within(root_resolved, deck_dir)
            if deck_resolved is None:
                continue  # traversal or symlink escape -- skip silently

            readme_path = deck_resolved / README_NAME
            if not readme_path.is_file():
                continue
            readme_resolved = _resolve_within(root_resolved, readme_path)
            if readme_resolved is None:
                continue

            rel_path = f"decks/{deck_resolved.relative_to(root_resolved).as_posix()}"
            readme_rel_path = f"{rel_path}/{README_NAME}"

            try:
                readme_text = readme_resolved.read_text()
            except OSError:
                readme_text = ""
            deck_frontmatter, _ = _split_frontmatter(readme_text)
            deck_diagnostics, sanitized = _deck_frontmatter_diagnostics(
                rel_path, deck_frontmatter, readme_text, readme_rel_path
            )

            boards: list[BoardSummary] = []
            board_file_errors: list[ValidationError] = []
            for candidate in sorted(deck_resolved.glob("*.md")):
                if candidate.name == README_NAME:
                    continue
                candidate_resolved = _resolve_within(root_resolved, candidate)
                if candidate_resolved is None:
                    continue
                try:
                    candidate_text = candidate_resolved.read_text()
                except OSError:
                    candidate_text = ""
                candidate_fm, _ = _split_frontmatter(candidate_text)
                if candidate_fm is None or not str(candidate_fm.get("schema", "")).startswith(
                    "hermes-mtg/board/"
                ):
                    # Not a board candidate at all (e.g. piloting.md / plain notes).
                    continue
                board_rel = f"decks/{candidate_resolved.relative_to(root_resolved).as_posix()}"
                board_fm, board_diag = _is_board_markdown(candidate_resolved, board_rel)
                if board_fm is None:
                    board_file_errors.extend(board_diag)
                    continue
                boards.append(
                    BoardSummary(
                        path=board_rel,
                        name=board_fm.get("name", candidate_resolved.stem),
                        kind=board_fm["kind"],
                        order=board_fm["order"],
                        valid=True,
                    )
                )

            deck_diagnostics_all = list(deck_diagnostics)
            if board_file_errors:
                deck_diagnostics_all.extend(board_file_errors)
            elif not boards:
                deck_diagnostics_all.append(
                    ValidationError(
                        code="BOARD_FRONTMATTER_MISSING",
                        message="Deck has no recognizable board markdown.",
                        path=rel_path,
                    )
                )

            valid = not deck_diagnostics_all

            summaries.append(
                DeckSummary(
                    repository_id=str(root_resolved),
                    path=rel_path,
                    name=sanitized["name"] or deck_resolved.name,
                    format=sanitized["format"] if sanitized["format"] != "unknown" else format_name,
                    color_identity=sanitized["color_identity"],
                    status=sanitized["status"],
                    valid=valid,
                    errors=tuple(deck_diagnostics_all),
                    boards=tuple(boards),
                )
            )

    return summaries


def _iter_revision_files(root_resolved: Path):
    """Yield README/board markdown paths directly under
    `<root>/<format>/<deck>/`, pruned: never descends into excluded
    directories (cache/images/research/.git) nor any nested subdirectory
    beyond the deck directory itself, and never parses file content."""

    for format_dir in sorted(p for p in root_resolved.iterdir() if p.is_dir()):
        if format_dir.name in EXCLUDED_DIR_NAMES:
            continue
        format_resolved = _resolve_within(root_resolved, format_dir)
        if format_resolved is None:
            continue

        for deck_dir in sorted(p for p in format_resolved.iterdir() if p.is_dir()):
            if deck_dir.name in EXCLUDED_DIR_NAMES:
                continue
            deck_resolved = _resolve_within(root_resolved, deck_dir)
            if deck_resolved is None:
                continue

            for candidate in sorted(deck_resolved.glob("*.md")):
                candidate_resolved = _resolve_within(root_resolved, candidate)
                if candidate_resolved is None:
                    continue
                yield candidate_resolved


def compute_revision(decks_root: Path) -> str:
    """Cheap revision fingerprint: hashes (relative path, mtime_ns, size) for
    every relevant README/board markdown file. Never reads file content or
    parses cards, so this stays sub-two-second even on large repositories."""

    decks_root = Path(decks_root)
    try:
        root_resolved = decks_root.resolve(strict=False)
    except OSError:
        return hashlib.sha256().hexdigest()
    if not root_resolved.is_dir():
        return hashlib.sha256().hexdigest()

    digest = hashlib.sha256()
    for path in _iter_revision_files(root_resolved):
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
