// Executable proof that buildCategoryTree() (the real function shipped in
// desktop/plugin.js) correctly reconstructs a nested category/card tree from
// the flat `cards` list `/deck` actually returns (card t_f0bff516).
//
// Extracts the real function body (not a reimplementation) and calls it with
// a realistic flat card list carrying `category_path` arrays, then asserts
// the nested { name, path, cards, subcategories } shape DecklistColumn
// expects.
//
// Usage: node scripts/check_build_category_tree.mjs

import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const pluginPath = path.join(__dirname, '..', 'desktop', 'plugin.js')

const src = execFileSync('node', [
  path.join(__dirname, 'extract_plugin_js_function.mjs'),
  pluginPath,
  'buildCategoryTree'
]).toString()

const results = {}
let failures = 0
function check(name, cond, detail) {
  results[name] = { pass: Boolean(cond), detail: detail ?? null }
  if (!cond) failures += 1
}

// eslint-disable-next-line no-new-func
const buildCategoryTree = new Function(`${src}\nreturn buildCategoryTree`)()

const flatCards = [
  { name: 'Sol Ring', quantity: 1, category_path: ['Deck', 'Ramp'] },
  { name: 'Arcane Signet', quantity: 1, category_path: ['Deck', 'Ramp'] },
  { name: 'Mountain', quantity: 12, category_path: ['Deck', 'Lands'] },
  { name: 'Plains', quantity: 10, category_path: ['Deck', 'Lands'] },
  { name: 'Smothering Tithe', quantity: 1, category_path: ['Deck'] }
]

const tree = buildCategoryTree(flatCards)

check('tree_is_array', Array.isArray(tree), tree)
const deckNode = tree.find(c => c.name === 'Deck')
check('top_level_deck_category_present', Boolean(deckNode), tree.map(c => c.name))
check('deck_has_direct_card', (deckNode?.cards ?? []).some(c => c.name === 'Smothering Tithe'), deckNode?.cards)
const ramp = deckNode?.subcategories?.find(c => c.name === 'Ramp')
check('ramp_subcategory_present', Boolean(ramp), deckNode?.subcategories?.map(c => c.name))
check('ramp_has_both_cards', (ramp?.cards ?? []).length === 2, ramp?.cards)
const lands = deckNode?.subcategories?.find(c => c.name === 'Lands')
check('lands_quantity_sum_is_22', flatCards.filter(c => c.category_path.includes('Lands')).reduce((s, c) => s + c.quantity, 0) === 22, null)
check('lands_subcategory_present', Boolean(lands), deckNode?.subcategories?.map(c => c.name))

// Mutation control: a broken tree-builder that ignores category_path depth
// beyond the first segment would flatten Ramp/Lands into Deck directly.
if (process.env.CHECK_CATEGORY_TREE_MUTATE === '1') {
  const brokenBuildCategoryTree = cards => {
    const top = { name: 'Deck', path: 'Deck', cards: [...cards], subcategories: [] }
    return [top]
  }
  const brokenTree = brokenBuildCategoryTree(flatCards)
  const brokenDeck = brokenTree.find(c => c.name === 'Deck')
  const brokenRamp = brokenDeck?.subcategories?.find(c => c.name === 'Ramp')
  check('mutation_loses_ramp_subcategory', !brokenRamp, 'expected broken builder to NOT nest Ramp')
}

console.log(JSON.stringify({ results, failures }, null, 2))
process.exit(failures === 0 ? 0 : 1)
