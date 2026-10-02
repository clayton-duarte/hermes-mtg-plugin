# Minimal compatible repository example

One commander deck, one board (`mainboard.md`), 24 cards (23 + commander).
Validates clean with no network access:

```
$ cd hermes-mtg-plugin
$ python3 -c "
import sys; sys.path.insert(0, '.')
from deck_lab.service import DeckLabService
import json
print(json.dumps(DeckLabService('examples/minimal-repo').validate('decks', resolve_remote=False), indent=2))
"
```

Expected output:

```json
{
  "schema": "hermes-mtg/service/v1",
  "target": "decks",
  "valid": true,
  "deck_count": 1,
  "valid_count": 1,
  "invalid_count": 0,
  "errors": [],
  "remote_resolved": false,
  "remote_unresolved_count": 0,
  "remote_warnings": []
}
```

See `docs/CONTRACT.md` for the field-by-field format this repository follows.
