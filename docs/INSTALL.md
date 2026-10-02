## Install & dev-sync (card t_f0bff516)

This repository ships ONE unified Hermes package: a backend half
(`plugin.yaml` + `dashboard/plugin_api.py`, five tools) and a desktop half
(`desktop/plugin.js`). Both halves install from this one repo but are
enabled/disabled independently.

### Profile-safe / disposable install

Never install into your daily-driver profile to validate this repo. Use a
disposable `HERMES_HOME` so nothing here can touch your real config,
sessions, or other plugins:

```
export HERMES_HOME=/tmp/hermes_scratch_home   # throwaway, not your real ~/.hermes
hermes plugins validate . --json --install-deps
```

`--install-deps` installs this plugin's declared Python dependencies (e.g.
`pyyaml`) into the interpreter `hermes` resolves, so the capability probe
inside `validate` can actually import them instead of failing with
`No module named 'yaml'`. `validate` returns a JSON report; the top-level
`"ok"` field must be `true` before treating the package as installable.

### Independent enable gates

The backend (tools + dashboard API routes) and the desktop pane are
separate enable surfaces:

```
hermes plugins enable hermes-mtg-plugin          # backend: tools + dashboard routes
```

```
# Desktop half: either symlink for live dev-sync (hot-reloads on save)...
ln -s "$(pwd)/desktop/plugin.js" "$HERMES_HOME/desktop-plugins/deck-lab/plugin.js"
# ...or let `hermes plugins install .` copy the desktop/ half in for a
# non-dev, static install.
```

A profile can run the backend half without the desktop half (e.g. a
headless/CLI-only profile using the five tools), or vice versa — enabling
one does not implicitly enable the other.

### Gateway / backend restart

Backend route and tool registration load at gateway start; a running
gateway does not pick up a newly-enabled backend plugin until restarted:

```
hermes serve --home "$HERMES_HOME" --restart   # or stop/start your gateway process
```

The desktop half does not need a gateway restart — the Electron app itself
watches `desktop-plugins/` and hot-reloads `plugin.js` within a few seconds
of a save.

### Cold-start inventory / contribution registration

After enabling the backend half and restarting the gateway, confirm the
five tools and the dashboard routes actually registered (not just that the
manifest declares them):

```
hermes plugins list --home "$HERMES_HOME" --json   # tools: deck_list, deck_get,
                                                     # deck_validate, deck_import,
                                                     # deck_export all present
```

### Live pane data

Once both halves are enabled and the gateway/desktop app are running
against a real deck repository (`workspace_root` = that repo's path), the
Deck Lab pane polls `/revision` every ~2s, refetches `/decks` and the
selected board's `/deck` whenever the revision changes or the focused
project (`host.state.cwd`) changes, and shows explicit loading/error/empty
states (see `desktop/plugin.js:1236-1282` and
`tests/test_ui_live_wiring.py`) rather than ever collapsing a request
failure into "Select a deck".

## Status

Backend (`plugin.yaml`, `dashboard/plugin_api.py`, five tools) and desktop
(`desktop/plugin.js`) halves are both implemented and wired to live data:
`/revision` drives a cheap polling cadence that invalidates `/decks` (list)
and the selected board's `/deck` (detail); selection persistence is keyed
by the live `repository_id`; loading/error/empty states are explicit at
both the repository and board level. See `tests/` for the executable and
contract-level test coverage per lane.
