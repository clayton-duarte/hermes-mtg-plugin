"""RED contract test for the thin Deck Lab FastAPI routes.

`dashboard/plugin_api.py` is not on any Python package path (the real
dashboard loader imports plugin runtime panes by file path, never via a
normal package import) -- so this test loads it the same way the real
loader would, with `importlib.util.spec_from_file_location`, to prove the
"must import when loaded standalone by file path" constraint for real
instead of asserting it from a package-relative import that could never
catch that failure mode.

"""

import importlib.util
import itertools
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_API_PATH = REPO_ROOT / "dashboard" / "plugin_api.py"
MANIFEST_PATH = REPO_ROOT / "dashboard" / "manifest.json"

NELLY_FIXTURE = Path(__file__).parent / "fixtures" / "nelly-borca"

HERMES_AGENT_SRC = Path("/Users/claytonduarte/.hermes/hermes-agent")

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


def test_import_accepts_single_target_string_expected_hash(client):
    # The merged DeckLabService supports a bare string `expected_hash` as
    # shorthand for a single-target import (vs. {path: hash} for multiple
    # targets). A route-level `Optional[dict]` annotation rejected the
    # valid string form with HTTP 422 before this was fixed.
    resp = client.post(
        "/import",
        json={
            "dialect": "arena",
            "target_deck_path": "decks/commander/scratch-import",
            "text": "1 Sol Ring\n",
            "expected_hash": "deadbeef",
        },
    )
    assert resp.status_code != 422


def test_traversal_path_returns_actionable_error(client):
    resp = client.get("/validate", params={"path": "decks/../../../etc/passwd"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "PATH_OUTSIDE_DECKS_ROOT"


def test_not_found_deck_returns_404(client):
    resp = client.get("/deck", params={"path": "decks/commander/does-not-exist"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DECK_NOT_FOUND"


# ---------------------------------------------------------------------------
# Focused-root propagation: the dashboard is one long-lived process whose own
# cwd cannot represent multiple focused chat projects. Routes must accept an
# explicit `workspace_root` and use it instead of (or in addition to) the
# process cwd.
# ---------------------------------------------------------------------------


def test_revision_route_uses_explicit_workspace_root_over_process_cwd(tmp_path, monkeypatch):
    """monkeypatch.chdir() only proves process-cwd behavior; this proves
    the route honors an explicit workspace_root that differs from the
    server process's actual cwd."""
    from fastapi.testclient import TestClient

    # Process cwd points somewhere with NO decks/ at all.
    empty_root = tmp_path / "empty_process_cwd"
    empty_root.mkdir()
    monkeypatch.chdir(empty_root)

    plugin_api = _load_plugin_api()
    client_local = TestClient(plugin_api.router_app())

    resp = client_local.get("/decks", params={"workspace_root": str(NELLY_FIXTURE)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["decks"][0]["path"] == "decks/commander/nelly-borca"


def test_decks_route_without_workspace_root_falls_back_to_process_cwd(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.chdir(NELLY_FIXTURE)
    plugin_api = _load_plugin_api()
    client_local = TestClient(plugin_api.router_app())

    resp = client_local.get("/decks")
    assert resp.status_code == 200
    assert resp.json()["decks"][0]["path"] == "decks/commander/nelly-borca"


# ---------------------------------------------------------------------------
# Neutral-path standalone import: run in a real subprocess from `/` with a
# cleared PYTHONPATH, so the installed-uv-project masking this repo's own
# test session provides cannot hide a bare `deck_lab` import failure.
# ---------------------------------------------------------------------------


def test_plugin_api_imports_standalone_from_neutral_cwd_and_pythonpath():
    script = textwrap.dedent(
        f"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "deck_lab_plugin_api_neutral", {str(PLUGIN_API_PATH)!r}
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "router")
        print("NEUTRAL_IMPORT_OK")
        """
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd="/",
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "NEUTRAL_IMPORT_OK" in result.stdout


# ---------------------------------------------------------------------------
# Real discovery/mount seam: Hermes never imports plugin_api.py directly --
# it discovers it via dashboard/manifest.json's `api` field
# (`_discover_dashboard_plugins`) and mounts it under
# `/api/plugins/<name>/` (`_mount_plugin_api_routes`). Exercise those real
# functions, not a hand-rolled substitute.
# ---------------------------------------------------------------------------


@pytest.fixture
def hermes_dashboard_module():
    if not HERMES_AGENT_SRC.is_dir():
        pytest.skip(f"hermes-agent source not available at {HERMES_AGENT_SRC}")
    added = str(HERMES_AGENT_SRC) not in sys.path
    if added:
        sys.path.insert(0, str(HERMES_AGENT_SRC))
    try:
        import hermes_cli.web_server_dashboard as dashboard_mod
    except Exception as exc:  # pragma: no cover - environment gap
        pytest.skip(f"hermes_cli.web_server_dashboard unavailable: {exc}")
    yield dashboard_mod
    if added:
        sys.path.remove(str(HERMES_AGENT_SRC))


def _require_web_server_app():
    """`_mount_plugin_api_routes` imports `hermes_cli.web_server.app` lazily,
    which drags in the full dashboard dependency tree (psutil, etc). Skip
    the real-mount test rather than fake that dependency chain when it is
    not installed in this isolated test env -- the plugin-side contract
    (manifest declares api, _dashboard_plugin_entry sets has_api) is still
    proven by test_manifest_declares_api_file_and_is_discovered without it.
    """
    try:
        import hermes_cli.web_server  # noqa: F401
    except Exception as exc:
        pytest.skip(f"hermes_cli.web_server full import chain unavailable: {exc}")


def test_manifest_declares_api_file_and_is_discovered(hermes_dashboard_module):
    manifest = json.loads(MANIFEST_PATH.read_text())
    assert manifest["api"] == "plugin_api.py"

    dashboard_dir = REPO_ROOT / "dashboard"
    entry = hermes_dashboard_module._dashboard_plugin_entry(
        manifest, manifest["name"], dashboard_dir, "user"
    )
    assert entry["has_api"] is True
    assert entry["_api_file"] == "plugin_api.py"
    # Hidden-tab/API-only contract: no nav tab, but the API still mounts.
    assert entry["tab"]["hidden"] is True


def test_mount_plugin_api_routes_wires_router_under_plugin_prefix(
    hermes_dashboard_module, monkeypatch
):
    _require_web_server_app()
    from fastapi import FastAPI

    manifest = json.loads(MANIFEST_PATH.read_text())
    dashboard_dir = REPO_ROOT / "dashboard"
    entry = hermes_dashboard_module._dashboard_plugin_entry(
        manifest, manifest["name"], dashboard_dir, "user"
    )

    test_app = FastAPI()
    monkeypatch.setattr(
        "hermes_cli.web_server.app", test_app, raising=False
    )
    monkeypatch.setattr(
        "hermes_cli.web_server._get_dashboard_plugins", lambda *a, **k: [entry]
    )
    monkeypatch.setattr(
        "hermes_cli.plugins_cmd._get_enabled_set",
        lambda: {manifest["name"]},
        raising=False,
    )
    monkeypatch.setattr(
        "hermes_cli.plugins_cmd._get_disabled_set", lambda: set(), raising=False
    )

    hermes_dashboard_module._mount_plugin_api_routes()

    from fastapi.testclient import TestClient

    with TestClient(test_app) as client:
        resp = client.get(f"/api/plugins/{manifest['name']}/revision")
    assert resp.status_code == 200
    assert resp.json()["schema"] == "hermes-mtg/service/v1"
