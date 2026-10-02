"""RED contract test for the thin Deck Lab FastAPI routes.

`dashboard/plugin_api.py` is not on any Python package path (the real
dashboard loader imports plugin runtime panes by file path, never via a
normal package import) -- so this test loads it the same way the real
loader would, with `importlib.util.spec_from_file_location`, to prove the
"must import when loaded standalone by file path" constraint for real
instead of asserting it from a package-relative import that could never
catch that failure mode.

This currently fails at import time because `dashboard/plugin_api.py` does
not exist yet. That is the intended RED signal for this contract card.
"""

import importlib.util
import itertools
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_API_PATH = REPO_ROOT / "dashboard" / "plugin_api.py"

NELLY_FIXTURE = Path(__file__).parent / "fixtures" / "nelly-borca"

_module_name_counter = itertools.count()


def _load_plugin_api():
    # Each load gets a unique module name: pydantic caches model schemas by
    # (module, qualname), so reloading "the same" module name across tests
    # (as the real file-path loader would for each plugin reload) raises
    # PydanticUserError "not fully defined" on the second load's BaseModel
    # subclasses. Real standalone-by-file-path loading only happens once per
    # process, so this is a test-only accommodation, not a change to how
    # dashboard/plugin_api.py itself is loaded in production.
    name = f"deck_lab_plugin_api_{next(_module_name_counter)}"
    spec = importlib.util.spec_from_file_location(name, PLUGIN_API_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging error
        raise ImportError(f"cannot load {PLUGIN_API_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.chdir(NELLY_FIXTURE)
    plugin_api = _load_plugin_api()
    return TestClient(plugin_api.router_app())


def test_plugin_api_imports_standalone_by_file_path():
    module = _load_plugin_api()
    assert hasattr(module, "router")


def test_revision_route_returns_service_schema(client):
    resp = client.get("/revision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema"] == "hermes-mtg/service/v1"
    assert "revision" in body


def test_list_decks_route_discovers_nelly(client):
    resp = client.get("/decks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["decks"][0]["path"] == "decks/commander/nelly-borca"


def test_get_deck_route_returns_golden_counts(client):
    resp = client.get(
        "/deck", params={"path": "decks/commander/nelly-borca", "resolve_remote": "false"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 100
    assert body["commander_count"] == 1


def test_validate_route_reports_valid(client):
    resp = client.get("/validate", params={"path": "decks/commander/nelly-borca"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_cache_status_route_reports_unconfigured(client):
    resp = client.get("/scryfall/cache-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False


def test_export_route_renders_manabox_text():
    from fastapi.testclient import TestClient

    import_module = _load_plugin_api()
    client_local = TestClient(import_module.router_app())
    os.chdir(NELLY_FIXTURE)
    resp = client_local.post(
        "/export", json={"deck_path": "decks/commander/nelly-borca", "dialect": "manabox"}
    )
    assert resp.status_code == 200
    assert resp.json()["dialect"] == "manabox"


def test_import_dry_run_route_returns_targets(client):
    resp = client.post(
        "/import",
        json={
            "dialect": "arena",
            "target_deck_path": "decks/commander/scratch-import",
            "text": "1 Sol Ring\n",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["applied"] is False


def test_traversal_path_returns_actionable_error(client):
    resp = client.get("/validate", params={"path": "decks/../../../etc/passwd"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "PATH_OUTSIDE_DECKS_ROOT"


def test_not_found_deck_returns_404(client):
    resp = client.get("/deck", params={"path": "decks/commander/does-not-exist"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DECK_NOT_FOUND"
