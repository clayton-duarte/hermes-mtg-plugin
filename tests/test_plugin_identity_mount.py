"""Identity-unification regression test (card t_ec7866cf).

Proves the real root ``plugin.yaml`` name and the real dashboard
``manifest.json`` name are the same canonical id, and that the real Hermes
``_plugin_api_mount_skip_reason`` gate therefore allows the dashboard/API
plugin to mount once that id is in ``plugins.enabled`` -- reproducing the
exact RED probe pasted into this card before the fix.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
HERMES_AGENT_ROOT = Path(
    os.environ.get("HERMES_AGENT_ROOT", "/Users/claytonduarte/.hermes/hermes-agent")
)


def _hermes_agent_importable() -> bool:
    return (HERMES_AGENT_ROOT / "hermes_cli" / "web_server_dashboard.py").is_file()


pytestmark = pytest.mark.skipif(
    not _hermes_agent_importable(),
    reason="real Hermes agent checkout not found; identity-mount test needs it",
)


def _root_manifest_name() -> str:
    data = yaml.safe_load((REPO_ROOT / "plugin.yaml").read_text())
    return data["name"]


def _dashboard_manifest_name() -> str:
    data = json.loads((REPO_ROOT / "dashboard" / "manifest.json").read_text())
    return data["name"]


def test_root_and_dashboard_manifest_names_match():
    """The identity mismatch this card fixes: without this, the root
    enable-identity and the dashboard/API discovery identity diverge and the
    mount gate below rejects the plugin no matter what's enabled."""
    assert _root_manifest_name() == _dashboard_manifest_name()


def test_mount_skip_reason_is_none_once_the_canonical_id_is_enabled():
    import sys

    if str(HERMES_AGENT_ROOT) not in sys.path:
        sys.path.insert(0, str(HERMES_AGENT_ROOT))
    from hermes_cli.web_server_dashboard import (
        _dashboard_plugin_entry,
        _plugin_api_mount_skip_reason,
    )

    root_name = _root_manifest_name()
    dashboard_name = _dashboard_manifest_name()
    data = json.loads((REPO_ROOT / "dashboard" / "manifest.json").read_text())
    entry = _dashboard_plugin_entry(data, dashboard_name, REPO_ROOT / "dashboard", source="user")

    enabled_set = {root_name}
    disabled_set: set = set()

    skip_reason = _plugin_api_mount_skip_reason(entry, enabled_set, disabled_set)

    debug = {
        "root_name": root_name,
        "dashboard_name": dashboard_name,
        "enabled_set": sorted(enabled_set),
        "skip_reason": skip_reason,
    }
    assert skip_reason is None, (
        f"dashboard API identity must match installed plugin enable identity: {debug}"
    )
