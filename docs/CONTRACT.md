# Deck Lab file & service contract (`hermes-mtg/*/v1`)

Terse, normative reference. Rationale lives in `README.md`; this file is
cross-linked, not re-derived. Source of truth for every claim here:
`deck_lab/models.py` (schema identifiers, dataclasses, error codes),
`deck_lab/parser.py`, `deck_lab/scanner.py`, `deck_lab/service.py`,
`deck_lab/tools.py`, `dashboard/plugin_api.py`.

## Schema identifiers

| Constant | Value |
|---|---|
| `DECK_SCHEMA_V1` | `hermes-mtg/deck/v1` |
| `BOARD_SCHEMA_V1` | `hermes-mtg/board/v1` |
| `SERVICE_SCHEMA_V1` | `hermes-mtg/service/v1` |

## Repository layout

```
<workspace_root>/decks/<format-or-category>/<deck-slug>/
  README.md        # hermes-mtg/deck/v1
  mainboard.md      # hermes-mtg/board/v1, kind: mainboard
  sideboard.md       # optional, kind: sideboard
  maybeboard.md      # optional, kind: maybeboard
```

All service/tool paths are repository-relative and MUST begin with `decks/`
(or be exactly `decks`). Any other path raises `PATH_OUTSIDE_DECKS_ROOT`.

## `decks/<deck>/README.md` (`hermes-mtg/deck/v1`)

YAML frontmatter fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema` | string | yes | must equal `hermes-mtg/deck/v1` |
| `name` | string | yes | |
| `format` | string | yes | e.g. `commander` |
| `color_identity` | list of `W/U/B/R/G/C` | yes | invalid member rejected |
| `status` | string | yes | free text (e.g. `built`, `brewing`) |
| `tags` | list of string | no | |

Body prose after frontmatter is never parsed as a card list.

## `decks/<deck>/<board>.md` (`hermes-mtg/board/v1`)

YAML frontmatter:

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema` | string | yes | must equal `hermes-mtg/board/v1` |
| `name` | string | yes | |
| `kind` | `mainboard \| sideboard \| maybeboard` | yes | |
| `order` | int | yes | lowest-`order` board is the deck's default board |
| `description` | string | no | |

Body structure: `## Zone` → `### Category` → one or more fenced
` ```decklist ` blocks of `<qty> <card name> [(SET) [collector-number]]` rows.

Allowed H2 zones per `kind`:

| `kind` | allowed zones |
|---|---|
| `mainboard` | `Commander`, `Deck` |
| `sideboard` | `Sideboard` |
| `maybeboard` | `Maybeboard` |

A zone may appear at most once per board (`ZONE_DUPLICATE` otherwise). A
category heading is required directly under a zone before any `decklist`
fence (`CATEGORY_LEVEL_SKIPPED`/`DECKLIST_FENCE_NO_CATEGORY` otherwise).

## Validation error codes

`code`, `message`, `path`, `severity` (`error`|`warning`), optional `line`,
optional `context` — `deck_lab.models.ValidationError`.

```
DECK_FRONTMATTER_MISSING, DECK_FRONTMATTER_INVALID, DECK_SCHEMA_UNSUPPORTED,
BOARD_FRONTMATTER_MISSING, BOARD_FRONTMATTER_INVALID, BOARD_SCHEMA_UNSUPPORTED,
BOARD_KIND_INVALID, ZONE_INVALID_FOR_BOARD, ZONE_DUPLICATE,
CATEGORY_LEVEL_SKIPPED, DECKLIST_FENCE_INVALID, CARD_OUTSIDE_DECKLIST,
CARD_ROW_INVALID, CARD_QUANTITY_INVALID, CARD_PRINTING_INCOMPLETE,
REMOTE_CARD_UNRESOLVED, PATH_OUTSIDE_DECKS_ROOT
```

`REMOTE_CARD_UNRESOLVED` is always `severity: warning` — an unresolved
Scryfall lookup never invalidates otherwise-correct Markdown. All other
codes above default to `severity: error` when raised.

Every fixture under `tests/fixtures/malformed/` reproduces exactly one of
these codes; see that directory for a minimal repro per code.

## Service response envelope

Every `DeckLabService` method and every tool/route response carries
`"schema": "hermes-mtg/service/v1"`. Errors are
`DeckLabServiceError.to_dict()`:

```json
{"schema": "hermes-mtg/service/v1",
 "error": {"code": "...", "message": "...", "path": "...",
           "status": 400, "category": "client|not_found|conflict|server"}}
```

## Tools (`deck_lab/tools.py`, registered by `plugin.yaml`)

All tools accept an optional `workspace_root` (defaults to the process cwd).
Response is a UTF-8 JSON string bounded at 200,000 bytes
(`RESPONSE_TOO_LARGE` error if exceeded).

| Tool | Required args | Key optional args | Mutates? |
|---|---|---|---|
| `deck_list` | — | `limit` (int, ≤1000, default 200) | no |
| `deck_get` | `deck_path` | `board_path`, `resolve_remote` (default `true`) | no |
| `deck_validate` | `target_path` | `resolve_remote` (default `false`) | no |
| `deck_export` | `deck_path`, `dialect` (`manabox\|arena\|moxfield-bulk`) | `board_path` | no |
| `deck_import` | `dialect`, `target_deck_path` | `target_board_path`, `text` XOR `source_file`, `apply` (default `false`), `expected_hash`, `overwrite` (default `false`) | yes, only when `apply=true` |

`deck_validate`'s `target_path` may be `decks` (whole-repository summary),
a deck directory, or a single board/README file — the response shape
differs accordingly (see `DeckLabService.validate` docstring-equivalent in
`deck_lab/service.py`).

`deck_import` apply semantics: creating a new file requires
`expected_hash=None` and `overwrite=false`; overwriting an existing file
requires `overwrite=true` and `expected_hash` matching the current
sha256 (`IMPORT_HASH_REQUIRED` / `IMPORT_OVERWRITE_REQUIRED` /
`IMPORT_HASH_MISMATCH` otherwise). Writes are atomic (tempfile + `os.replace`)
and the write is re-checked for concurrent modification immediately before
replacing (`IMPORT_CONCURRENT_MODIFICATION`).

## Dashboard routes (`dashboard/plugin_api.py`)

Thin, unparsing wrappers over the same service — same request/response
shapes as the tools above, as HTTP:

| Method | Path | Mirrors |
|---|---|---|
| GET | `/revision` | repository content-hash/revision, for poll-driven cache invalidation |
| GET | `/decks` | `deck_list` |
| GET | `/deck` | `deck_get` |
| GET | `/validate` | `deck_validate` |
| GET | `/scryfall/cache-status` | cache introspection only |
| POST | `/import` | `deck_import` |
| POST | `/export` | `deck_export` |

`workspace_root` is a query param on GET routes and a body field on POST
routes; it is resolved relative to the dashboard server process's cwd when
relative.

## Interchange dialects (`deck_lab/adapters/`)

`manabox`, `arena`: plain `<qty> <name> [(SET) [#]] [*finish*]` rows under
`Commander`/`Deck`/`Sideboard`/`Maybeboard` plaintext headers. No category
concept — exporting Markdown with categories drops them
(`losses: ["categories are not representable in ManaBox/Arena plain text..."]`).

`moxfield-bulk`: `<qty> <name> [(SET) <#>] [*finish*] [#category]` rows.
Category round-trips as a `#tag`; finish markers are stripped on import
(no per-copy finish field in the Deck Lab model) and any loss is reported
in `export_deck`'s `losses` list.

## Minimal compatible example

`examples/minimal-repo/decks/commander/krenko-goblins/` — one deck, one
board, 24 cards. Validates clean:

```
$ python -c "from deck_lab.service import DeckLabService; import json; \
  print(json.dumps(DeckLabService('examples/minimal-repo').validate('decks', resolve_remote=False)))"
{"schema": "hermes-mtg/service/v1", "target": "decks", "valid": true,
 "deck_count": 1, "valid_count": 1, "invalid_count": 0, "errors": [],
 "remote_resolved": false, "remote_unresolved_count": 0, "remote_warnings": []}
```
