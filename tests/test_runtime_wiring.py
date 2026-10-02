"""RED-first tests for the shared Deck Lab runtime composition factory
(card t_678aa3e7).

`dashboard/plugin_api.py:_service()` and `deck_lab/tools.py:_service_for()`
must both delegate to one shared factory in `deck_lab.runtime` that wires a
real HTTP transport and a persistent cache path under `HERMES_HOME` -- never
construct a bare `DeckLabService(workspace_root)` with no client/cache in
production code paths.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_API_PATH = REPO_ROOT / "dashboard" / "plugin_api.py"
NELLY_FIXTURE = Path(__file__).parent / "fixtures" / "nelly-borca"

GOOD_DECK_README = (
    "---\nschema: hermes-mtg/deck/v1\nname: Simple\nformat: commander\n"
    "color_identity: [R]\nstatus: built\n---\n"
)
GOOD_BOARD = (
    "---\nschema: hermes-mtg/board/v1\nname: Mainboard\nkind: mainboard\norder: 10\n"
    "---\n\n## Commander\n\n### Commander\n\n```decklist\n1 Sol Ring\n```\n"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _simple_workspace(tmp_path):
    deck_dir = tmp_path / "decks" / "commander" / "simple"
    _write(deck_dir / "README.md", GOOD_DECK_README)
    _write(deck_dir / "mainboard.md", GOOD_BOARD)
    return tmp_path


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


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, headers=None):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.headers = headers or {}

    def json(self):
        return self._json_body


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, headers):
        self.calls.append({"url": url, "json": json, "headers": headers})
        next_response = self.responses.pop(0)
        if next_response == "timeout":
            raise TimeoutError("simulated timeout")
        return next_response


# ---------------------------------------------------------------------
# 1 + 7 + 8: shared factory wires a non-None transport and a persistent
# cache path outside workspace_root, under HERMES_HOME.
# ---------------------------------------------------------------------


def test_build_service_wires_non_none_http_client(tmp_path, monkeypatch):
    from deck_lab import runtime

    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    workspace = _simple_workspace(tmp_path / "workspace")

    service = runtime.build_service(str(workspace))

    assert service.http_client is not None
    assert service.cache_path is not None
    assert not str(service.cache_path).startswith(str(workspace))


def test_build_service_cache_lands_under_hermes_home_not_workspace(tmp_path, monkeypatch):
    from deck_lab import runtime

    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    workspace = _simple_workspace(tmp_path / "workspace")

    service = runtime.build_service(str(workspace))

    assert str(hermes_home) in str(service.cache_path)
    decks_root = workspace / "decks"
    assert not any(decks_root.rglob("*cache*")) if decks_root.exists() else True


def test_build_service_falls_back_to_safe_home_when_hermes_home_unset(tmp_path, monkeypatch):
    from deck_lab import runtime

    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    workspace = _simple_workspace(tmp_path / "workspace")

    service = runtime.build_service(str(workspace))

    assert service.cache_path is not None
    assert str(tmp_path) in str(service.cache_path)


def test_runtime_cache_persists_across_new_service_instances(tmp_path, monkeypatch):
    from deck_lab import runtime
    from deck_lab import scryfall as _scryfall

    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    workspace = _simple_workspace(tmp_path / "workspace")

    fake_client = FakeHttpClient(
        [FakeResponse(json_body={"data": [_card("Sol Ring")], "not_found": []})]
    )
    monkeypatch.setattr(runtime, "_get_http_client", lambda: fake_client)

    service1 = runtime.build_service(str(workspace))
    result = service1.get_deck("decks/commander/simple", resolve_remote=True)
    assert result["remote_unresolved_count"] == 0

    # Second, offline (no client) service using the SAME cache path resolves
    # without any network call.
    cache_path = service1.cache_path
    from deck_lab.service import DeckLabService

    offline = DeckLabService(workspace, cache_path=cache_path)
    offline_result = offline.get_deck("decks/commander/simple", resolve_remote=True)
    assert offline_result["remote_unresolved_count"] == 0
    assert offline_result["cards"][0]["scryfall"]["name"] == "Sol Ring"


# ---------------------------------------------------------------------
# 4: direct DeckLabService(workspace_root) with no client stays cache-only
# ---------------------------------------------------------------------


def test_direct_service_without_client_is_cache_only_no_network(tmp_path):
    from deck_lab.service import DeckLabService

    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace)
    assert service.http_client is None

    result = service.get_deck("decks/commander/simple", resolve_remote=True)
    assert result["cards"][0]["scryfall"] is None
    assert result["remote_unresolved_count"] == 1


# ---------------------------------------------------------------------
# 6: real httpx timeout shape reaches the resolver's retry path, not a 500
# ---------------------------------------------------------------------


def test_httpx_adapter_normalizes_timeout_into_retryable_contract(tmp_path, monkeypatch):
    httpx = pytest.importorskip("httpx")
    from deck_lab import runtime

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))

    class _TimeoutClient:
        def __init__(self):
            self.calls = 0

        def post(self, url, json=None, headers=None, timeout=None):
            self.calls += 1
            raise httpx.TimeoutException("simulated")

    adapter = runtime.HttpxScryfallTransport(_TimeoutClient())
    with pytest.raises(TimeoutError):
        adapter.post("https://api.scryfall.com/cards/collection", json={}, headers={})


def test_timeout_adapter_produces_unresolved_warning_not_500(tmp_path, monkeypatch):
    httpx = pytest.importorskip("httpx")
    from deck_lab import runtime
    from deck_lab.service import DeckLabService

    class _TimeoutClient:
        def post(self, url, json=None, headers=None, timeout=None):
            raise httpx.TimeoutException("simulated")

    adapter = runtime.HttpxScryfallTransport(_TimeoutClient())
    workspace = _simple_workspace(tmp_path)
    service = DeckLabService(workspace, http_client=adapter)

    result = service.get_deck(
        "decks/commander/simple", resolve_remote=True
    )
    assert result["remote_unresolved_count"] == 1
    assert result["remote_warnings"][0]["code"] == "REMOTE_CARD_UNRESOLVED"


# ---------------------------------------------------------------------
# 2 + 3: route delegates to the shared factory (production composition)
# ---------------------------------------------------------------------

_module_name_counter = itertools.count()


def _load_plugin_api():
    name = f"deck_lab_plugin_api_runtime_{next(_module_name_counter)}"
    spec = importlib.util.spec_from_file_location(name, PLUGIN_API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_service_delegates_to_shared_runtime_factory(monkeypatch):
    plugin_api = _load_plugin_api()

    calls = []

    def fake_build_service(workspace_root):
        calls.append(workspace_root)
        from deck_lab.service import DeckLabService

        return DeckLabService(workspace_root)

    monkeypatch.setattr(plugin_api, "build_service", fake_build_service)
    monkeypatch.chdir(NELLY_FIXTURE)

    plugin_api._service(None)

    assert len(calls) == 1


def test_route_get_deck_resolves_through_fake_transport_and_writes_cache(tmp_path, monkeypatch):
    plugin_api = _load_plugin_api()
    from deck_lab import runtime

    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    workspace = _simple_workspace(tmp_path / "workspace")

    fake_client = FakeHttpClient(
        [FakeResponse(json_body={"data": [_card("Sol Ring")], "not_found": []})]
    )
    monkeypatch.setattr(runtime, "_get_http_client", lambda: fake_client)
    monkeypatch.setattr(plugin_api, "build_service", runtime.build_service)

    from fastapi.testclient import TestClient

    client = TestClient(plugin_api.router_app())
    resp = client.get(
        "/deck",
        params={
            "path": "decks/commander/simple",
            "resolve_remote": "true",
            "workspace_root": str(workspace),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["remote_unresolved_count"] == 0
    assert body["cards"][0]["scryfall"]["name"] == "Sol Ring"

    cache_files = list(hermes_home.rglob("*.json"))
    assert cache_files, "expected the runtime cache file to be written under HERMES_HOME"


def test_route_resolve_remote_false_makes_no_transport_call(tmp_path, monkeypatch):
    plugin_api = _load_plugin_api()
    from deck_lab import runtime

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    workspace = _simple_workspace(tmp_path / "workspace")

    fake_client = FakeHttpClient([])  # no responses queued -- must not be called
    monkeypatch.setattr(runtime, "_get_http_client", lambda: fake_client)
    monkeypatch.setattr(plugin_api, "build_service", runtime.build_service)

    from fastapi.testclient import TestClient

    client = TestClient(plugin_api.router_app())
    resp = client.get(
        "/deck",
        params={
            "path": "decks/commander/simple",
            "resolve_remote": "false",
            "workspace_root": str(workspace),
        },
    )
    assert resp.status_code == 200
    assert fake_client.calls == []


def test_route_cache_status_reports_configured_true(tmp_path, monkeypatch):
    plugin_api = _load_plugin_api()
    from deck_lab import runtime

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    workspace = _simple_workspace(tmp_path / "workspace")
    monkeypatch.setattr(plugin_api, "build_service", runtime.build_service)

    from fastapi.testclient import TestClient

    client = TestClient(plugin_api.router_app())
    resp = client.get("/scryfall/cache-status", params={"workspace_root": str(workspace)})
    assert resp.status_code == 200
    assert resp.json()["configured"] is True


# ---------------------------------------------------------------------
# tool-side equivalents
# ---------------------------------------------------------------------


def test_tools_service_for_delegates_to_shared_runtime_factory(monkeypatch):
    from deck_lab import tools as deck_tools

    calls = []

    def fake_build_service(workspace_root):
        calls.append(workspace_root)
        from deck_lab.service import DeckLabService

        return DeckLabService(workspace_root)

    monkeypatch.setattr(deck_tools, "build_service", fake_build_service)

    deck_tools._service_for({"workspace_root": "/tmp/whatever-does-not-need-to-exist"})

    assert len(calls) == 1


def test_deck_get_tool_resolves_remote_under_injected_fake_transport(tmp_path, monkeypatch):
    from deck_lab import runtime
    from deck_lab import tools as deck_tools

    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    workspace = _simple_workspace(tmp_path / "workspace")

    fake_client = FakeHttpClient(
        [FakeResponse(json_body={"data": [_card("Sol Ring")], "not_found": []})]
    )
    monkeypatch.setattr(runtime, "_get_http_client", lambda: fake_client)
    monkeypatch.setattr(deck_tools, "build_service", runtime.build_service)

    raw = deck_tools.handle_deck_get(
        {
            "workspace_root": str(workspace),
            "deck_path": "decks/commander/simple",
            "resolve_remote": True,
        }
    )
    data = json.loads(raw)
    assert data["remote_unresolved_count"] == 0
    assert data["cards"][0]["scryfall"]["name"] == "Sol Ring"


def test_deck_get_tool_resolve_remote_false_makes_no_transport_call(tmp_path, monkeypatch):
    from deck_lab import runtime
    from deck_lab import tools as deck_tools

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    workspace = _simple_workspace(tmp_path / "workspace")

    fake_client = FakeHttpClient([])
    monkeypatch.setattr(runtime, "_get_http_client", lambda: fake_client)
    monkeypatch.setattr(deck_tools, "build_service", runtime.build_service)

    raw = deck_tools.handle_deck_get(
        {
            "workspace_root": str(workspace),
            "deck_path": "decks/commander/simple",
            "resolve_remote": False,
        }
    )
    json.loads(raw)
    assert fake_client.calls == []


# ---------------------------------------------------------------------
# 9: dependency-light registration invariant still holds (bare admission
# probe never needs the runtime module/httpx to be importable).
# ---------------------------------------------------------------------


def test_register_tools_still_dependency_light_without_httpx():
    from deck_lab import tools as deck_tools

    class _FakeCtx:
        def __init__(self):
            self.registered = []

        def register_tool(self, name, **kwargs):
            self.registered.append(name)

    ctx = _FakeCtx()
    deck_tools.register_tools(ctx)
    assert sorted(ctx.registered) == [
        "deck_export",
        "deck_get",
        "deck_import",
        "deck_list",
        "deck_validate",
    ]
