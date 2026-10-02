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

Each lane's RED test currently fails because the corresponding production
module does not exist yet (`ModuleNotFoundError` is the *intended* RED signal
for this contract card; the assertion-level failure lands once the module
exists and the promoted lane is actively implementing against it).

- Parser/validator lane (`t_09bc9ceb`):
  `pytest tests/test_parser_lane_contract.py -q`
- Scanner lane (`t_eb91eeab`):
  `pytest tests/test_scanner_lane_contract.py -q`
- Scryfall resolver lane (`t_5d228091`):
  `pytest tests/test_scryfall_lane_contract.py -q`
- ManaBox/Arena adapter lane (`t_21314a59`):
  `pytest tests/test_adapter_lane_contract.py -q`
- Moxfield bulk adapter lane (`t_e5e51273`):
  `pytest tests/test_moxfield_lane_contract.py -q`
- Desktop pane lane (`t_e9b37fbc`):
  `pytest tests/test_ui_lane_contract.py -q`

Once a lane's module exists, its RED test must fail on the assertion inside
the test body (e.g. wrong parsed count, wrong error code), not on import.
