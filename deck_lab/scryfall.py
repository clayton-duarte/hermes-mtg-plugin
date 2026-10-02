"""Scryfall batch resolver and persistent stale-while-revalidate cache
(t_5d228091, corrected by t_9e8245c7).

Implements:
  - `resolve_collection`: batches identifiers into <=75-item requests to
    POST https://api.scryfall.com/cards/collection with required headers,
    retries on 429/timeout with backoff, paces outbound requests at least
    500ms apart, and serves cache-first results.
  - `identifier_for_card`: set+collector printing resolution before the
    exact-name fallback, used by callers to build identifier dicts.
  - `ScryfallCache`: a plugin/profile-owned persistent JSON cache (the
    caller supplies the path -- this module never writes into the deck
    repository). Stale entries are served immediately and refreshed in
    the same call (stale-while-revalidate), never silently dropped.

Unresolved identifiers (timeout exhausted, 429 exhausted, or a Scryfall
`not_found` entry with no usable cache and no successful name fallback)
resolve to `None` in the result dict. Callers render those rows with
`models.ERROR_CODES` member `REMOTE_CARD_UNRESOLVED` rather than failing
parsing.

Response association (defect #1/#2 correction): Scryfall's `/cards/collection`
response preserves the request order of *found* identifiers in `data` and
echoes failed identifiers verbatim in `not_found`. A name-only request's
returned Card object always carries `set`/`collector_number` too, so
association MUST NOT be done by re-deriving a key from the returned card's
printing fields -- that silently drops every exact-name request. Instead we
walk `to_fetch` in request order, consult `not_found` (by identifier value)
to decide whether a given request failed, and otherwise consume the next
item from `data` in order.

An identifier dict built for exact-printing resolution may additionally
carry a `"name"` key (NOT part of the Scryfall wire identifier) that this
module uses -- and strips before sending -- to retry an unresolved
set+collector identifier by exact name (defect #2 correction).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from typing import Optional

from deck_lab.models import ScryfallProjection

SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
MAX_IDENTIFIERS_PER_BATCH = 75
USER_AGENT = "hermes-mtg-plugin/0.1 (+https://github.com/clayton-duarte/hermes-mtg-plugin)"
STALE_TTL_SECONDS = 24 * 60 * 60  # 24h cache freshness window

# Scryfall's documented /cards/collection rate limit is 2 requests/second.
MIN_REQUEST_INTERVAL_SECONDS = 0.5


def identifier_for_card(set_code: Optional[str], collector_number: Optional[str], name: str) -> dict:
    """Set+collector printing resolution before the exact-name fallback.

    When both `set_code` and `collector_number` are present, prefer the
    exact-printing Scryfall identifier shape; otherwise fall back to an
    exact-name identifier.
    """

    if set_code and collector_number:
        return {"set": set_code.lower(), "collector_number": str(collector_number), "name": name}
    return {"name": name}


def _identifier_key(identifier: dict) -> tuple:
    if "set" in identifier and "collector_number" in identifier:
        return ("set_collector", identifier["set"].lower(), str(identifier["collector_number"]))
    return ("name", identifier.get("name"))


def identifier_key(identifier: dict) -> tuple:
    """Public wrapper over the identifier -> cache/result key mapping, so
    callers outside this module (e.g. the service lane) never reach into
    the private `_identifier_key`."""

    return _identifier_key(identifier)


def resolve_from_cache(identifiers, cache) -> dict:
    """Cache-only resolution: never performs a network call. Used by
    callers (e.g. the service lane) that must honor `resolve_remote=True`
    without a declared `http_client` -- an intentional offline/cache-only
    fallback rather than a crash or a silent no-op. Entries are served
    whether fresh or stale (stale-while-revalidate without the
    revalidate, since there is no transport to revalidate with); anything
    absent from the cache resolves to `None` (unresolved).

    Returns `{identifier_key: ScryfallProjection | None}`, matching the
    shape `resolve_collection` returns.
    """

    results: dict = {}
    for identifier in identifiers:
        key = _identifier_key(identifier)
        entry = cache.get(key) if cache is not None else None
        results[key] = _projection_from_dict(entry["data"]) if entry is not None else None
    return results


def _wire_identifier(identifier: dict) -> dict:
    """The exact shape POSTed to Scryfall -- strips any caller-side-only
    metadata (e.g. a `name` fallback hint carried alongside set+collector)."""

    if "set" in identifier and "collector_number" in identifier:
        return {"set": identifier["set"], "collector_number": identifier["collector_number"]}
    return {"name": identifier["name"]}


def _identifier_matches_not_found(wire_identifier: dict, not_found_entry: dict) -> bool:
    return wire_identifier == not_found_entry


def _batches(identifiers, size=MAX_IDENTIFIERS_PER_BATCH):
    for i in range(0, len(identifiers), size):
        yield list(identifiers[i : i + size])


def _cache_key_str(key: tuple) -> str:
    return "|".join(str(part) for part in key)


class ScryfallCache:
    """Plugin/profile-owned persistent stale-while-revalidate cache.

    The caller is responsible for choosing a path outside the deck
    repository (e.g. a Hermes plugin/profile cache directory) -- this
    class performs no repository writes of its own.
    """

    def __init__(self, path: Optional[str], ttl_seconds: int = STALE_TTL_SECONDS):
        self.path = path
        self.ttl_seconds = ttl_seconds
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if self.path and os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as fh:
                try:
                    self._data = json.load(fh)
                except json.JSONDecodeError:
                    self._data = {}

    def _save(self) -> None:
        if not self.path:
            return
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh)

    def get(self, key: tuple) -> Optional[dict]:
        return self._data.get(_cache_key_str(key))

    def is_fresh(self, entry: Optional[dict], now: Optional[float] = None) -> bool:
        if entry is None:
            return False
        now = time.time() if now is None else now
        return (now - entry["fetched_at"]) < self.ttl_seconds

    def put(self, key: tuple, projection_dict: dict, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self._data[_cache_key_str(key)] = {"fetched_at": now, "data": projection_dict}
        self._save()

    def entries(self) -> list:
        """Public read-only snapshot of cached entries, for status/
        diagnostic reporting only -- callers must never reach into
        `_data` directly."""

        return list(self._data.values())


def _projection_from_dict(data: dict) -> ScryfallProjection:
    return ScryfallProjection(**data)


def _projection_from_scryfall_card(card: dict) -> ScryfallProjection:
    image_uris = card.get("image_uris") or {}
    card_faces = []
    for face in card.get("card_faces") or []:
        card_faces.append(
            {
                "name": face.get("name"),
                "mana_cost": face.get("mana_cost"),
                "image_uris": {"normal": face["image_uris"]["normal"]}
                if face.get("image_uris", {}).get("normal")
                else {},
            }
        )
    return ScryfallProjection(
        name=card.get("name"),
        oracle_id=card.get("oracle_id"),
        scryfall_id=card.get("id"),
        scryfall_uri=card.get("scryfall_uri"),
        mana_cost=card.get("mana_cost"),
        layout=card.get("layout"),
        image_uris={"normal": image_uris["normal"]} if image_uris.get("normal") else {},
        card_faces=card_faces,
    )


class _Pacer:
    """Enforces >= `min_interval` seconds between outbound requests,
    using an injectable clock/sleeper for deterministic tests."""

    def __init__(self, min_interval, clock_fn, sleep_fn):
        self.min_interval = min_interval
        self.clock_fn = clock_fn
        self.sleep_fn = sleep_fn
        self._last_sent_at = None

    def before_request(self) -> None:
        if self._last_sent_at is not None:
            elapsed = self.clock_fn() - self._last_sent_at
            remaining = self.min_interval - elapsed
            if remaining > 0:
                self.sleep_fn(remaining)
        self._last_sent_at = self.clock_fn()


def _post_with_retry(http_client, identifiers, max_retries, sleep_fn, pacer):
    """POST one batch, retrying on 429/timeout. Returns the parsed JSON
    body, or None if every attempt failed."""

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        pacer.before_request()
        try:
            response = http_client.post(
                SCRYFALL_COLLECTION_URL,
                json={"identifiers": identifiers},
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except TimeoutError:
            if attempt >= max_retries:
                return None
            sleep_fn(2**attempt)
            continue

        if getattr(response, "status_code", 200) == 429:
            if attempt >= max_retries:
                return None
            retry_after = float(getattr(response, "headers", {}).get("Retry-After", 2**attempt))
            sleep_fn(retry_after)
            continue

        return response.json()

    return None


def _resolve_batch(to_fetch, http_client, max_retries, sleep_fn, pacer):
    """Resolve one batch of (key, identifier) pairs. Returns a dict of
    `key -> ScryfallProjection | None`."""

    wire_identifiers = [_wire_identifier(identifier) for _, identifier in to_fetch]
    body = _post_with_retry(http_client, wire_identifiers, max_retries=max_retries, sleep_fn=sleep_fn, pacer=pacer)

    if body is None:
        return {key: None for key, _identifier in to_fetch}

    data = list(body.get("data", []))
    not_found = list(body.get("not_found", []))
    data_iter = iter(data)

    resolved: dict = {}
    for (key, _identifier), wire_identifier in zip(to_fetch, wire_identifiers):
        matched_not_found = False
        for i, entry in enumerate(not_found):
            if _identifier_matches_not_found(wire_identifier, entry):
                matched_not_found = True
                del not_found[i]
                break
        if matched_not_found:
            resolved[key] = None
            continue
        card = next(data_iter, None)
        resolved[key] = _projection_from_scryfall_card(card) if card is not None else None

    return resolved


def resolve_collection(
    identifiers,
    http_client=None,
    dry_run=False,
    cache=None,
    no_cache=False,
    max_retries=3,
    sleep_fn=None,
    clock_fn=None,
):
    """Batch `identifiers` (each a Scryfall identifier dict -- see
    `identifier_for_card`) into <=75-item POST /cards/collection requests.

    An identifier produced for exact-printing resolution (containing `set`
    and `collector_number`) may additionally carry a `name` key; on an
    exact-printing `not_found` miss, that name is retried as a single
    exact-name fallback request. The `name` key is never sent to Scryfall.

    `dry_run=True` returns the batches themselves (`list[list[dict]]`)
    with no network calls -- used to prove the 75-identifier cap.

    Otherwise returns `{identifier_key: ScryfallProjection | None}`.
    `None` means the identifier is a valid row with no resolvable
    Scryfall data (timeout exhausted, 429 exhausted, `not_found` with no
    successful fallback); callers render it with `REMOTE_CARD_UNRESOLVED`
    rather than failing.
    """

    batches = list(_batches(identifiers))
    if dry_run:
        return batches

    sleep_fn = sleep_fn or time.sleep
    clock_fn = clock_fn or time.monotonic
    pacer = _Pacer(MIN_REQUEST_INTERVAL_SECONDS, clock_fn, sleep_fn)

    results: dict = {}
    fallback_candidates: list = []  # [(key, name)] for exact-printing misses

    for batch in batches:
        to_fetch = []
        for identifier in batch:
            key = _identifier_key(identifier)
            cached_entry = None if no_cache else cache.get(key) if cache else None
            if cached_entry is not None:
                results[key] = _projection_from_dict(cached_entry["data"])
                if cache.is_fresh(cached_entry):
                    continue  # fresh: served from cache, no refetch needed
            to_fetch.append((key, identifier))

        if not to_fetch:
            continue

        resolved = _resolve_batch(to_fetch, http_client, max_retries, sleep_fn, pacer)

        for key, identifier in to_fetch:
            projection = resolved.get(key)
            if projection is not None:
                results[key] = projection
                if cache is not None:
                    cache.put(key, asdict(projection))
            else:
                if key[0] == "set_collector" and identifier.get("name"):
                    fallback_candidates.append((key, identifier["name"]))
                else:
                    results.setdefault(key, None)

    if fallback_candidates:
        fallback_to_fetch = [(key, {"name": name}) for key, name in fallback_candidates]
        for fallback_batch in _batches(fallback_to_fetch):
            resolved = _resolve_batch(fallback_batch, http_client, max_retries, sleep_fn, pacer)
            for key, identifier in fallback_batch:
                projection = resolved.get(key)
                if projection is not None:
                    results[key] = projection
                    if cache is not None:
                        cache.put(key, asdict(projection))
                else:
                    results.setdefault(key, None)

    return results
