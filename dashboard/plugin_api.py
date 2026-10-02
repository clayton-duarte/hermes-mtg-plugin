"""Thin Deck Lab FastAPI routes (card t_ba1838d1).

Mounted by the Hermes dashboard loader, which imports plugin runtime panes
by FILE PATH (not as a normal package import) -- `importlib.util.
spec_from_file_location`. This module must therefore import cleanly with no
reliance on this directory being a package or being on `sys.path`: it uses
only absolute imports of the top-level `deck_lab` package (already
installed/importable in the Hermes process) and declares no package-relative
imports of its own.

Every route is a direct, unparsing wrapper over `deck_lab.service.
DeckLabService` (card t_e08aa8a4) -- the single orchestration boundary for
scanning, parsing, Scryfall resolution, import/export and path safety. No
parsing/validation/path-safety policy is duplicated here: a route's entire
job is (1) decode the request, (2) call the service, (3) translate a
`DeckLabServiceError` into the matching HTTP status with its `to_dict()`
body untouched, and (4) return the service's own response dict verbatim so
every response conforms exactly to `hermes-mtg/service/v1`.
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from deck_lab.service import DeckLabService, DeckLabServiceError

router = APIRouter()


def _workspace_root() -> Path:
    """The focused Hermes cwd, re-read per request.

    Reading `os.getcwd()` per-request (rather than caching it at import
    time) matters for the standalone-import test and for any host process
    that changes directory after loading this module once.
    """

    return Path(os.getcwd())


def _service() -> DeckLabService:
    return DeckLabService(_workspace_root())


def _error_response(exc: DeckLabServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.to_dict())


@router.get("/revision")
def get_revision():
    try:
        return _service().revision()
    except DeckLabServiceError as exc:
        return _error_response(exc)


@router.get("/decks")
def list_decks(limit: int = 200):
    try:
        return _service().list_decks(limit=limit)
    except DeckLabServiceError as exc:
        return _error_response(exc)


@router.get("/deck")
def get_deck(path: str, board_path: Optional[str] = None, resolve_remote: bool = True):
    try:
        return _service().get_deck(path, board_path=board_path, resolve_remote=resolve_remote)
    except DeckLabServiceError as exc:
        return _error_response(exc)


@router.get("/validate")
def validate(path: str, resolve_remote: bool = False):
    try:
        return _service().validate(path, resolve_remote=resolve_remote)
    except DeckLabServiceError as exc:
        return _error_response(exc)


@router.get("/scryfall/cache-status")
def cache_status():
    try:
        return _service().cache_status()
    except DeckLabServiceError as exc:
        return _error_response(exc)


class ImportBody(BaseModel):
    dialect: str
    target_deck_path: str
    target_board_path: Optional[str] = None
    text: Optional[str] = None
    source_file: Optional[str] = None
    apply: bool = False
    expected_hash: Optional[dict] = None
    overwrite: bool = False


@router.post("/import")
def import_deck(body: ImportBody):
    try:
        return _service().import_deck(
            dialect=body.dialect,
            target_deck_path=body.target_deck_path,
            target_board_path=body.target_board_path,
            text=body.text,
            source_file=body.source_file,
            apply=body.apply,
            expected_hash=body.expected_hash,
            overwrite=body.overwrite,
        )
    except DeckLabServiceError as exc:
        return _error_response(exc)


class ExportBody(BaseModel):
    deck_path: str
    board_path: Optional[str] = None
    dialect: str


@router.post("/export")
def export_deck(body: ExportBody):
    try:
        return _service().export_deck(body.deck_path, board_path=body.board_path, dialect=body.dialect)
    except DeckLabServiceError as exc:
        return _error_response(exc)


def router_app() -> FastAPI:
    """A standalone app wrapping `router`, used by tests and any standalone
    run of this module. The real dashboard loader mounts `router` directly
    onto its own app instead of calling this."""

    app = FastAPI()
    app.include_router(router)
    return app
