// Executable proof that restQuery() never produces a malformed URL with two
// `?` characters, regardless of whether the input path already has a query
// string (card t_f0bff516, review finding 1).
//
// This extracts the REAL restQuery function body out of desktop/plugin.js
// (scripts/extract_plugin_js_function.mjs), wraps it in a tiny harness that
// supplies `workspaceRoot`, and calls it with two distinct focused roots and
// both a bare path and a path that already has `?path=...&board_path=...`,
// then parses the resulting URL with the real URL/URLSearchParams API and
// asserts workspace_root/path/board_path all come back as distinct, correct
// params -- not a source grep.
//
// Usage: node scripts/check_restquery_workspace_root.mjs
// Exit 0 + all pass:true on success.

import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const pluginPath = path.join(__dirname, '..', 'desktop', 'plugin.js')

const restQuerySrc = execFileSync('node', [
  path.join(__dirname, 'extract_plugin_js_function.mjs'),
  pluginPath,
  'restQuery'
]).toString()

const results = {}
let failures = 0
function check(name, cond, detail) {
  results[name] = { pass: Boolean(cond), detail: detail ?? null }
  if (!cond) failures += 1
}

function makeRestQuery(workspaceRoot) {
  // eslint-disable-next-line no-new-func
  return new Function('workspaceRoot', `${restQuerySrc}\nreturn restQuery`)(workspaceRoot)
}

const ROOT_A = '/Users/example/decks-a'
const ROOT_B = '/Users/example/decks-b and spaces'

// --- Root A, bare path ------------------------------------------------------
{
  const restQuery = makeRestQuery(ROOT_A)
  const url = new URL(restQuery('/revision'), 'http://host')
  check('bare_path_single_question_mark', (url.pathname + url.search).split('?').length === 2, url.href)
  check('bare_path_workspace_root_param', url.searchParams.get('workspace_root') === ROOT_A, url.searchParams.get('workspace_root'))
}

// --- Root A, path that ALREADY has a query string (the exact /deck shape
// that previously swallowed workspace_root into board_path) -------------
{
  const restQuery = makeRestQuery(ROOT_A)
  const deckPath = '/path/to/My Deck.md'
  const boardPath = '/path/to/board.md'
  const withExistingQuery = `/deck?path=${encodeURIComponent(deckPath)}&board_path=${encodeURIComponent(boardPath)}`
  const generated = restQuery(withExistingQuery)
  check('existing_query_single_question_mark', generated.split('?').length === 2, generated)
  const url = new URL(generated, 'http://host')
  check('existing_query_path_param_exact', url.searchParams.get('path') === deckPath, url.searchParams.get('path'))
  check('existing_query_board_path_param_exact', url.searchParams.get('board_path') === boardPath, url.searchParams.get('board_path'))
  check('existing_query_workspace_root_param_exact', url.searchParams.get('workspace_root') === ROOT_A, url.searchParams.get('workspace_root'))
  // The historical bug: workspace_root got swallowed into board_path's value.
  check('board_path_does_not_contain_workspace_root', !String(url.searchParams.get('board_path')).includes('workspace_root'), url.searchParams.get('board_path'))
}

// --- Two distinct focused roots produce two distinct workspace_root values -
{
  const genA = makeRestQuery(ROOT_A)('/decks')
  const genB = makeRestQuery(ROOT_B)('/decks')
  const paramA = new URL(genA, 'http://host').searchParams.get('workspace_root')
  const paramB = new URL(genB, 'http://host').searchParams.get('workspace_root')
  check('two_roots_produce_distinct_workspace_root', paramA !== paramB && paramA === ROOT_A && paramB === ROOT_B, { paramA, paramB })
}

// --- Mutation control: deliberately regress to naive `path + '?' + params`
// concatenation (the exact bug the review found at 6366e3a) and prove the
// named checks correctly turn red against it -- the mutation is defined
// inline here (it never touches desktop/plugin.js), so this run always
// reflects the committed source; set CHECK_RESTQUERY_MUTATE=1 to run it.
if (process.env.CHECK_RESTQUERY_MUTATE === '1') {
  const naiveRestQuery = workspaceRoot => path => {
    const params = new URLSearchParams()
    params.set('workspace_root', workspaceRoot)
    return `${path}?${params.toString()}` // BUG: always '?', even if path has one already
  }
  const restQuery = naiveRestQuery(ROOT_A)
  const deckPath = '/path/to/My Deck.md'
  const boardPath = '/path/to/board.md'
  const withExistingQuery = `/deck?path=${encodeURIComponent(deckPath)}&board_path=${encodeURIComponent(boardPath)}`
  const generated = restQuery(withExistingQuery)
  const url = new URL(generated, 'http://host')
  check('mutation_reproduces_swallowed_workspace_root', String(url.searchParams.get('board_path')).includes('workspace_root'), url.searchParams.get('board_path'))
}

console.log(JSON.stringify({ results, failures }, null, 2))
process.exit(failures === 0 ? 0 : 1)
