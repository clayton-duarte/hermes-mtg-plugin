"""Full behavior tests for the Scryfall batch resolver and cache
(t_5d228091). Deterministic HTTP fakes only -- no real network calls.
"""

from __future__ import annotations

import json

import pytest

from deck_lab.scryfall import (
    MAX_IDENTIFIERS_PER_BATCH,
    ScryfallCache,
    identifier_for_card,
    resolve_collection,
)


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, headers=None):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.headers = headers or {}

    def json(self):
        return self._json_body


class FakeHttpClient:
    """Deterministic fake: `responses` is a list consumed in order per
    call to `.post`; a response may also be the string "timeout" to
    simulate a `TimeoutError`."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, headers):
        self.calls.append({"url": url, "json": json, "headers": headers})
        next_response = self.responses.pop(0)
        if next_response == "timeout":
            raise TimeoutError("simulated timeout")
        return next_response


def _card(name, **overrides):
    card = {
        "name": name,
        "oracle_id": f"oracle-{name}",
        "id": f"id-{name}",
        "scryfall_uri": f"https://scryfall.com/card/{name}",
        "mana_cost": "{1}{U}",
        "layout": "normal",
        "image_uris": {"normal": f"https://img/{name}.jpg"},
    }
    card.update(overrides)
    return card


def test_identifier_for_card_prefers_set_collector_over_name():
    identifier = identifier_for_card("znr", "100", "Essence Scatter")
    assert identifier == {"set": "znr", "collector_number": "100", "name": "Essence Scatter"}


def test_identifier_for_card_falls_back_to_exact_name():
    identifier = identifier_for_card(None, None, "Essence Scatter")
    assert identifier == {"name": "Essence Scatter"}


def test_resolve_collection_sends_required_headers_and_pacing():
    identifiers = [{"name": "Arcane Signet"}]
    http_client = FakeHttpClient([FakeResponse(json_body={"data": [_card("Arcane Signet")], "not_found": []})])

    resolve_collection(identifiers, http_client=http_client)

    call = http_client.calls[0]
    assert call["url"] == "https://api.scryfall.com/cards/collection"
    assert call["headers"]["Accept"] == "application/json"
    assert call["headers"]["Content-Type"] == "application/json"
    assert "User-Agent" in call["headers"]
    assert call["json"] == {"identifiers": identifiers}


def test_resolve_collection_exact_printing_resolution_before_name_fallback():
    identifier = identifier_for_card("znr", "100", "Essence Scatter")
    http_client = FakeHttpClient(
        [FakeResponse(json_body={"data": [_card("Essence Scatter", set="znr", collector_number="100")], "not_found": []})]
    )

    results = resolve_collection([identifier], http_client=http_client)

    key = ("set_collector", "znr", "100")
    assert results[key] is not None
    assert results[key].name == "Essence Scatter"


def test_resolve_collection_returns_dfc_card_faces():
    card = _card("Delver of Secrets // Insectile Aberration", layout="transform", image_uris={})
    card["card_faces"] = [
        {"name": "Delver of Secrets", "mana_cost": "{U}", "image_uris": {"normal": "https://img/front.jpg"}},
        {"name": "Insectile Aberration", "mana_cost": "", "image_uris": {"normal": "https://img/back.jpg"}},
    ]
    http_client = FakeHttpClient([FakeResponse(json_body={"data": [card], "not_found": []})])

    results = resolve_collection(
        [{"name": "Delver of Secrets // Insectile Aberration"}], http_client=http_client
    )

    key = ("name", "Delver of Secrets // Insectile Aberration")
    projection = results[key]
    assert projection.layout == "transform"
    assert len(projection.card_faces) == 2
    assert projection.card_faces[0]["name"] == "Delver of Secrets"
    assert projection.card_faces[0]["image_uris"]["normal"] == "https://img/front.jpg"


def test_resolve_collection_marks_not_found_as_unresolved():
    http_client = FakeHttpClient([FakeResponse(json_body={"data": [], "not_found": [{"name": "Nonexistent Card"}]})])

    results = resolve_collection([{"name": "Nonexistent Card"}], http_client=http_client)

    assert results[("name", "Nonexistent Card")] is None


def test_resolve_collection_retries_on_429_then_succeeds():
    http_client = FakeHttpClient(
        [
            FakeResponse(status_code=429, headers={"Retry-After": "0"}),
            FakeResponse(json_body={"data": [_card("Sol Ring")], "not_found": []}),
        ]
    )
    sleeps = []

    results = resolve_collection(
        [{"name": "Sol Ring"}], http_client=http_client, sleep_fn=lambda s: sleeps.append(s)
    )

    assert results[("name", "Sol Ring")].name == "Sol Ring"
    # One sleep from the 429 Retry-After backoff, plus one from pacing
    # the second outbound request >=500ms after the first.
    assert len(sleeps) == 2
    assert sleeps[0] == 0.0
    assert sleeps[1] >= 0.4
    assert len(http_client.calls) == 2


def test_resolve_collection_429_exhausted_marks_unresolved():
    http_client = FakeHttpClient(
        [
            FakeResponse(status_code=429, headers={"Retry-After": "0"}),
            FakeResponse(status_code=429, headers={"Retry-After": "0"}),
        ]
    )

    results = resolve_collection(
        [{"name": "Sol Ring"}], http_client=http_client, max_retries=2, sleep_fn=lambda s: None
    )

    assert results[("name", "Sol Ring")] is None


def test_resolve_collection_timeout_retries_then_succeeds():
    http_client = FakeHttpClient(["timeout", FakeResponse(json_body={"data": [_card("Sol Ring")], "not_found": []})])

    results = resolve_collection([{"name": "Sol Ring"}], http_client=http_client, sleep_fn=lambda s: None)

    assert results[("name", "Sol Ring")].name == "Sol Ring"


def test_resolve_collection_timeout_exhausted_marks_unresolved():
    http_client = FakeHttpClient(["timeout", "timeout"])

    results = resolve_collection(
        [{"name": "Sol Ring"}], http_client=http_client, max_retries=2, sleep_fn=lambda s: None
    )

    assert results[("name", "Sol Ring")] is None


def test_resolve_collection_caps_at_75_and_issues_multiple_requests():
    identifiers = [{"name": f"Card {i}"} for i in range(80)]
    responses = [FakeResponse(json_body={"data": [], "not_found": []}) for _ in range(2)]
    http_client = FakeHttpClient(responses)

    resolve_collection(identifiers, http_client=http_client)

    assert len(http_client.calls) == 2
    assert len(http_client.calls[0]["json"]["identifiers"]) == MAX_IDENTIFIERS_PER_BATCH
    assert len(http_client.calls[1]["json"]["identifiers"]) == 5


def test_resolve_collection_mixed_batch_not_found_maps_correct_identifiers():
    http_client = FakeHttpClient(
        [
            FakeResponse(
                json_body={
                    "data": [_card("Sol Ring"), _card("Arcane Signet")],
                    "not_found": [{"name": "Nonexistent Card"}],
                }
            )
        ]
    )

    results = resolve_collection(
        [{"name": "Sol Ring"}, {"name": "Nonexistent Card"}, {"name": "Arcane Signet"}],
        http_client=http_client,
        sleep_fn=lambda s: None,
    )

    assert results[("name", "Sol Ring")].name == "Sol Ring"
    assert results[("name", "Nonexistent Card")] is None
    assert results[("name", "Arcane Signet")].name == "Arcane Signet"


def test_resolve_collection_exact_printing_miss_falls_back_to_exact_name():
    identifier = identifier_for_card("znr", "100", "Essence Scatter")
    http_client = FakeHttpClient(
        [
            FakeResponse(json_body={"data": [], "not_found": [{"set": "znr", "collector_number": "100"}]}),
            FakeResponse(json_body={"data": [_card("Essence Scatter")], "not_found": []}),
        ]
    )

    results = resolve_collection([identifier], http_client=http_client, sleep_fn=lambda s: None)

    key = ("set_collector", "znr", "100")
    assert results[key] is not None
    assert results[key].name == "Essence Scatter"
    assert len(http_client.calls) == 2
    assert http_client.calls[1]["json"] == {"identifiers": [{"name": "Essence Scatter"}]}


def test_resolve_collection_exact_printing_hit_performs_no_fallback():
    identifier = identifier_for_card("znr", "100", "Essence Scatter")
    http_client = FakeHttpClient(
        [FakeResponse(json_body={"data": [_card("Essence Scatter", set="znr", collector_number="100")], "not_found": []})]
    )

    results = resolve_collection([identifier], http_client=http_client, sleep_fn=lambda s: None)

    key = ("set_collector", "znr", "100")
    assert results[key] is not None
    assert len(http_client.calls) == 1


def test_resolve_collection_paces_requests_at_least_500ms_apart():
    identifiers = [{"name": f"Card {i}"} for i in range(80)]
    responses = [FakeResponse(json_body={"data": [], "not_found": []}) for _ in range(2)]
    http_client = FakeHttpClient(responses)

    clock = {"t": 0.0}
    sleeps = []

    def fake_clock():
        return clock["t"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds

    resolve_collection(identifiers, http_client=http_client, sleep_fn=fake_sleep, clock_fn=fake_clock)

    assert len(http_client.calls) == 2
    assert len(sleeps) == 1
    assert sleeps[0] >= 0.5


def test_resolve_collection_serves_fresh_cache_without_network_call(tmp_path):
    import time as time_module

    cache_path = str(tmp_path / "scryfall_cache_test_fresh.json")
    cache = ScryfallCache(cache_path)
    cache.put(("name", "Sol Ring"), {"name": "Sol Ring", "oracle_id": "o1"}, now=time_module.time())

    http_client = FakeHttpClient([])  # no responses queued: must not be called

    results = resolve_collection(
        [{"name": "Sol Ring"}], http_client=http_client, cache=cache, sleep_fn=lambda s: None
    )

    assert results[("name", "Sol Ring")].name == "Sol Ring"
    assert len(http_client.calls) == 0


def test_resolve_collection_stale_cache_serves_then_revalidates(tmp_path):
    cache_path = str(tmp_path / "scryfall_cache_test_stale.json")
    cache = ScryfallCache(cache_path, ttl_seconds=10)
    cache.put(("name", "Sol Ring"), {"name": "Sol Ring", "oracle_id": "o1"}, now=0.0)

    http_client = FakeHttpClient([FakeResponse(json_body={"data": [_card("Sol Ring")], "not_found": []})])

    import time as time_module

    real_time = time_module.time
    try:
        time_module.time = lambda: 1_000_000.0  # force staleness
        results = resolve_collection(
            [{"name": "Sol Ring"}], http_client=http_client, cache=cache, sleep_fn=lambda s: None
        )
    finally:
        time_module.time = real_time

    # Stale entry is served immediately (no unresolved row)...
    assert results[("name", "Sol Ring")] is not None
    # ...and the cache was revalidated against the network.
    assert len(http_client.calls) == 1


def test_resolve_collection_no_cache_flag_forces_network_call(tmp_path):
    cache_path = str(tmp_path / "scryfall_cache_test_nocache.json")
    cache = ScryfallCache(cache_path)
    cache.put(("name", "Sol Ring"), {"name": "Sol Ring", "oracle_id": "o1"}, now=0.0)

    http_client = FakeHttpClient([FakeResponse(json_body={"data": [_card("Sol Ring")], "not_found": []})])

    resolve_collection(
        [{"name": "Sol Ring"}], http_client=http_client, cache=cache, no_cache=True, sleep_fn=lambda s: None
    )

    assert len(http_client.calls) == 1


def test_cache_persists_across_instances_without_repository_writes(tmp_path):
    cache_path = str(tmp_path / "scryfall_cache.json")
    cache = ScryfallCache(cache_path)
    cache.put(("name", "Sol Ring"), {"name": "Sol Ring", "oracle_id": "o1"}, now=1000.0)

    reloaded = ScryfallCache(cache_path)
    entry = reloaded.get(("name", "Sol Ring"))

    assert entry is not None
    assert entry["data"]["name"] == "Sol Ring"
    with open(cache_path) as fh:
        on_disk = json.load(fh)
    assert on_disk  # cache file written at the caller-supplied path, not into the repo
