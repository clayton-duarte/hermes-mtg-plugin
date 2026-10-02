"""Shared Deck Lab runtime composition factory (card t_678aa3e7).

`dashboard/plugin_api.py` and `deck_lab/tools.py` both construct the real,
network-capable `DeckLabService` through `build_service(workspace_root)`
defined here -- the single place that wires a real synchronous Scryfall
HTTP transport and a persistent cache path under the active Hermes home.
Neither wrapper may duplicate this composition.

This module is intentionally NOT imported by `deck_lab/tools.py` at module
load time (only inside a handler, lazily) so the dependency-light plugin
admission probe (bare interpreter import of `__init__.py` registering the
five schemas) never needs `httpx` importable.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

CACHE_FILENAME = "scryfall_cache.json"

# A single shared httpx.Client is reused across requests in this long-lived
# plugin process instead of opening a new connection pool per call.
_client_lock = threading.Lock()
_shared_http_client = None


class HttpxScryfallTransport:
    """Adapts an `httpx.Client` to the `.post(url, json=..., headers=...)`
    contract `scryfall.resolve_collection` expects, normalizing httpx's
    timeout exception into the resolver's retryable `TimeoutError` contract
    instead of letting a raw `httpx.TimeoutException` escape as a 500."""

    def __init__(self, client):
        self._client = client

    def post(self, url, json=None, headers=None):
        import httpx

        try:
            return self._client.post(url, json=json, headers=headers)
        except httpx.TimeoutException as exc:
            raise TimeoutError(str(exc)) from exc


def _get_http_client():
    """Lazily construct (once) and reuse a single real `httpx.Client` for
    the life of this process. Imported lazily so the dependency-light
    plugin admission probe never needs `httpx` importable."""

    global _shared_http_client
    with _client_lock:
        if _shared_http_client is None:
            import httpx

            _shared_http_client = httpx.Client(timeout=10.0)
        return _shared_http_client


def _hermes_home() -> Path:
    """The active Hermes home: `$HERMES_HOME` when set, else a safe
    fallback under the real user home -- never under the focused deck
    repository (`workspace_root`)."""

    configured = os.environ.get("HERMES_HOME")
    if configured:
        return Path(configured)
    return Path.home() / ".hermes"


def runtime_cache_path() -> str:
    """One persistent cache path shared across focused workspaces (Scryfall
    projections are keyed by card identity, not by repository), living
    under the active Hermes home so it survives process restarts."""

    cache_dir = _hermes_home() / "plugins" / "deck-lab"
    return str(cache_dir / CACHE_FILENAME)


def build_service(workspace_root):
    """The shared runtime composition factory: both the dashboard route
    wrapper and the Hermes tool wrapper call this exact function instead of
    constructing a bare `DeckLabService(workspace_root)` -- which would
    intentionally fall back to offline/cache-only mode."""

    from deck_lab.service import DeckLabService

    transport = HttpxScryfallTransport(_get_http_client())
    return DeckLabService(
        workspace_root,
        cache_path=runtime_cache_path(),
        http_client=transport,
    )
