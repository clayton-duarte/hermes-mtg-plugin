"""Scryfall batch resolver and persistent stale-while-revalidate cache
(t_5d228091).

Implements:
  - `resolve_collection`: batches identifiers into <=75-item requests to
    POST https://api.scryfall.com/cards/collection with required headers,
    retries on 429/timeout with backoff, and serves cache-first results.
  - `identifier_for_card`: set+collector printing resolution before the
    exact-name fallback, used by callers to build identifier dicts.
  - `ScryfallCache`: a plugin/profile-owned persistent JSON cache (the
    caller supplies the path -- this module never writes into the deck
    repository). Stale entries are served immediately and refreshed in
    the same call (stale-while-revalidate), never silently dropped.

Unresolved identifiers (timeout exhausted, 429 exhausted, or a Scryfall
`not_found` entry with no usable cache) resolve to `None` in the result
dict. Callers render those rows with `models.ERROR_CODES` member
`REMOTE_CARD_UNRESOLVED` rather than failing parsing.
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


def identifier_for_card(set_code: Optional[str], collector_number: Optional[str], name: str) -> dict:
    """Set+collector printing resolution before the exact-name fallback.

    When both `set_code` and `collector_number` are present, prefer the
    exact-printing Scryfall identifier shape; otherwise fall back to an
    exact-name identifier.
    """

    if set_code and collector_number:
        return {"set": set_code.lower(), "collector_number": str(collector_number)}
    return {"name": name}


def _identifier_key(identifier: dict) -> tuple:
    if "set" in identifier and "collector_number" in identifier:
        return ("set_collector", identifier["set"].lower(), str(identifier["collector_number"]))
    return ("name", identifier.get("name"))


def _card_key(card: dict) -> tuple:
    if card.get("set") and card.get("collector_number"):
        return ("set_collector", card["set"].lower(), str(card["collector_number"]))
    return ("name", card.get("name"))


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


def _post_with_retry(http_client, identifiers, max_retries, sleep_fn):
    """POST one batch, retrying on 429/timeout. Returns the parsed JSON
    body, or None if every attempt failed."""

    attempt = 0
    while attempt < max_retries:
        attempt += 1
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


def resolve_collection(
    identifiers,
    http_client=None,
    dry_run=False,
    cache=None,
    no_cache=False,
    max_retries=3,
    sleep_fn=None,
):
    """Batch `identifiers` (each a Scryfall identifier dict -- see
    `identifier_for_card`) into <=75-item POST /cards/collection requests.

    `dry_run=True` returns the batches themselves (`list[list[dict]]`)
    with no network calls -- used to prove the 75-identifier cap.

    Otherwise returns `{identifier_key: ScryfallProjection | None}`.
    `None` means the identifier is a valid row with no resolvable
    Scryfall data (timeout exhausted, 429 exhausted, or `not_found`);
    callers render it with `REMOTE_CARD_UNRESOLVED` rather than failing.
    """

    batches = list(_batches(identifiers))
    if dry_run:
        return batches

    sleep_fn = sleep_fn or (lambda _seconds: None)
    results: dict = {}

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

        body = _post_with_retry(
            http_client,
            [identifier for _, identifier in to_fetch],
            max_retries=max_retries,
            sleep_fn=sleep_fn,
        )

        if body is None:
            # Total failure (e.g. timeout/429 retries exhausted): keep any
            # stale value already recorded in `results`; otherwise mark
            # unresolved so the row still renders.
            for key, _identifier in to_fetch:
                results.setdefault(key, None)
            continue

        resolved_by_key = {_card_key(card): _projection_from_scryfall_card(card) for card in body.get("data", [])}

        for key, identifier in to_fetch:
            projection = resolved_by_key.get(key)
            if projection is None and key[0] == "set_collector":
                # Printing-exact miss: Scryfall's `not_found` array means
                # this specific identifier did not resolve. No further
                # fallback is attempted here -- exact-name fallback is a
                # caller-side identifier choice (`identifier_for_card`),
                # not a resolver-side retry.
                projection = None
            if projection is not None:
                results[key] = projection
                if cache is not None:
                    cache.put(key, asdict(projection))
            else:
                results.setdefault(key, None)

    return results
