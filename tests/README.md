# Fixture self-validation and lane RED tests

Run everything:

```
pytest tests/ -q
```

## Contract card (this card)

```
pytest tests/test_contract_fixtures.py -q
```

Expected: PASS. This is the self-validating fixture/model layer this card
owns -- no production parser/scanner/network/UI code is implemented here.

## Promoted implementation lanes

Each lane module now exists as a minimal importable skeleton (a sentinel
function/constant with no real parser/scanner/network/adapter/UI behavior).
Each lane's RED test therefore imports successfully and fails at its named
assertion -- not at import, collection, or `NotImplementedError`.

- Parser/validator lane (`t_09bc9ceb`):
  `pytest tests/test_parser_lane_contract.py -q`
  fails at `assert total == 100` (`deck_lab.parser.parse_board` returns no
  cards yet).
- Scanner lane (`t_eb91eeab`):
  `pytest tests/test_scanner_lane_contract.py -q`
  fails at `assert any(...)` (`deck_lab.scanner.scan_repository` returns no
  deck summaries yet).
- Scryfall resolver lane (`t_5d228091`):
  `pytest tests/test_scryfall_lane_contract.py -q`
  fails at `assert all(len(batch) <= 75 ...)` (`deck_lab.scryfall.resolve_collection`
  does not batch identifiers yet).
- ManaBox/Arena adapter lane (`t_21314a59`):
  `pytest tests/test_adapter_lane_contract.py -q`
  fails at `assert len(commander_rows) == 1` (`deck_lab.adapters.manabox_arena.import_text`
  does not parse zone headers yet).
- Moxfield bulk adapter lane (`t_e5e51273`):
  `pytest tests/test_moxfield_lane_contract.py -q`
  fails looking up the card by name (`deck_lab.adapters.moxfield_bulk.import_text`
  does not strip provider-only finish markers yet, so the row name still
  carries `*F*` and the lookup by bare name finds nothing).
- Desktop pane lane (`t_e9b37fbc`):
  `pytest tests/test_ui_lane_contract.py -q`
  fails at `assert PANE_COLUMN_COUNT == 2` (`deck_lab.ui.pane_contract`
  declares a deliberately wrong sentinel value of `1`).

Once a lane implements real behavior, its RED test must keep failing on the
assertion inside the test body (e.g. wrong parsed count, wrong error code)
until the lane's own implementation makes it pass for real.
