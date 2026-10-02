"""Shared Deck Lab domain service (card t_e08aa8a4).

A single orchestration boundary over the independently-developed parser,
scanner, Scryfall resolver, and ManaBox/Arena/Moxfield adapters. Both the
(future) FastAPI routes and Hermes tool wrappers call this exact class --
no path/hash/error policy may be re-invented downstream.

This module never reimplements parser/scanner/Scryfall/adapter grammar; it
only resolves paths, serializes dataclasses, and wires existing lanes
together.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Optional

from deck_lab import parser as _parser
from deck_lab import scanner as _scanner
from deck_lab import scryfall as _scryfall
from deck_lab.adapters import manabox_arena as _manabox_arena
from deck_lab.adapters import moxfield_bulk as _moxfield_bulk
from deck_lab.models import SERVICE_SCHEMA_V1

SUPPORTED_IMPORT_DIALECTS = ("manabox", "arena", "moxfield-bulk")
SUPPORTED_EXPORT_DIALECTS = ("manabox", "arena", "moxfield-bulk")

# Input/output bounds -- explicit errors instead of silent truncation.
MAX_PASTED_TEXT_BYTES = 2_000_000
MAX_LIST_LIMIT = 1000
DEFAULT_LIST_LIMIT = 200

_ZONE_TO_MOXFIELD_BOARD = {
    "Commander": "commander",
    "Deck": "mainboard",
    "Sideboard": "sideboard",
    "Maybeboard": "maybeboard",
}
_MOXFIELD_BOARD_TO_ZONE = {v: k for k, v in _ZONE_TO_MOXFIELD_BOARD.items()}


class DeckLabServiceError(Exception):
    """Stable, machine-readable error so route/tool wrappers never invent
    their own error policy.

    `status` is an HTTP-neutral integer (400/404/409/...) and `category`
    is a coarse bucket (`client`, `not_found`, `conflict`, `server`) that a
    thin wrapper can map onto its own transport without inspecting `code`.
    """

    def __init__(self, code: str, message: str, *, path: Optional[str] = None, status: int = 400, category: str = "client"):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.status = status
        self.category = category

    def to_dict(self) -> dict:
        return {
            "schema": SERVICE_SCHEMA_V1,
            "error": {
                "code": self.code,
                "message": self.message,
                "path": self.path,
                "status": self.status,
                "category": self.category,
            },
        }


def _err(code: str, message: str, *, path: Optional[str] = None, status: int = 400, category: str = "client") -> DeckLabServiceError:
    return DeckLabServiceError(code, message, path=path, status=status, category=category)


def _serialize(value):
    """Serialize dataclasses (and nested dataclasses/tuples) into plain
    JSON-compatible structures, without losing any field (notably
    path/line diagnostics on ValidationError/SourceLocation)."""

    if is_dataclass(value) and not isinstance(value, type):
        return {k: _serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


class DeckLabService:
    """The single orchestration boundary for Deck Lab.

    `workspace_root` is the focused Hermes cwd; `<workspace_root>/decks` is
    derived and resolved once, and no read/write path may ever escape it.
    """

    def __init__(self, workspace_root, *, cache_path=None, http_client=None):
        self.workspace_root = Path(workspace_root)
        self.decks_root = (self.workspace_root / "decks").resolve(strict=False)
        self.cache_path = cache_path
        self.http_client = http_client
        self._cache = _scryfall.ScryfallCache(cache_path) if cache_path else None

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------

    def _resolve_repo_path(self, rel_path: str, *, must_exist: bool = False) -> Path:
        """Resolve a repository-relative path (must begin with `decks/`)
        to an absolute path guaranteed to stay within the resolved decks
        root. Raises `PATH_OUTSIDE_DECKS_ROOT` before any read/write on
        any violation: absolute paths, `..`, a path that doesn't start
        with `decks/`, or symlink escape."""

        if not isinstance(rel_path, str) or not rel_path.startswith("decks/") and rel_path != "decks":
            raise _err(
                "PATH_OUTSIDE_DECKS_ROOT",
                f"Path must be repository-relative and begin with 'decks/': {rel_path!r}",
                path=rel_path if isinstance(rel_path, str) else None,
                status=400,
            )
        if Path(rel_path).is_absolute():
            raise _err("PATH_OUTSIDE_DECKS_ROOT", f"Absolute paths are not permitted: {rel_path!r}", path=rel_path)

        suffix = rel_path[len("decks"):].lstrip("/")
        candidate = self.decks_root / suffix if suffix else self.decks_root

        try:
            resolved = candidate.resolve(strict=must_exist)
        except OSError as exc:
            raise _err("PATH_OUTSIDE_DECKS_ROOT", f"Path could not be resolved: {rel_path!r}", path=rel_path) from exc

        try:
            resolved.relative_to(self.decks_root)
        except ValueError:
            raise _err(
                "PATH_OUTSIDE_DECKS_ROOT",
                f"Path escapes the resolved decks root: {rel_path!r}",
                path=rel_path,
            ) from None

        if must_exist and not resolved.exists():
            raise _err("PATH_OUTSIDE_DECKS_ROOT", f"Path does not exist: {rel_path!r}", path=rel_path, status=404, category="not_found")

        return resolved

    def _repo_rel(self, absolute: Path) -> str:
        return f"decks/{absolute.relative_to(self.decks_root).as_posix()}" if absolute != self.decks_root else "decks"

    # ------------------------------------------------------------------
    # revision / list_decks
    # ------------------------------------------------------------------

    def revision(self) -> dict:
        rev = _scanner.compute_revision(self.decks_root)
        return {
            "schema": SERVICE_SCHEMA_V1,
            "repository_id": str(self.decks_root),
            "revision": rev,
        }

    def list_decks(self, *, limit: int = DEFAULT_LIST_LIMIT) -> dict:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise _err("INVALID_INPUT", f"limit must be a positive integer, got {limit!r}")
        if limit > MAX_LIST_LIMIT:
            raise _err("LIMIT_EXCEEDED", f"limit must be <= {MAX_LIST_LIMIT}, got {limit}")

        decks = _scanner.scan_repository(self.decks_root)
        truncated = len(decks) > limit
        bounded = decks[:limit]

        return {
            "schema": SERVICE_SCHEMA_V1,
            "decks": [_serialize(d) for d in bounded],
            "total": len(decks),
            "truncated": truncated,
        }

    # ------------------------------------------------------------------
    # get_deck / validate
    # ------------------------------------------------------------------

    def _find_deck_summary(self, deck_path: str):
        self._resolve_repo_path(deck_path)  # path-safety only; the deck may not exist yet
        decks = _scanner.scan_repository(self.decks_root)
        for deck in decks:
            if deck.path == deck_path:
                return deck
        raise _err("DECK_NOT_FOUND", f"No deck discovered at {deck_path!r}", path=deck_path, status=404, category="not_found")

    def _select_board(self, deck_summary, board_path: Optional[str]):
        if board_path is not None:
            self._resolve_repo_path(board_path)  # path-safety before semantic lookup
            for board in deck_summary.boards:
                if board.path == board_path:
                    return board
            raise _err("BOARD_NOT_FOUND", f"No board at {board_path!r} for deck {deck_summary.path!r}", path=board_path, status=404, category="not_found")
        if not deck_summary.boards:
            return None
        return sorted(deck_summary.boards, key=lambda b: b.order)[0]

    def _resolve_remote_projections(self, identifiers: list) -> dict:
        """Batched Scryfall enrichment/status pass shared by `get_deck`
        and `validate(resolve_remote=True)`.

        When a real `http_client` is declared, performs the normal
        batched network resolution. With no declared `http_client`, this
        is an intentional offline/cache-only fallback: cached projections
        (fresh or stale) are served and anything absent resolves to
        `None` (unresolved) -- never a raw transport/attribute crash.
        """

        if self.http_client is None:
            return _scryfall.resolve_from_cache(identifiers, self._cache)
        return _scryfall.resolve_collection(identifiers, http_client=self.http_client, cache=self._cache)

    def _enrich_cards_with_remote(self, cards, *, board_path: str, resolve_remote: bool):
        """Shared batched Scryfall enrichment/status pass used by both
        `get_deck` and `validate(resolve_remote=True)`.

        Returns `(cards_serialized, remote_resolved, remote_unresolved_count,
        remote_warnings)`. `remote_warnings` are `REMOTE_CARD_UNRESOLVED`
        diagnostics carrying source name/path/line, kept separate from
        syntactic board validity -- an unresolved remote lookup never makes
        otherwise-valid Markdown invalid.
        """

        if not resolve_remote or not cards:
            return [_serialize(c) for c in cards], False, 0, []

        identifiers = [_scryfall.identifier_for_card(c.set_code, c.collector_number, c.name) for c in cards]
        projections = self._resolve_remote_projections(identifiers)

        cards_serialized = []
        remote_unresolved_count = 0
        remote_warnings = []
        for card in cards:
            key = _scryfall.identifier_key(
                _scryfall.identifier_for_card(card.set_code, card.collector_number, card.name)
            )
            projection = projections.get(key)
            card_dict = _serialize(card)
            card_dict["scryfall"] = _serialize(projection) if projection is not None else None
            if projection is None:
                remote_unresolved_count += 1
                remote_warnings.append(
                    {
                        "code": "REMOTE_CARD_UNRESOLVED",
                        "severity": "warning",
                        "name": card.name,
                        "path": card.source.path if card.source is not None else board_path,
                        "line": card.source.line if card.source is not None else None,
                    }
                )
            cards_serialized.append(card_dict)
        return cards_serialized, True, remote_unresolved_count, remote_warnings

    def get_deck(self, deck_path, *, board_path=None, resolve_remote=True) -> dict:
        deck_summary = self._find_deck_summary(deck_path)
        board_summary = self._select_board(deck_summary, board_path)

        cards_serialized = []
        board_errors = []
        zone_counts: dict = {}
        category_counts: dict = {}
        total = 0
        commander_count = 0
        remote_resolved = False
        remote_unresolved_count = 0
        remote_warnings: list = []

        if board_summary is not None:
            board_abs = self._resolve_repo_path(board_summary.path, must_exist=True)
            board_text = board_abs.read_text()
            parse_result = _parser.parse_board(board_text, path=board_summary.path)
            board_errors = [_serialize(e) for e in parse_result.errors]
            zone_counts = parse_result.zone_counts
            category_counts = {" / ".join(k): v for k, v in parse_result.category_counts.items()}
            total = parse_result.card_count
            commander_count = parse_result.commander_count

            (
                cards_serialized,
                remote_resolved,
                remote_unresolved_count,
                remote_warnings,
            ) = self._enrich_cards_with_remote(
                list(parse_result.cards), board_path=board_summary.path, resolve_remote=resolve_remote
            )

        return {
            "schema": SERVICE_SCHEMA_V1,
            "deck": _serialize(deck_summary),
            "board": _serialize(board_summary) if board_summary is not None else None,
            "cards": cards_serialized,
            "zone_counts": zone_counts,
            "category_counts": category_counts,
            "total": total,
            "commander_count": commander_count,
            "board_errors": board_errors,
            "remote_resolved": remote_resolved,
            "remote_unresolved_count": remote_unresolved_count,
            "remote_warnings": remote_warnings,
        }

    def validate(self, target_path, *, resolve_remote=False) -> dict:
        resolved = self._resolve_repo_path(target_path, must_exist=True)
        rel = self._repo_rel(resolved)

        if rel == "decks":
            decks = _scanner.scan_repository(self.decks_root)
            valid = [d for d in decks if d.valid]
            invalid = [d for d in decks if not d.valid]
            remote_unresolved_count = 0
            remote_warnings: list = []
            if resolve_remote:
                for deck in decks:
                    for board in deck.boards:
                        board_abs = self._resolve_repo_path(board.path, must_exist=True)
                        parse_result = _parser.parse_board(board_abs.read_text(), path=board.path)
                        _, _, unresolved, warnings = self._enrich_cards_with_remote(
                            list(parse_result.cards), board_path=board.path, resolve_remote=True
                        )
                        remote_unresolved_count += unresolved
                        remote_warnings.extend(warnings)
            return {
                "schema": SERVICE_SCHEMA_V1,
                "target": rel,
                "valid": len(invalid) == 0,
                "deck_count": len(decks),
                "valid_count": len(valid),
                "invalid_count": len(invalid),
                "errors": [e for d in invalid for e in _serialize(d.errors)],
                "remote_resolved": resolve_remote,
                "remote_unresolved_count": remote_unresolved_count,
                "remote_warnings": remote_warnings,
            }

        if resolved.is_dir():
            deck_summary = self._find_deck_summary(rel)
            all_errors = list(deck_summary.errors)
            card_total = 0
            remote_unresolved_count = 0
            remote_warnings = []
            for board in deck_summary.boards:
                board_abs = self._resolve_repo_path(board.path, must_exist=True)
                parse_result = _parser.parse_board(board_abs.read_text(), path=board.path)
                all_errors.extend(parse_result.errors)
                card_total += parse_result.card_count
                if resolve_remote:
                    _, _, unresolved, warnings = self._enrich_cards_with_remote(
                        list(parse_result.cards), board_path=board.path, resolve_remote=True
                    )
                    remote_unresolved_count += unresolved
                    remote_warnings.extend(warnings)
            return {
                "schema": SERVICE_SCHEMA_V1,
                "target": rel,
                "valid": not any(e.severity == "error" for e in all_errors),
                "card_total": card_total,
                "errors": _serialize(all_errors),
                "remote_resolved": resolve_remote,
                "remote_unresolved_count": remote_unresolved_count,
                "remote_warnings": remote_warnings,
            }

        # Single board/README file.
        text = resolved.read_text()
        if resolved.name == "README.md":
            parse_result = _parser.parse_deck_readme(text, path=rel)
        else:
            parse_result = _parser.parse_board(text, path=rel)
        remote_resolved = False
        remote_unresolved_count = 0
        remote_warnings = []
        if resolve_remote:
            _, remote_resolved, remote_unresolved_count, remote_warnings = self._enrich_cards_with_remote(
                list(parse_result.cards), board_path=rel, resolve_remote=True
            )
        return {
            "schema": SERVICE_SCHEMA_V1,
            "target": rel,
            "valid": parse_result.valid,
            "card_total": parse_result.card_count,
            "errors": _serialize(parse_result.errors),
            "remote_resolved": remote_resolved,
            "remote_unresolved_count": remote_unresolved_count,
            "remote_warnings": remote_warnings,
        }

    # ------------------------------------------------------------------
    # import_deck
    # ------------------------------------------------------------------

    def _normalize_import_cards(self, dialect: str, text: str):
        """Returns `(documents, warnings)` where `documents` is a tuple of
        `manabox_arena.BoardDocument` (kind/markdown/parse_result), one per
        board kind actually present. Both dialects funnel through the
        public `manabox_arena.to_board_markdown` renderer/validator --
        this module never reimplements board-kind/zone/category rendering
        grammar itself.
        """

        if dialect in ("manabox", "arena"):
            result = _manabox_arena.import_text(text, dialect=dialect)
            return _manabox_arena.to_board_markdown(result), []

        if dialect == "moxfield-bulk":
            result = _moxfield_bulk.import_text(text)
            rows = [
                _manabox_arena.CardRow(
                    quantity=card.quantity,
                    name=card.name,
                    zone=_MOXFIELD_BOARD_TO_ZONE.get(card.board, "Deck"),
                    category=card.category or "Uncategorized",
                    set_code=card.set_code,
                    collector_number=card.collector_number,
                )
                for card in result.cards
            ]
            documents = _manabox_arena.to_board_markdown(_manabox_arena.ImportResult(cards=rows))
            return documents, list(result.warnings)

        raise _err("UNSUPPORTED_DIALECT", f"Unsupported import dialect: {dialect!r}")

    def import_deck(
        self,
        *,
        dialect,
        target_deck_path,
        target_board_path=None,
        text=None,
        source_file=None,
        apply=False,
        expected_hash=None,
        overwrite=False,
    ) -> dict:
        if dialect not in SUPPORTED_IMPORT_DIALECTS:
            raise _err("UNSUPPORTED_DIALECT", f"Unsupported import dialect: {dialect!r}")

        if (text is None) == (source_file is None):
            raise _err("INVALID_INPUT", "Exactly one of 'text' or 'source_file' must be provided")

        if source_file is not None:
            source_abs = self._resolve_repo_path(source_file, must_exist=True)
            text = source_abs.read_text()

        if len(text.encode("utf-8")) > MAX_PASTED_TEXT_BYTES:
            raise _err("TEXT_TOO_LARGE", f"Input text exceeds {MAX_PASTED_TEXT_BYTES} bytes")

        documents, warnings = self._normalize_import_cards(dialect, text)

        self._resolve_repo_path(target_deck_path)  # path-safety only; need not exist

        targets = []  # list of (rel_path, rendered_text, kind, parse_result)
        for document in documents:
            if target_board_path is not None and len(documents) == 1:
                target_rel = target_board_path
            else:
                target_rel = f"{target_deck_path}/{document.kind}.md"
            targets.append((target_rel, document.markdown, document.kind, document.parse_result))

        if not targets:
            raise _err("INVALID_INPUT", "No recognizable cards were parsed from the provided input")

        target_results = []
        current_hashes = {}
        for target_rel, rendered, kind, parse_result in targets:
            target_abs = self._resolve_repo_path(target_rel)
            current_bytes = target_abs.read_bytes() if target_abs.exists() else None
            current_hash = hashlib.sha256(current_bytes).hexdigest() if current_bytes is not None else None
            current_hashes[target_rel] = current_hash
            diff = ""
            if current_bytes is not None:
                diff = "".join(
                    difflib.unified_diff(
                        current_bytes.decode("utf-8", errors="replace").splitlines(keepends=True),
                        rendered.splitlines(keepends=True),
                        fromfile=target_rel,
                        tofile=target_rel,
                    )
                )
            target_results.append(
                {
                    "path": target_rel,
                    "rendered": rendered,
                    "diff": diff,
                    "current_hash": current_hash,
                    "errors": _serialize(parse_result.errors),
                    "valid": parse_result.valid,
                }
            )

        result = {
            "schema": SERVICE_SCHEMA_V1,
            "dialect": dialect,
            "dry_run": not apply,
            "targets": target_results,
            "warnings": warnings,
            "applied": False,
        }

        if not apply:
            return result

        invalid_targets = [tr["path"] for tr in target_results if not tr["valid"]]
        if invalid_targets:
            raise _err(
                "IMPORT_VALIDATION_FAILED",
                f"Rendered import is not valid board Markdown for: {', '.join(invalid_targets)}; "
                "apply is refused before any filesystem mutation",
                path=invalid_targets[0],
                status=400,
                category="client",
            )

        # --- apply path: validate every precondition before touching any file ---
        if isinstance(expected_hash, dict):
            expected_map = expected_hash
        elif len(target_results) == 1:
            expected_map = {target_results[0]["path"]: expected_hash}
        else:
            raise _err(
                "IMPORT_HASH_REQUIRED",
                "expected_hash must be a {path: hash} mapping when import produces multiple targets",
            )

        for tr in target_results:
            path = tr["path"]
            exp = expected_map.get(path)
            cur = current_hashes[path]
            if cur is None:
                if exp is not None or overwrite:
                    raise _err(
                        "IMPORT_HASH_REQUIRED",
                        f"Creating {path!r} requires expected_hash=None and overwrite=False",
                        path=path,
                        status=409,
                        category="conflict",
                    )
            else:
                if not overwrite:
                    raise _err(
                        "IMPORT_OVERWRITE_REQUIRED",
                        f"Target {path!r} already exists; overwrite=True is required",
                        path=path,
                        status=409,
                        category="conflict",
                    )
                if exp != cur:
                    raise _err(
                        "IMPORT_HASH_MISMATCH",
                        f"expected_hash for {path!r} does not match current content",
                        path=path,
                        status=409,
                        category="conflict",
                    )

        # Re-read/re-hash immediately before replacement to reject concurrent
        # modification between the precondition check above and the write.
        for tr in target_results:
            path = tr["path"]
            target_abs = self._resolve_repo_path(path)
            cur_bytes = target_abs.read_bytes() if target_abs.exists() else None
            cur_hash = hashlib.sha256(cur_bytes).hexdigest() if cur_bytes is not None else None
            if cur_hash != current_hashes[path]:
                raise _err(
                    "IMPORT_CONCURRENT_MODIFICATION",
                    f"Target {path!r} changed concurrently; aborting before any write",
                    path=path,
                    status=409,
                    category="conflict",
                )

        written = []
        try:
            for tr in target_results:
                path = tr["path"]
                target_abs = self._resolve_repo_path(path)
                target_abs.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(dir=str(target_abs.parent), prefix=".deck-lab-import-")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(tr["rendered"])
                        fh.flush()
                        os.fsync(fh.fileno())
                    os.replace(tmp_path, target_abs)
                    written.append(str(target_abs))
                except Exception:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    raise
        except Exception:
            raise

        result["applied"] = True
        return result

    # ------------------------------------------------------------------
    # export_deck
    # ------------------------------------------------------------------

    def export_deck(self, deck_path, *, board_path=None, dialect) -> dict:
        if dialect not in SUPPORTED_EXPORT_DIALECTS:
            raise _err("UNSUPPORTED_DIALECT", f"Unsupported export dialect: {dialect!r}")

        deck_summary = self._find_deck_summary(deck_path)
        boards = deck_summary.boards
        if board_path is not None:
            self._resolve_repo_path(board_path)  # path-safety before semantic lookup
            boards = [b for b in boards if b.path == board_path]
            if not boards:
                raise _err("BOARD_NOT_FOUND", f"No board at {board_path!r}", path=board_path, status=404, category="not_found")

        all_cards = []
        for board in boards:
            board_abs = self._resolve_repo_path(board.path, must_exist=True)
            parse_result = _parser.parse_board(board_abs.read_text(), path=board.path)
            all_cards.extend(parse_result.cards)

        losses = []
        if dialect in ("manabox", "arena"):
            rows = [
                _manabox_arena.CardRow(
                    quantity=c.quantity,
                    name=c.name,
                    zone=c.zone,
                    category=c.category_path[-1] if c.category_path else "Uncategorized",
                    set_code=c.set_code,
                    collector_number=c.collector_number,
                )
                for c in all_cards
            ]
            exported_text = _manabox_arena.export_text(
                _manabox_arena.ImportResult(cards=rows), dialect=dialect
            )
            categories = {c.category_path[-1] for c in all_cards if c.category_path}
            if categories:
                losses.append("categories are not representable in ManaBox/Arena plain text and will be lost")
        else:  # moxfield-bulk
            mox_cards = [
                _moxfield_bulk.Card(
                    quantity=c.quantity,
                    name=c.name,
                    board=_ZONE_TO_MOXFIELD_BOARD.get(c.zone, "mainboard"),
                    category=c.category_path[-1] if c.category_path else "Uncategorized",
                    set_code=c.set_code,
                    collector_number=c.collector_number,
                )
                for c in all_cards
            ]
            export_result = _moxfield_bulk.export_cards(mox_cards)
            exported_text = export_result.text
            losses.extend(export_result.losses)

        return {
            "schema": SERVICE_SCHEMA_V1,
            "dialect": dialect,
            "text": exported_text,
            "losses": losses,
        }

    # ------------------------------------------------------------------
    # cache_status
    # ------------------------------------------------------------------

    def cache_status(self) -> dict:
        if self._cache is None:
            return {
                "schema": SERVICE_SCHEMA_V1,
                "configured": False,
                "path": None,
                "entry_count": 0,
                "fresh_count": 0,
                "stale_count": 0,
            }

        now = time.time()
        entries = self._cache.entries()
        fresh = sum(1 for e in entries if self._cache.is_fresh(e, now))
        return {
            "schema": SERVICE_SCHEMA_V1,
            "configured": True,
            "path": str(self.cache_path),
            "entry_count": len(entries),
            "fresh_count": fresh,
            "stale_count": len(entries) - fresh,
        }
