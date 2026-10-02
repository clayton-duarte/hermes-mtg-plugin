// Extracts a single top-level function/const-arrow definition out of
// desktop/plugin.js by name and prints its exact source text on stdout.
// Used by executable (non-source-grep) tests that need to actually CALL the
// real pane logic (restQuery, buildCategoryTree, groupDecksByFormatAndStatus,
// ...) with real inputs, instead of asserting on substrings of the file.
//
// This does not re-implement the logic: it slices the exact bytes that ship
// in desktop/plugin.js, so a regression in the real function always shows up
// here too.
//
// Usage: node scripts/extract_plugin_js_function.mjs <path> <name...>
// Prints each requested function's source, in order, separated by a blank
// line, to stdout. Exits 1 if any name is not found.

import { readFileSync } from 'node:fs'

const [, , filePath, ...names] = process.argv
if (!filePath || names.length === 0) {
  console.error('usage: extract_plugin_js_function.mjs <path> <name...>')
  process.exit(1)
}

const src = readFileSync(filePath, 'utf8')

function extractOne(name) {
  // Matches `function NAME(` or `const NAME = ` at the start of a line,
  // then captures balanced braces for the function body.
  const startRe = new RegExp(`^[ \\t]*(?:function ${name}\\s*\\(|const ${name}\\s*=)`, 'm')
  const startMatch = startRe.exec(src)
  if (!startMatch) return null
  const start = startMatch.index

  // Walk forward from the first `{` after the match, tracking brace depth,
  // to find the matching close brace -- robust to nested objects/arrows.
  let i = src.indexOf('{', start)
  if (i === -1) return null
  let depth = 0
  let end = -1
  for (; i < src.length; i++) {
    const c = src[i]
    if (c === '{') depth++
    else if (c === '}') {
      depth--
      if (depth === 0) {
        end = i + 1
        break
      }
    }
  }
  if (end === -1) return null
  return src.slice(start, end)
}

const out = []
for (const name of names) {
  const text = extractOne(name)
  if (text === null) {
    console.error(`function/const '${name}' not found in ${filePath}`)
    process.exit(1)
  }
  out.push(text)
}
console.log(out.join('\n\n'))
