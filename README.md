# hermes-mtg-plugin

Deck Lab: Magic: The Gathering deck repository tooling for Hermes Agent.

This repository implements the V1 file contract defined in the project plan.
Locked schema identifiers:

- `hermes-mtg/deck/v1`
- `hermes-mtg/board/v1`
- `hermes-mtg/service/v1`

## Status

Backend (`plugin.yaml`, `dashboard/plugin_api.py`, five tools) and desktop
(`desktop/plugin.js`) halves are both implemented and wired to live API
data (not the bundled fixture): `/revision` drives a cheap ~2s poll that
invalidates `/decks` (list) and the selected board's `/deck` (detail);
selection persistence is keyed by the live repository identity. See
`docs/INSTALL.md` for the profile-safe install/dev-sync flow, independent
backend/desktop enable gates, gateway restart, and cold-start inventory
instructions.

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
