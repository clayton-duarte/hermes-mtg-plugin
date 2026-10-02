"""Loader-seam test (card t_b5b4148d, correction round): proves the real Hermes
plugin loader -- not a direct ``register_tools(ctx)`` call -- discovers and
registers exactly the five Deck Lab tools via the root ``register(ctx)``
entrypoint next to ``plugin.yaml``.

Run from a neutral cwd with ``$HERMES_HOME`` pointed at a throwaway user
plugins directory containing a *copy* of this repo's plugin files (manifest +
``__init__.py`` + ``deck_lab`` package), isolated from the real Hermes repo's
own plugin tree and from this repo's own cwd-relative imports.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HERMES_AGENT_ROOT = Path(
    os.environ.get("HERMES_AGENT_ROOT", "/Users/claytonduarte/.hermes/hermes-agent")
)


def _hermes_agent_importable() -> bool:
    return (HERMES_AGENT_ROOT / "hermes_cli" / "plugins.py").is_file()


pytestmark = pytest.mark.skipif(
    not _hermes_agent_importable(),
    reason="real Hermes agent checkout not found; loader-seam test needs it",
)


def _install_plugin_copy(dest_dir: Path) -> None:
    """Copy this repo's plugin surface (manifest, root entrypoint, deck_lab
    package) into ``dest_dir`` -- a real directory plugin the loader scans."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "plugin.yaml", dest_dir / "plugin.yaml")
    shutil.copy2(REPO_ROOT / "__init__.py", dest_dir / "__init__.py")
    shutil.copytree(REPO_ROOT / "deck_lab", dest_dir / "deck_lab")


@pytest.fixture
def loaded_manager(tmp_path, monkeypatch):
    """Discover-and-load through the REAL Hermes PluginManager from a neutral
    cwd, with this plugin installed as a user plugin under an isolated
    ``$HERMES_HOME``. Returns (manager, PluginContext-recorded tool names)."""
    # Left on sys.path for the whole test: the real loader's internals (e.g.
    # plugins_loader._track_tool_override_policy) import ``tools.registry`` by
    # absolute name lazily, mid-``discover_and_load``, not just at this import.
    if str(HERMES_AGENT_ROOT) not in sys.path:
        sys.path.insert(0, str(HERMES_AGENT_ROOT))
    from hermes_cli import plugins as plugins_mod

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Plugins are opt-in (plugins.enabled allow-list); user plugins are
    # otherwise gated to a "not enabled in config" placeholder before the
    # loader ever imports the module.
    (hermes_home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - hermes-mtg-plugin\n"
    )

    _install_plugin_copy(hermes_home / "plugins" / "hermes-mtg-plugin")

    # Deck Lab's own `deck_lab` package must be importable the way the real
    # plugin module resolves it (sibling of the copied __init__.py), and a
    # neutral cwd (not this repo) proves nothing relies on repo-relative cwd.
    neutral_cwd = tmp_path / "neutral-cwd"
    neutral_cwd.mkdir()
    monkeypatch.chdir(neutral_cwd)
    sys.path.insert(0, str(hermes_home / "plugins" / "hermes-mtg-plugin"))

    manager = plugins_mod.PluginManager()
    try:
        manager.discover_and_load()
        yield manager
    finally:
        sys.path.remove(str(hermes_home / "plugins" / "hermes-mtg-plugin"))
        sys.modules.pop("deck_lab", None)
        for mod_name in list(sys.modules):
            if mod_name.startswith("deck_lab."):
                sys.modules.pop(mod_name, None)


_EXPECTED_TOOL_NAMES = {
    "deck_list", "deck_get", "deck_validate", "deck_import", "deck_export",
}


def _registered_tool_names(manager) -> set[str]:
    """Names from this plugin's own scoped overlay (not the global registry),
    so this only sees what THIS plugin load actually registered."""
    from tools.registry import registry

    scope = manager.scope_key
    return {
        name for name in _EXPECTED_TOOL_NAMES
        if registry.snapshot_registration(name, scope=scope) is not None
    }


class TestRealLoaderDiscoversDeckLab:
    def test_root_entrypoint_registers_exactly_the_five_tools(self, loaded_manager):
        loaded = loaded_manager._plugins.get("hermes-mtg-plugin")
        assert loaded is not None, "real loader did not discover the plugin.yaml at all"
        assert loaded.error is None, f"plugin load failed: {loaded.error}"

        names = _registered_tool_names(loaded_manager)
        assert names == _EXPECTED_TOOL_NAMES

    def test_no_duplicate_registration_on_a_second_sweep(self, loaded_manager):
        """A forced re-discovery (gateway reload path) must not double-register
        or error on a name collision."""
        loaded_manager.discover_and_load(force=True)
        loaded = loaded_manager._plugins.get("hermes-mtg-plugin")
        assert loaded is not None and loaded.error is None
        assert _registered_tool_names(loaded_manager) == _EXPECTED_TOOL_NAMES


class TestMissingRootEntrypointFailsToLoad:
    """Deletion control: without the root ``register(ctx)`` entrypoint this
    card adds, the real loader must NOT be able to discover the five tools
    (reproduces the rejection on the prior PR #9 head)."""

    def test_plugin_without_root_init_has_no_register_function(self, tmp_path, monkeypatch):
        if str(HERMES_AGENT_ROOT) not in sys.path:
            sys.path.insert(0, str(HERMES_AGENT_ROOT))
        from hermes_cli import plugins as plugins_mod

        hermes_home = tmp_path / ".hermes"
        hermes_home.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (hermes_home / "config.yaml").write_text(
            "plugins:\n  enabled:\n    - hermes-mtg-plugin\n"
        )

        plugin_dir = hermes_home / "plugins" / "hermes-mtg-plugin"
        plugin_dir.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "plugin.yaml", plugin_dir / "plugin.yaml")
        shutil.copytree(REPO_ROOT / "deck_lab", plugin_dir / "deck_lab")
        # Deliberately NOT copying __init__.py -- reproduces the pre-fix state.

        neutral_cwd = tmp_path / "neutral-cwd"
        neutral_cwd.mkdir()
        monkeypatch.chdir(neutral_cwd)

        manager = plugins_mod.PluginManager()
        manager.discover_and_load()

        loaded = manager._plugins.get("hermes-mtg-plugin")
        assert loaded is not None, "manifest should still be found"
        assert loaded.error is not None
        assert "__init__.py" in loaded.error

        from tools.registry import registry
        scope = manager.scope_key
        assert registry.snapshot_registration("deck_list", scope=scope) is None
