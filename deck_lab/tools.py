"""Thin Hermes tool wrappers over `deck_lab.service.DeckLabService`
(card t_b5b4148d).

Every handler: resolves a `DeckLabService` for the declared `workspace_root`
(default: the process cwd, matching Hermes's focused-cwd convention), calls
exactly one service method, and serializes the result (or the service's own
`DeckLabServiceError`) to a bounded JSON string. No path/hash/validation
policy is re-implemented here -- see `deck_lab/service.py` for that single
orchestration boundary.

`deck_list`, `deck_get`, `deck_validate`, `deck_export` are read-only in V1.
`deck_import` defaults to a dry run; applying a write requires
`expected_hash` (atomic replace, explicit `overwrite=True` for an existing
target, and the service aborts on a concurrent modification detected
immediately before the write).
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

from deck_lab.service import DeckLabService, DeckLabServiceError

# Bound on any single tool's JSON response so a huge repository/board can
# never flood model context; this mirrors the service's own list/text bounds
# but is enforced again here as the final wrapper-level guarantee.
MAX_RESPONSE_BYTES = 200_000


def _bounded(data: dict) -> str:
    encoded = json.dumps(data, ensure_ascii=False)
    if len(encoded.encode("utf-8")) <= MAX_RESPONSE_BYTES:
        return encoded
    # Truncate defensively rather than ever emit a half-written JSON blob:
    # report the overflow as a stable, machine-readable error instead.
    return json.dumps(
        {
            "error": "Tool response exceeds the bounded output size",
            "code": "RESPONSE_TOO_LARGE",
            "bytes": len(encoded.encode("utf-8")),
            "limit": MAX_RESPONSE_BYTES,
        },
        ensure_ascii=False,
    )


def _service_for(args: dict) -> DeckLabService:
    workspace_root = args.get("workspace_root") or os.getcwd()
    return DeckLabService(workspace_root)


def _run(args: dict, call: Callable[[DeckLabService], dict]) -> str:
    try:
        service = _service_for(args)
        result = call(service)
    except DeckLabServiceError as exc:
        payload = exc.to_dict()["error"]
        return _bounded({"error": payload["message"], **payload})
    except Exception as exc:  # defensive: never let a raw traceback leak out
        return _bounded({"error": str(exc), "code": "INTERNAL_ERROR"})
    return _bounded(result)


# ---------------------------------------------------------------------
# deck_list (read-only)
# ---------------------------------------------------------------------

DECK_LIST_SCHEMA = {
    "name": "deck_list",
    "description": "List decks discovered in the Deck Lab repository, each with validity and diagnostics.",
    "parameters": {
        "type": "object",
        "properties": {
            "workspace_root": {"type": "string", "description": "Repository root containing 'decks/'. Defaults to the current working directory."},
            "limit": {"type": "integer", "description": "Maximum number of decks to return (bounded)."},
        },
    },
}


def handle_deck_list(args: dict, **_kw) -> str:
    kwargs: dict[str, Any] = {}
    if args.get("limit") is not None:
        kwargs["limit"] = args["limit"]
    return _run(args, lambda s: s.list_decks(**kwargs))


# ---------------------------------------------------------------------
# deck_get (read-only)
# ---------------------------------------------------------------------

DECK_GET_SCHEMA = {
    "name": "deck_get",
    "description": "Get one deck's selected board: cards, zone/category counts, and board errors with source path/line.",
    "parameters": {
        "type": "object",
        "properties": {
            "workspace_root": {"type": "string"},
            "deck_path": {"type": "string", "description": "Repository-relative deck path, e.g. 'decks/commander/nelly-borca'."},
            "board_path": {"type": "string", "description": "Optional specific board path; defaults to the deck's lowest-order board."},
            "resolve_remote": {"type": "boolean", "description": "Enrich cards with cached/live Scryfall projections. Default true."},
        },
        "required": ["deck_path"],
    },
}


def handle_deck_get(args: dict, **_kw) -> str:
    deck_path = args.get("deck_path")
    if not deck_path:
        return _bounded({"error": "deck_path is required", "code": "INVALID_INPUT"})
    kwargs: dict[str, Any] = {"board_path": args.get("board_path")}
    if "resolve_remote" in args:
        kwargs["resolve_remote"] = bool(args["resolve_remote"])
    return _run(args, lambda s: s.get_deck(deck_path, **kwargs))


# ---------------------------------------------------------------------
# deck_validate (read-only)
# ---------------------------------------------------------------------

DECK_VALIDATE_SCHEMA = {
    "name": "deck_validate",
    "description": "Validate a repository-relative target ('decks', a deck directory, or a single board/README file); returns errors with source path/line.",
    "parameters": {
        "type": "object",
        "properties": {
            "workspace_root": {"type": "string"},
            "target_path": {"type": "string", "description": "Repository-relative path to validate."},
            "resolve_remote": {"type": "boolean", "description": "Also resolve cards against Scryfall. Default false."},
        },
        "required": ["target_path"],
    },
}


def handle_deck_validate(args: dict, **_kw) -> str:
    target_path = args.get("target_path")
    if not target_path:
        return _bounded({"error": "target_path is required", "code": "INVALID_INPUT"})
    resolve_remote = bool(args.get("resolve_remote", False))
    return _run(args, lambda s: s.validate(target_path, resolve_remote=resolve_remote))


# ---------------------------------------------------------------------
# deck_export (read-only)
# ---------------------------------------------------------------------

DECK_EXPORT_SCHEMA = {
    "name": "deck_export",
    "description": "Export a deck (or one of its boards) as ManaBox/Arena or Moxfield-bulk interchange text, with any representability losses reported explicitly.",
    "parameters": {
        "type": "object",
        "properties": {
            "workspace_root": {"type": "string"},
            "deck_path": {"type": "string"},
            "board_path": {"type": "string"},
            "dialect": {"type": "string", "enum": ["manabox", "arena", "moxfield-bulk"]},
        },
        "required": ["deck_path", "dialect"],
    },
}


def handle_deck_export(args: dict, **_kw) -> str:
    deck_path = args.get("deck_path")
    dialect = args.get("dialect")
    if not deck_path or not dialect:
        return _bounded({"error": "deck_path and dialect are required", "code": "INVALID_INPUT"})
    board_path = args.get("board_path")
    return _run(args, lambda s: s.export_deck(deck_path, board_path=board_path, dialect=dialect))


# ---------------------------------------------------------------------
# deck_import (write; defaults to dry-run)
# ---------------------------------------------------------------------

DECK_IMPORT_SCHEMA = {
    "name": "deck_import",
    "description": (
        "Import ManaBox/Arena or Moxfield-bulk interchange text into one or more board "
        "Markdown files. Defaults to a dry run (renders + validates, no write). Applying "
        "a write (apply=true) requires expected_hash for every existing target, refuses "
        "to overwrite an existing target unless overwrite=true, replaces files atomically, "
        "and aborts without writing if a target changed concurrently."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "workspace_root": {"type": "string"},
            "dialect": {"type": "string", "enum": ["manabox", "arena", "moxfield-bulk"]},
            "target_deck_path": {"type": "string", "description": "Repository-relative deck directory to import into."},
            "target_board_path": {"type": "string", "description": "Optional explicit single board target path."},
            "text": {"type": "string", "description": "Pasted interchange text. Exactly one of text/source_file is required."},
            "source_file": {"type": "string", "description": "Repository-relative path to read interchange text from."},
            "apply": {"type": "boolean", "description": "Write the rendered board(s) to disk. Default false (dry run)."},
            "expected_hash": {
                "description": "sha256 hex of each target's current content (string for a single target, or {path: hash} for multiple); required to apply onto an existing target, null to create a new one.",
            },
            "overwrite": {"type": "boolean", "description": "Required true to apply onto an already-existing target. Default false."},
        },
        "required": ["dialect", "target_deck_path"],
    },
}


def handle_deck_import(args: dict, **_kw) -> str:
    dialect = args.get("dialect")
    target_deck_path = args.get("target_deck_path")
    if not dialect or not target_deck_path:
        return _bounded({"error": "dialect and target_deck_path are required", "code": "INVALID_INPUT"})

    kwargs: dict[str, Any] = dict(
        dialect=dialect,
        target_deck_path=target_deck_path,
        target_board_path=args.get("target_board_path"),
        text=args.get("text"),
        source_file=args.get("source_file"),
        apply=bool(args.get("apply", False)),
        expected_hash=args.get("expected_hash"),
        overwrite=bool(args.get("overwrite", False)),
    )
    return _run(args, lambda s: s.import_deck(**kwargs))


# ---------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------

_TOOLS = (
    ("deck_list", DECK_LIST_SCHEMA, handle_deck_list),
    ("deck_get", DECK_GET_SCHEMA, handle_deck_get),
    ("deck_validate", DECK_VALIDATE_SCHEMA, handle_deck_validate),
    ("deck_import", DECK_IMPORT_SCHEMA, handle_deck_import),
    ("deck_export", DECK_EXPORT_SCHEMA, handle_deck_export),
)


def register_tools(ctx) -> None:
    """Register exactly the five tools declared in `plugin.yaml`'s `tools:` list."""

    for name, schema, handler in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="deck_lab",
            schema=schema,
            handler=handler,
            description=schema["description"],
        )
