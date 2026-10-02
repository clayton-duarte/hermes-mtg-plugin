# hermes-mtg-plugin

Deck Lab: Magic: The Gathering deck repository tooling for Hermes Agent.

This repository implements the V1 file contract defined in the project plan.
Locked schema identifiers:

- `hermes-mtg/deck/v1`
- `hermes-mtg/board/v1`
- `hermes-mtg/service/v1`

## Status

This card (`t_09171717`) locks the contract fixtures and model only. Parser,
scanner, Scryfall resolver, interchange adapters, and the desktop pane are
separate, downstream lanes -- see `tests/` for the RED tests that define each
lane's contract surface.

## Fixtures

- `tests/fixtures/nelly-borca/` — valid golden deck repository (100 cards
  including commander).
- `tests/fixtures/malformed/` — one fixture per contract violation family.
- `tests/fixtures/interchange/` — ManaBox/Arena/Moxfield-bulk sample text for
  adapter round-trip tests.

## Running tests

```
pytest tests/ -q
```

See `tests/README.md` for the exact command per lane and the expected RED
assertion failure (contract has no implementation yet in this card).

## License

MIT. See `LICENSE`.
