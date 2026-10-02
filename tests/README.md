# Running the test suite

```
PYTHONPATH=. uv run --with pytest --with fastapi --with httpx \
  --with 'ruamel.yaml' --with pyyaml --with python-multipart \
  --with psutil --with python-dotenv pytest -q tests/
```

This dependency-isolated command is the acceptance path used by maintainers;
it also makes `fastapi` and Hermes' YAML support available to subprocess tests.
See `docs/INSTALL.md` for profile-safe plugin validation. The suite is expected
to finish with no failures or errors (platform-specific tests may skip when
their external host surface is unavailable).

## Lane map

Every parser/scanner/Scryfall/adapter/service/UI lane is implemented; each
test file below is that lane's executable contract, not a placeholder:

- `tests/test_contract_fixtures.py` — fixture/model self-validation
  (`deck_lab/models.py`, locked schema identifiers).
- `tests/test_parser_lane_contract.py`,
  `tests/test_parser_strict_contract_coverage.py` — board/README Markdown
  parser and validator (`deck_lab/parser.py`); one malformed fixture per
  error code under `tests/fixtures/malformed/`.
- `tests/test_scanner_lane_contract.py`, `tests/test_scanner_behavior.py`,
  `tests/test_scanner_corrections.py` — repository scan and revision
  (`deck_lab/scanner.py`).
- `tests/test_scryfall_lane_contract.py`, `tests/test_scryfall_resolver.py`
  — batched Scryfall resolution and on-disk cache (`deck_lab/scryfall.py`).
- `tests/test_adapter_lane_contract.py`, `tests/test_manabox_arena_adapter.py`
  — ManaBox/Arena plain-text import/export
  (`deck_lab/adapters/manabox_arena.py`).
- `tests/test_moxfield_lane_contract.py`, `tests/test_moxfield_bulk_adapter.py`
  — Moxfield-bulk import/export (`deck_lab/adapters/moxfield_bulk.py`).
- `tests/test_service_lane_contract.py`, `tests/test_service_behavior.py`,
  `tests/test_service_defect_corrections.py` — the shared orchestration
  boundary (`deck_lab/service.py`): path safety, list/get/validate/
  import/export, atomic writes, hash preconditions.
- `tests/test_ui_lane_contract.py` — desktop pane contract sentinel
  (`deck_lab/ui/pane_contract.py`).
- `tests/test_plugin_api_lane_contract.py` — FastAPI route wrappers
  (`dashboard/plugin_api.py`), including the standalone-file-import
  constraint the real dashboard loader relies on.
- `tests/test_ui_live_wiring.py` — desktop pane (`desktop/plugin.js`) live
  `/revision`-poll wiring, cache invalidation, and loading/error/empty
  states.
