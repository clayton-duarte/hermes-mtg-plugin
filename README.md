# hermes-mtg-plugin — Deck Lab

Deck Lab manages Magic: The Gathering decks as a plain Markdown + YAML
repository, inside your normal project folder, instead of locking your
decklists into a web app or a bespoke binary format. Hermes (CLI tools and
agents) and the desktop Deck Lab pane both read and write the exact same
`decks/` tree, so an agent edit, a hand edit, and the live pane view can never
drift from one another.

- **Why**: decks are source-controllable text. Validation errors point at an
  exact file and line. Tools that read/write decks (`deck_list`, `deck_get`,
  `deck_validate`, `deck_import`, `deck_export`) and the desktop pane all go
  through one shared service, so there is exactly one definition of "valid."
- **How**: see `docs/CONTRACT.md` for the terse file-format and tool
  reference, `docs/INSTALL.md` for installing/enabling the plugin, and
  `examples/minimal-repo/` for a complete, validating two-file deck.

## Quick start

```
git clone https://github.com/clayton-duarte/hermes-mtg-plugin.git
cd hermes-mtg-plugin
HERMES_HOME=/path/to/disposable/profile hermes plugins install . --enable
```

See `docs/INSTALL.md` for the profile-safe verification flow, independent
backend/desktop enable gates, and the gateway restart this requires.

## Repository layout you write

```
decks/
  <format>/<deck-slug>/
    README.md       # hermes-mtg/deck/v1 frontmatter + prose (not parsed as cards)
    mainboard.md    # hermes-mtg/board/v1 frontmatter + ## zone / ### category / ```decklist``` fences
    sideboard.md    # optional, kind: sideboard
    maybeboard.md   # optional, kind: maybeboard
```

`docs/CONTRACT.md` is the normative reference for every field, zone, error
code, and tool signature. This README does not repeat it.

## V1 scope (what this does NOT do)

- **Read/validate/import/export only** — there is no deckbuilding UI, no
  deck optimizer, no format legality checker.
- **One repository, one `decks/` root** — no multi-repository federation.
- **Scryfall enrichment is best-effort** — `deck_get`/`deck_validate
  (resolve_remote=true)` attach cached or live Scryfall projections, but an
  unresolved card is a warning (`REMOTE_CARD_UNRESOLVED`), never a hard
  validation failure; the canonical source of truth is always the Markdown,
  not the network.
- **Interchange is lossy both ways.** ManaBox/Arena plain text and
  Moxfield-bulk text cannot represent everything the Markdown contract can,
  and vice versa:
  - Markdown → ManaBox/Arena: **categories are dropped** (ManaBox/Arena has
    no category concept).
  - Markdown → Moxfield-bulk: category survives as a `#tag`, but finish
    markers (`*F*`, `*E*`, ...) round-trip only as provider-only markers
    Deck Lab strips back out on import (Deck Lab has no per-copy finish
    field).
  - Any import/export `losses` list in the tool/route response enumerates
    exactly what did not survive — never silently.

## Tools (agent-facing)

`deck_list`, `deck_get`, `deck_validate`, `deck_export` are read-only.
`deck_import` defaults to a dry run (render + validate, no write); writing
requires `apply=true`, `expected_hash` for any existing target, and
`overwrite=true` to replace an existing file. See `docs/CONTRACT.md` for
every parameter and error code.

## Cache & privacy

Scryfall responses are cached on disk (see `deck_lab.scryfall.ScryfallCache`,
wired through `DeckLabService(cache_path=...)`); nothing in this repository
phones home except batched Scryfall lookups needed to enrich card data, and
those are skippable (`resolve_remote=false`) or served from the cache alone
when no `http_client` is configured. No deck content ever leaves your
machine except the card identifiers (set code / collector number / name)
sent to Scryfall's public API.

## Troubleshooting

- **`PATH_OUTSIDE_DECKS_ROOT`**: every path a tool/route accepts must be
  repository-relative and begin with `decks/`; absolute paths, `..`, and
  symlink escapes are rejected before any file is touched.
- **A tool reports `No module named 'yaml'` or similar during `hermes
  plugins validate`**: re-run with `--install-deps` (see `docs/INSTALL.md`).
- **The desktop pane doesn't refresh after an edit**: it polls `/revision`
  every ~2s and only refetches when the revision or focused project changes;
  give it a couple of seconds, or check the gateway/backend is actually
  enabled and restarted (`docs/INSTALL.md`).
- **Contributor tests**: `pytest tests/ -q` from the repo root (install
  `PyYAML`, `fastapi`, `pytest` first). See `tests/README.md` for the exact
  command and expected result per lane.

## License

MIT. See `LICENSE`.
