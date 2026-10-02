/**
 * Deck Lab — MTG deck repository browser (decklist + reserved card preview).
 *
 * Runtime desktop plugin: plain ESM, loaded uncompiled, hot-reloads on save.
 * UI is jsx()/jsxs() calls -- JSX syntax will not parse here.
 *
 * FIXTURE-DRIVEN (t_e9b37fbc): every deck/board/category/card row below is a
 * faithful, non-fabricated transform of the landed golden Nelly Borca fixture
 * (tests/fixtures/nelly-borca/decks/commander/nelly-borca/{README,mainboard}.md),
 * conforming to the `hermes-mtg/service/v1` schema (see deck_lab/ui/fixture.py,
 * the Python source of truth this JS literal is generated from -- run
 * `python scripts/gen_deck_lab_fixture_js.py` to regenerate the block between
 * the FIXTURE_GENERATED_START/END markers below, and
 * `python scripts/gen_deck_lab_fixture_js.py --check` to verify it is in
 * sync; tests/test_ui_fixture_js_parity.py enforces this in CI. No Markdown
 * is read, no backend route is called, and no
 * scan/parse/scryfall lane is touched. Live routes, polling, and repository
 * refresh are the later integration card (t_f0bff516) -- this pane is
 * read-only against the fixture below.
 *
 * Fidelity to the golden board: exact quantity/name multiset (100 cards
 * total, 78 unique names, verified by tests/test_ui_fixture_invariants.py),
 * real tags (politics, goad), a single real `mainboard` board (Nelly has no
 * sideboard), and the real recursive category depth (Deck > Veggies >
 * Interaction > Removal, etc). Scryfall projection data is attached only for
 * verified real Scryfall records (fetched 2026-10-01); the `loading` and
 * `error` placeholder states are deterministically applied to real in-deck
 * card names (Agrus Kos, Spirit of Justice / Thought Vessel) -- no card or
 * deck name anywhere in this fixture is invented. The one invalid candidate
 * is projected from the existing golden malformed fixture
 * tests/fixtures/malformed/card_quantity_invalid_zero.md and visibly cites
 * that source.
 *
 * Geometry: the plugin registers docked right of `workspace` at `40vw`. The
 * whole desktop window is five regions (Hermes rail ~20% / chat ~40% / this
 * pane's decklist column ~20% / this pane's preview column ~20%); INSIDE this
 * ~40vw pane there are exactly two equal columns -- decklist (left) and
 * reserved card preview (right). PANE_COLUMN_COUNT in
 * deck_lab/ui/pane_contract.py locks that count at 2.
 */

import { Badge, Button, cn, Input, PANES_AREA, ScrollArea, SearchField, Tabs, TabsList, TabsTrigger, Tip, useQuery, useQueryClient } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useMemo, useState } from 'react'

const ID = 'deck-lab'

// --- Fixture data (hermes-mtg/service/v1) -----------------------------------
// FIXTURE/MOCK DATA ONLY. See file header for provenance/fidelity notes.
// --- FIXTURE_GENERATED_START ---
const FIXTURE = {
  schema: "hermes-mtg/service/v1",
  repository_id: "fixture-repo",
  decks: [
    {
      path: "decks/commander/nelly-borca",
      name: "Nelly Borca",
      format: "commander",
      color_identity: [
        "R",
        "W"
      ],
      status: "built",
      tags: [
        "politics",
        "goad"
      ],
      valid: true,
      errors: [],
      boards: [
        {
          path: "decks/commander/nelly-borca/mainboard.md",
          name: "Mainboard",
          kind: "mainboard",
          order: 10,
          valid: true,
          errors: [],
          categories: [
            {
              name: "Commander",
              path: [
                "Commander"
              ],
              cards: [
                {
                  quantity: 1,
                  name: "Nelly Borca, Impulsive Accuser",
                  scryfall: {
                    state: "cached",
                    name: "Nelly Borca, Impulsive Accuser",
                    oracle_id: "7ef5b2b6-86da-4e4a-9456-dcbb878936c4",
                    scryfall_id: "2ef59aa9-f5e1-413a-869b-d287db95efd0",
                    scryfall_uri: "https://scryfall.com/card/mkc/4/nelly-borca-impulsive-accuser?utm_source=api",
                    mana_cost: "{2}{R}{W}",
                    layout: "normal",
                    image_uris: {
                      normal: "https://cards.scryfall.io/normal/front/2/e/2ef59aa9-f5e1-413a-869b-d287db95efd0.jpg?1783913057"
                    },
                    card_faces: []
                  }
                }
              ]
            },
            {
              name: "Deck",
              path: [
                "Deck"
              ],
              cards: [],
              subcategories: [
                {
                  name: "Veggies",
                  path: [
                    "Deck",
                    "Veggies"
                  ],
                  cards: [],
                  subcategories: [
                    {
                      name: "Lands",
                      path: [
                        "Deck",
                        "Veggies",
                        "Lands"
                      ],
                      cards: [
                        {
                          quantity: 11,
                          name: "Mountain"
                        },
                        {
                          quantity: 13,
                          name: "Plains"
                        },
                        {
                          quantity: 1,
                          name: "Battlefield Forge"
                        },
                        {
                          quantity: 1,
                          name: "Boros Garrison"
                        },
                        {
                          quantity: 1,
                          name: "Clifftop Retreat"
                        },
                        {
                          quantity: 1,
                          name: "Command Tower"
                        },
                        {
                          quantity: 1,
                          name: "Exotic Orchard"
                        },
                        {
                          quantity: 1,
                          name: "Furycalm Snarl"
                        },
                        {
                          quantity: 1,
                          name: "Rugged Prairie"
                        },
                        {
                          quantity: 1,
                          name: "Sacred Peaks"
                        },
                        {
                          quantity: 1,
                          name: "Sunscorched Divide"
                        },
                        {
                          quantity: 1,
                          name: "Labyrinth of Skophos"
                        },
                        {
                          quantity: 1,
                          name: "Rogue's Passage"
                        },
                        {
                          quantity: 1,
                          name: "Reliquary Tower"
                        }
                      ]
                    },
                    {
                      name: "Ramp",
                      path: [
                        "Deck",
                        "Veggies",
                        "Ramp"
                      ],
                      cards: [
                        {
                          quantity: 1,
                          name: "Sol Ring",
                          scryfall: {
                            state: "cached",
                            name: "Sol Ring",
                            oracle_id: "6ad8011d-3471-4369-9d68-b264cc027487",
                            scryfall_id: "8ee443cc-e17a-493b-9c93-1f9e141a30e4",
                            scryfall_uri: "https://scryfall.com/card/frc/21/sol-ring?utm_source=api",
                            mana_cost: "{1}",
                            layout: "normal",
                            image_uris: {
                              normal: "https://cards.scryfall.io/normal/front/8/e/8ee443cc-e17a-493b-9c93-1f9e141a30e4.jpg?1789644446"
                            },
                            card_faces: []
                          }
                        },
                        {
                          quantity: 1,
                          name: "Arcane Signet"
                        },
                        {
                          quantity: 1,
                          name: "Boros Signet"
                        },
                        {
                          quantity: 1,
                          name: "Talisman of Conviction"
                        },
                        {
                          quantity: 1,
                          name: "Fellwar Stone"
                        },
                        {
                          quantity: 1,
                          name: "Everflowing Chalice"
                        },
                        {
                          quantity: 1,
                          name: "Liquimetal Torque"
                        },
                        {
                          quantity: 1,
                          name: "Thought Vessel",
                          scryfall: {
                            state: "error",
                            name: "Thought Vessel",
                            error: "REMOTE_CARD_UNRESOLVED"
                          }
                        },
                        {
                          quantity: 1,
                          name: "Wayfarer's Bauble"
                        },
                        {
                          quantity: 1,
                          name: "Knight of the White Orchid"
                        },
                        {
                          quantity: 1,
                          name: "Loyal Warhound"
                        },
                        {
                          quantity: 1,
                          name: "Keeper of the Accord"
                        }
                      ]
                    },
                    {
                      name: "Card Advantage",
                      path: [
                        "Deck",
                        "Veggies",
                        "Card Advantage"
                      ],
                      cards: [
                        {
                          quantity: 1,
                          name: "Cut a Deal"
                        },
                        {
                          quantity: 1,
                          name: "Secret Rendezvous"
                        },
                        {
                          quantity: 1,
                          name: "Joined Researchers // Secret Rendezvous",
                          scryfall: {
                            state: "cached",
                            name: "Joined Researchers // Secret Rendezvous",
                            oracle_id: "ec744a2d-4a33-4807-bce0-d95cd5277b1f",
                            scryfall_id: "1ebaafe0-3a9a-424c-8698-d26e7be45343",
                            scryfall_uri: "https://scryfall.com/card/sos/23/joined-researchers-secret-rendezvous?utm_source=api",
                            mana_cost: "{1}{W} // {1}{W}{W}",
                            layout: "prepare",
                            image_uris: {
                              normal: "https://cards.scryfall.io/normal/front/1/e/1ebaafe0-3a9a-424c-8698-d26e7be45343.jpg?1783903702"
                            },
                            card_faces: [
                              {
                                name: "Joined Researchers",
                                mana_cost: "{1}{W}",
                                image_uris: {}
                              },
                              {
                                name: "Secret Rendezvous",
                                mana_cost: "{1}{W}{W}",
                                image_uris: {}
                              }
                            ]
                          }
                        },
                        {
                          quantity: 1,
                          name: "Tenuous Truce"
                        },
                        {
                          quantity: 1,
                          name: "Key to the City"
                        },
                        {
                          quantity: 1,
                          name: "Mangara, the Diplomat"
                        }
                      ]
                    },
                    {
                      name: "Interaction",
                      path: [
                        "Deck",
                        "Veggies",
                        "Interaction"
                      ],
                      cards: [],
                      subcategories: [
                        {
                          name: "Removal",
                          path: [
                            "Deck",
                            "Veggies",
                            "Interaction",
                            "Removal"
                          ],
                          cards: [
                            {
                              quantity: 1,
                              name: "Path to Exile"
                            },
                            {
                              quantity: 1,
                              name: "Swords to Plowshares"
                            },
                            {
                              quantity: 1,
                              name: "Erode"
                            },
                            {
                              quantity: 1,
                              name: "Generous Gift"
                            },
                            {
                              quantity: 1,
                              name: "Chaos Warp"
                            },
                            {
                              quantity: 1,
                              name: "Loran of the Third Path"
                            },
                            {
                              quantity: 1,
                              name: "Requisition Raid"
                            }
                          ]
                        },
                        {
                          name: "Wipes",
                          path: [
                            "Deck",
                            "Veggies",
                            "Interaction",
                            "Wipes"
                          ],
                          cards: [
                            {
                              quantity: 1,
                              name: "Blasphemous Act"
                            },
                            {
                              quantity: 1,
                              name: "Chain Reaction"
                            },
                            {
                              quantity: 1,
                              name: "Promise of Loyalty"
                            }
                          ]
                        },
                        {
                          name: "Protection & Reflection",
                          path: [
                            "Deck",
                            "Veggies",
                            "Interaction",
                            "Protection & Reflection"
                          ],
                          cards: [
                            {
                              quantity: 1,
                              name: "Comeuppance"
                            },
                            {
                              quantity: 1,
                              name: "Deflecting Palm"
                            },
                            {
                              quantity: 1,
                              name: "Take the Bait"
                            },
                            {
                              quantity: 1,
                              name: "Selfless Squire"
                            },
                            {
                              quantity: 1,
                              name: "Your Temple Is Under Attack"
                            },
                            {
                              quantity: 1,
                              name: "Redirect Lightning"
                            },
                            {
                              quantity: 1,
                              name: "Reconnaissance"
                            },
                            {
                              quantity: 1,
                              name: "Lightning Greaves"
                            },
                            {
                              quantity: 1,
                              name: "Swiftfoot Boots"
                            },
                            {
                              quantity: 1,
                              name: "Brotherhood Regalia"
                            }
                          ]
                        }
                      ]
                    }
                  ]
                },
                {
                  name: "Gameplan",
                  path: [
                    "Deck",
                    "Gameplan"
                  ],
                  cards: [],
                  subcategories: [
                    {
                      name: "Theme \u2014 Goad & Suspect",
                      path: [
                        "Deck",
                        "Gameplan",
                        "Theme \u2014 Goad & Suspect"
                      ],
                      cards: [
                        {
                          quantity: 1,
                          name: "Agitator Ant"
                        },
                        {
                          quantity: 1,
                          name: "Agrus Kos, Spirit of Justice",
                          scryfall: {
                            state: "loading",
                            name: "Agrus Kos, Spirit of Justice"
                          }
                        },
                        {
                          quantity: 1,
                          name: "Alexios, Deimos of Kosmos"
                        },
                        {
                          quantity: 1,
                          name: "Bloodthirsty Blade"
                        },
                        {
                          quantity: 1,
                          name: "Disrupt Decorum"
                        },
                        {
                          quantity: 1,
                          name: "Geode Rager"
                        },
                        {
                          quantity: 1,
                          name: "Hot Pursuit"
                        },
                        {
                          quantity: 1,
                          name: "Martial Impetus"
                        },
                        {
                          quantity: 1,
                          name: "Shiny Impetus"
                        },
                        {
                          quantity: 1,
                          name: "Taunt from the Rampart"
                        },
                        {
                          quantity: 1,
                          name: "The Sound of Drums"
                        },
                        {
                          quantity: 1,
                          name: "Vengeful Ancestor"
                        }
                      ]
                    },
                    {
                      name: "Enablers \u2014 The Funnel",
                      path: [
                        "Deck",
                        "Gameplan",
                        "Enablers \u2014 The Funnel"
                      ],
                      cards: [
                        {
                          quantity: 1,
                          name: "Kazuul, Tyrant of the Cliffs"
                        },
                        {
                          quantity: 1,
                          name: "Nils, Discipline Enforcer"
                        },
                        {
                          quantity: 1,
                          name: "Noble Heritage"
                        },
                        {
                          quantity: 1,
                          name: "War Cadence"
                        },
                        {
                          quantity: 1,
                          name: "Duelist's Heritage"
                        },
                        {
                          quantity: 1,
                          name: "Curse of Opulence"
                        }
                      ]
                    },
                    {
                      name: "Payoffs \u2014 Damage Conversion & Finishers",
                      path: [
                        "Deck",
                        "Gameplan",
                        "Payoffs \u2014 Damage Conversion & Finishers"
                      ],
                      cards: [
                        {
                          quantity: 1,
                          name: "Brash Taunter"
                        },
                        {
                          quantity: 1,
                          name: "Stuffy Doll"
                        },
                        {
                          quantity: 1,
                          name: "Truefire Captain"
                        },
                        {
                          quantity: 1,
                          name: "Arcbond"
                        },
                        {
                          quantity: 1,
                          name: "Gisela, Blade of Goldnight"
                        },
                        {
                          quantity: 1,
                          name: "Aurelia, the Law Above"
                        },
                        {
                          quantity: 1,
                          name: "Insurrection"
                        }
                      ]
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    },
    {
      path: "tests/fixtures/malformed/card_quantity_invalid_zero",
      name: "malformed/card_quantity_invalid_zero.md (projected)",
      format: "commander",
      color_identity: [],
      status: "draft",
      tags: [],
      valid: false,
      errors: [
        {
          code: "CARD_QUANTITY_INVALID",
          message: "Quantity must be a positive integer",
          path: "tests/fixtures/malformed/card_quantity_invalid_zero.md",
          severity: "error",
          line: 13,
          context: "0 Sol Ring"
        }
      ],
      boards: []
    }
  ]
}
// --- FIXTURE_GENERATED_END ---


// --- Helpers -----------------------------------------------------------------

/** Compact mana cost: `{2}{R}{W}` -> `2RW`. Empty/undefined -> ''. */
function compactManaCost(manaCost) {
  if (!manaCost) return ''
  return manaCost.replace(/\{([^}]+)\}/g, '$1')
}

/** Sum of card quantities under a category, including all nested
 *  subcategories recursively (required behavior: counts reflect quantity,
 *  not row count). */
function categoryQuantityTotal(category) {
  let total = 0
  for (const card of category.cards ?? []) total += card.quantity
  for (const sub of category.subcategories ?? []) total += categoryQuantityTotal(sub)
  return total
}

/** Flatten a board's categories into a render-order list of
 *  { depth, name, path, cards, quantityTotal }, recursing through every
 *  nesting level (H3-H5 in the golden board), not just one. */
function flattenCategories(categories, depth = 0, rows = []) {
  for (const cat of categories ?? []) {
    rows.push({ depth, name: cat.name, path: cat.path, cards: cat.cards ?? [], quantityTotal: categoryQuantityTotal(cat) })
    flattenCategories(cat.subcategories, depth + 1, rows)
  }
  return rows
}

/** Group decks by format, each group itself split by status -- the picker's
 *  two-level grouping (\"Required behavior: Searchable picker grouped by
 *  format/status\"). */
function groupDecksByFormatAndStatus(decks, query) {
  const q = query.trim().toLowerCase()
  const filtered = q ? decks.filter(d => d.name.toLowerCase().includes(q)) : decks
  const byFormat = new Map()
  for (const deck of filtered) {
    if (!byFormat.has(deck.format)) byFormat.set(deck.format, new Map())
    const byStatus = byFormat.get(deck.format)
    if (!byStatus.has(deck.status)) byStatus.set(deck.status, [])
    byStatus.get(deck.status).push(deck)
  }
  return byFormat
}

// --- Components ----------------------------------------------------------------

/** Searchable deck picker, grouped by format then status. Selecting a deck
 *  persists per-repository (ctx.storage, keyed by repository_id) so a reload
 *  reopens the same deck. */
function DeckPicker({ decks, onSelect, query, selectedPath, setQuery }) {
  const grouped = useMemo(() => groupDecksByFormatAndStatus(decks, query), [decks, query])

  return jsxs('div', {
    className: 'flex min-h-0 flex-col',
    children: [
      jsx(SearchField, {
        'aria-label': 'Search decks',
        placeholder: 'Search decks…',
        value: query,
        onChange: event => setQuery(event.target.value)
      }),
      jsx(ScrollArea, {
        className: 'min-h-0 flex-1',
        children: jsx('div', {
          className: 'flex flex-col gap-2 p-1',
          children:
            grouped.size === 0
              ? jsx('div', { className: 'px-2 py-3 text-[0.75rem] text-(--ui-text-quaternary)', children: 'No decks match.' })
              : Array.from(grouped.entries()).map(([format, byStatus]) =>
                  jsxs('div', {
                    key: format,
                    children: [
                      jsx('div', {
                        className: 'px-2 pb-1 pt-2 text-[0.64rem] font-semibold uppercase tracking-[0.12em] text-(--ui-text-tertiary)',
                        children: format
                      }),
                      Array.from(byStatus.entries()).map(([status, deckList]) =>
                        jsxs('div', {
                          key: status,
                          className: 'flex flex-col gap-0.5',
                          children: [
                            jsx('div', {
                              className: 'px-2 text-[0.6rem] uppercase tracking-[0.1em] text-(--ui-text-quaternary)',
                              children: status
                            }),
                            deckList.map(deck =>
                              jsx(DeckPickerRow, {
                                key: deck.path,
                                deck,
                                selected: deck.path === selectedPath,
                                onSelect
                              })
                            )
                          ]
                        })
                      )
                    ]
                  })
                )
        })
      })
    ]
  })
}

function DeckPickerRow({ deck, onSelect, selected }) {
  return jsx(Tip, {
    label: deck.valid ? deck.name : `${deck.name} — invalid (${deck.errors[0]?.code ?? 'error'})`,
    children: jsxs('button', {
      type: 'button',
      className: cn(
        'flex w-full min-w-0 items-center gap-1.5 rounded px-2 py-1 text-left text-[0.75rem] hover:bg-(--ui-row-hover-background)',
        selected && 'bg-(--ui-row-hover-background)'
      ),
      onClick: () => onSelect(deck.path),
      children: [
        jsx('span', { className: 'min-w-0 flex-1 truncate', children: deck.name }),
        !deck.valid && jsx(Badge, { className: 'shrink-0', variant: 'destructive', children: 'invalid' })
      ]
    })
  })
}

/** One card row: fixed quantity, linked card name (activation opens the
 *  validated Scryfall URL and never toggles pin state), compact mana cost,
 *  hover/focus preview trigger, and a row-level click/tap pin that works
 *  without requiring hover first (architect correction: pin must not be
 *  hover-only). */
function CardRow({ card, ctx, isPinned, onHoverPreview, onPinToggle }) {
  const scry = card.scryfall ?? {}
  const state = scry.state ?? 'unresolved'
  const validUrl = typeof scry.scryfall_uri === 'string' && scry.scryfall_uri.startsWith('https://scryfall.com/')

  const openCard = event => {
    event.stopPropagation()
    if (state !== 'cached' || !validUrl) return
    void ctx.os.openExternal(scry.scryfall_uri)
  }

  // Row click/tap pins/unpins the row's card directly (no hover required);
  // the name button stops propagation so its own click only opens Scryfall.
  const onRowActivate = () => onPinToggle(card)

  return jsx('div', {
    role: 'group',
    'aria-label': card.name,
    className: cn(
      'group/card-row flex items-center gap-1.5 rounded px-2 py-0.5 text-[0.75rem] hover:bg-(--ui-row-hover-background)',
      isPinned && 'bg-(--ui-row-hover-background)'
    ),
    onMouseEnter: () => onHoverPreview(card),
    onFocus: () => onHoverPreview(card),
    onClick: onRowActivate,
    tabIndex: 0,
    children: [
      jsx('span', { className: 'w-6 shrink-0 text-right tabular-nums text-(--ui-text-tertiary)', children: card.quantity }),
      jsx('button', {
        type: 'button',
        className: cn(
          'min-w-0 flex-1 truncate text-left',
          state === 'cached' && validUrl ? 'hover:underline' : 'cursor-default',
          state === 'error' && 'text-destructive',
          state === 'loading' && 'text-(--ui-text-quaternary)'
        ),
        disabled: state !== 'cached' || !validUrl,
        onClick: openCard,
        children: card.name
      }),
      state === 'cached' && jsx('span', { className: 'shrink-0 text-(--ui-text-quaternary) tabular-nums', children: compactManaCost(scry.mana_cost) }),
      state === 'loading' && jsx('span', { className: 'shrink-0 text-(--ui-text-quaternary)', children: '…' }),
      state === 'error' && jsx('span', { className: 'shrink-0 text-destructive', children: '!' }),
      jsx(Tip, {
        label: isPinned ? 'Unpin preview' : 'Pin preview',
        children: jsx(Button, {
          'aria-label': isPinned ? 'Unpin preview' : 'Pin preview',
          className: cn('shrink-0 opacity-0 group-hover/card-row:opacity-100 group-focus-within/card-row:opacity-100', isPinned && 'opacity-100'),
          size: 'icon',
          variant: 'ghost',
          onClick: event => {
            event.stopPropagation()
            onPinToggle(card)
          },
          children: isPinned ? '📌' : '📍'
        })
      })
    ]
  })
}

/** Category header + its card rows. Recurses through every nested level
 *  (flattenCategories already expanded depth), and shows a quantity-summed
 *  count, not a row count. */
function CategoryBlock({ ctx, onHoverPreview, onPinToggle, pinnedName, row }) {
  // Runtime-safe indentation: a bounded inline marginLeft, not a dynamically
  // synthesized `ml-${n}` utility class (the uncompiled host only ships the
  // literal classes it was built with, so an on-the-fly `ml-6` never takes
  // effect and deep categories visually collapse).
  const indentPx = Math.min(row.depth, 5) * 12
  return jsxs('div', {
    className: 'flex flex-col',
    style: indentPx > 0 ? { marginLeft: `${indentPx}px` } : undefined,
    children: [
      jsxs('div', {
        className: 'flex items-center gap-1.5 px-2 pb-0.5 pt-1.5 text-[0.64rem] font-semibold uppercase tracking-[0.1em] text-(--ui-text-tertiary)',
        children: [
          jsx('span', { children: row.name }),
          jsx('span', { className: 'tabular-nums text-(--ui-text-quaternary)', children: row.quantityTotal })
        ]
      }),
      row.cards.map(card =>
        jsx(CardRow, {
          key: card.name,
          card,
          ctx,
          isPinned: pinnedName === card.name,
          onHoverPreview,
          onPinToggle
        })
      )
    ]
  })
}

/** Decklist column: board tabs + one main scroller over nested categories. */
function DecklistColumn({ boardIndex, ctx, deck, onBoardChange, onHoverPreview, onPinToggle, pinnedName }) {
  if (!deck) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center p-4 text-center text-[0.75rem] text-(--ui-text-quaternary)',
      children: 'Select a deck from the picker to view its boards.'
    })
  }

  if (!deck.valid) {
    return jsxs('div', {
      className: 'flex h-full flex-col gap-2 p-3 text-[0.75rem]',
      children: [
        jsx('div', { className: 'font-semibold text-destructive', children: 'This deck is invalid.' }),
        deck.errors.map((error, index) =>
          jsxs('div', { key: index, className: 'text-(--ui-text-tertiary)', children: [error.code, ': ', error.message] })
        )
      ]
    })
  }

  if (!deck.boards || deck.boards.length === 0) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center p-4 text-center text-[0.75rem] text-(--ui-text-quaternary)',
      children: 'No boards found for this deck.'
    })
  }

  const board = deck.boards[boardIndex] ?? deck.boards[0]
  const rows = flattenCategories(board.categories)

  return jsxs('div', {
    className: 'flex min-h-0 flex-1 flex-col',
    children: [
      jsx(Tabs, {
        value: String(boardIndex),
        onValueChange: value => onBoardChange(Number(value)),
        children: jsx(TabsList, {
          children: deck.boards.map((b, index) =>
            jsx(TabsTrigger, { key: b.path, value: String(index), children: b.name }, b.path)
          )
        })
      }),
      jsx(ScrollArea, {
        className: 'min-h-0 flex-1',
        children:
          rows.length === 0
            ? jsx('div', { className: 'p-3 text-[0.75rem] text-(--ui-text-quaternary)', children: 'This board is empty.' })
            : jsx('div', { className: 'flex flex-col pb-2', children: rows.map(row => jsx(CategoryBlock, { key: row.path.join('/'), ctx, row, onHoverPreview, onPinToggle, pinnedName })) })
      })
    ]
  })
}

/** Reserved card preview column: hover/focus-driven unless pinned, shows
 *  cached/loading/error placeholders and a DFC face toggle. When a face has
 *  no per-face image (e.g. the real `prepare`-layout Joined Researchers //
 *  Secret Rendezvous), falls back to the real combined top-level image
 *  rather than showing nothing. */
function PreviewColumn({ card, onFaceToggle, pinned, faceIndex }) {
  if (!card) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center p-4 text-center text-[0.75rem] text-(--ui-text-quaternary)',
      children: 'Hover or focus a card to preview it here.'
    })
  }

  const scry = card.scryfall ?? {}
  const state = scry.state ?? 'unresolved'
  const hasFaces = Array.isArray(scry.card_faces) && scry.card_faces.length > 1
  const face = hasFaces ? scry.card_faces[faceIndex % scry.card_faces.length] : null
  const imageUrl = (hasFaces ? face?.image_uris?.normal : null) ?? scry.image_uris?.normal

  return jsxs('div', {
    className: 'flex h-full flex-col gap-2 p-3',
    children: [
      jsxs('div', {
        className: 'flex items-center gap-1.5',
        children: [
          jsx('span', { className: 'min-w-0 flex-1 truncate text-[0.8rem] font-semibold', children: hasFaces ? face?.name ?? card.name : card.name }),
          pinned && jsx(Badge, { variant: 'outline', children: 'pinned' })
        ]
      }),
      state === 'loading' &&
        jsx('div', { className: 'flex h-48 items-center justify-center rounded bg-(--ui-row-hover-background) text-[0.75rem] text-(--ui-text-quaternary)', children: 'Loading…' }),
      state === 'error' &&
        jsx('div', { className: 'flex h-48 flex-col items-center justify-center gap-1 rounded bg-(--ui-row-hover-background) p-2 text-center text-[0.75rem] text-destructive', children: [
          jsx('span', { children: 'Could not resolve this card.' }),
          jsx('span', { className: 'text-(--ui-text-quaternary)', children: scry.error ?? 'REMOTE_CARD_UNRESOLVED' })
        ] }),
      (state === 'cached' || state === 'unresolved') &&
        jsxs('div', {
          className: 'flex flex-col gap-2',
          children: [
            imageUrl
              ? jsx('img', { alt: hasFaces ? face?.name ?? card.name : card.name, className: 'w-full rounded', src: imageUrl })
              : jsx('div', { className: 'flex h-48 items-center justify-center rounded bg-(--ui-row-hover-background) text-[0.75rem] text-(--ui-text-quaternary)', children: 'No art cached' }),
            hasFaces &&
              jsx(Button, {
                size: 'sm',
                variant: 'outline',
                onClick: () => onFaceToggle(),
                children: `Show ${scry.card_faces[(faceIndex + 1) % scry.card_faces.length].name}`
              }),
            jsx('div', { className: 'text-[0.7rem] text-(--ui-text-tertiary)', children: compactManaCost(hasFaces ? face?.mana_cost : scry.mana_cost) })
          ]
        })
    ]
  })
}

/** Root pane: searchable picker + board tabs + decklist column + reserved
 *  preview column -- exactly two equal plugin columns (PANE_COLUMN_COUNT). */
function DeckLabPane({ ctx }) {
  const qc = useQueryClient()
  const storageKey = `${ID}:selected-deck:${FIXTURE.repository_id}`

  // Persisted selection per repository (ctx.storage mirrors localStorage
  // semantics for a plugin; falls back to the first deck on first run).
  const [selectedPath, setSelectedPath] = useState(() => ctx?.storage?.get?.(storageKey) ?? FIXTURE.decks[0]?.path ?? null)
  const [boardIndex, setBoardIndex] = useState(0)
  const [query, setQuery] = useState('')
  const [hoveredCard, setHoveredCard] = useState(null)
  const [pinnedCard, setPinnedCard] = useState(null)
  const [faceIndex, setFaceIndex] = useState(0)

  // Fixture is static, but routed through useQuery so the pane's data-fetch
  // shape matches what the live integration lane (t_f0bff516) will replace
  // this with -- a real ctx.rest('/decks') call -- without restructuring the
  // render tree.
  const { data } = useQuery({
    queryKey: [ID, 'fixture'],
    queryFn: () => Promise.resolve(FIXTURE),
    staleTime: Infinity
  })

  const decks = data?.decks ?? []
  const selectedDeck = decks.find(d => d.path === selectedPath) ?? null

  const selectDeck = path => {
    setSelectedPath(path)
    setBoardIndex(0)
    setPinnedCard(null)
    setFaceIndex(0)
    ctx?.storage?.set?.(storageKey, path)
  }

  const onHoverPreview = card => {
    if (pinnedCard) return
    setHoveredCard(card)
    setFaceIndex(0)
  }

  // Pin toggles regardless of hover state -- satisfies the click/tap pin
  // requirement independent of pointer-hover affordances.
  const onPinToggle = card => {
    setPinnedCard(prev => (prev && prev.name === card.name ? null : card))
    setFaceIndex(0)
  }

  const activeCard = pinnedCard ?? hoveredCard

  return jsxs('div', {
    className: 'flex h-full w-full',
    children: [
      jsxs('div', {
        className: 'flex min-h-0 w-1/2 flex-col border-r border-(--ui-border)',
        children: [
          jsx('div', { className: 'shrink-0 p-2', children: jsx(DeckPicker, { decks, query, setQuery, selectedPath, onSelect: selectDeck }) }),
          jsx(DecklistColumn, {
            deck: selectedDeck,
            boardIndex,
            ctx,
            onBoardChange: setBoardIndex,
            onHoverPreview,
            onPinToggle,
            pinnedName: pinnedCard?.name ?? null
          })
        ]
      }),
      jsx('div', {
        className: 'min-h-0 w-1/2',
        children: jsx(PreviewColumn, {
          card: activeCard,
          pinned: Boolean(pinnedCard),
          faceIndex,
          onFaceToggle: () => setFaceIndex(i => i + 1)
        })
      })
    ]
  })
}

export default {
  id: ID,
  register(ctx) {
    ctx.register({
      id: ID,
      area: PANES_AREA,
      title: 'Deck Lab',
      data: {
        placement: 'right',
        dock: { pane: 'workspace', pos: 'right' },
        width: '40vw'
      },
      render: () => jsx(DeckLabPane, { ctx })
    })
  }
}
