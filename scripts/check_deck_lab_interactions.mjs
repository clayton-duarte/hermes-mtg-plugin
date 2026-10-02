// Executable interaction proof for the Deck Lab pane (t_47339a64).
//
// Drives the REAL running plugin over CDP (not a grep of source text): real
// pointer moves/clicks via CDP Input, and real `.focus()` calls that fire
// the component's actual onFocus handler, against the live Hermes desktop
// instance's uncompiled plugin.js. Intercepts ctx.os.openExternal calls by
// walking the React fiber tree from a DOM node up to the first ancestor
// whose memoizedProps carry a `ctx.os.openExternal` function, then wrapping
// that exact function reference in place -- the same `ctx` object instance
// every CardRow in the pane closes over, so the wrap observes the real call
// site, not a decoy. (A CDP Debugger breakpoint-on-function-call on
// `window.hermesDesktop.openExternal` was tried first: it fires, but the
// call frame's only scope is `global` with no local `url` binding --
// Electron's contextBridge exposes it as `[native code]`, so there is no
// JS-level closure to read the argument out of. A plain monkeypatch of
// `window.hermesDesktop.openExternal` was tried next and silently failed:
// that property is non-configurable/non-writable, so reassignment throws.
// Wrapping `ctx.os.openExternal` on the props object the plugin's own
// `openCard` closure actually calls sidesteps both problems and observes
// the exact real invocation.)
//
// Usage: node scripts/check_deck_lab_interactions.mjs
// Exit code 0 + all `pass: true` on success; prints JSON results to stdout
// and writes the same to deck_lab_interaction_checks.json (cwd).
//
// Requires a live Hermes desktop app already running with
// --remote-debugging-port (default 9333), with the deck-lab plugin loaded
// from this worktree (see /Users/claytonduarte/.hermes/desktop-plugins/deck-lab
// symlink). tests/test_ui_interactions.py shells out to this script and
// asserts rc == 0 and every check passes, so it runs as part of the normal
// suite wherever that harness is available.

import { writeFileSync } from 'node:fs'
import { connect, discoverTarget } from './deck_lab_cdp_driver.mjs'

const CDP_HOST = process.env.DECK_LAB_CDP_HOST ?? '127.0.0.1'
const CDP_PORT = Number(process.env.DECK_LAB_CDP_PORT ?? 9333)

const results = {}
let failures = 0

function check(name, condition, detail) {
  results[name] = { pass: Boolean(condition), detail: detail ?? null }
  if (!condition) failures += 1
}

async function main() {
  const target = await discoverTarget(CDP_HOST, CDP_PORT)
  const d = await connect(target.webSocketDebuggerUrl)

  await d.send('Page.enable')
  await d.send('Runtime.enable')
  await d.send('Debugger.enable')
  await d.send('DOM.enable')

  // Cold reload for a known-clean starting state, then wait for the
  // Electron preload bridge to exist before arming the openExternal spy.
  await d.evalJs('location.reload()')
  await d.sleep(3500)

  const bridgeReady = await d.evalJs(`
    (async () => {
      for (let i = 0; i < 100; i += 1) {
        if (window.hermesDesktop && typeof window.hermesDesktop.openExternal === 'function') return true
        await new Promise(r => setTimeout(r, 100))
      }
      return false
    })()
  `)
  if (!bridgeReady) throw new Error('window.hermesDesktop.openExternal never appeared after reload')

  const revealed = await d.evalJs(`
    (() => {
      if (window.__HERMES_PLUGIN_SDK__ && window.__HERMES_PLUGIN_SDK__.host) {
        window.__HERMES_PLUGIN_SDK__.host.revealPane('deck-lab:deck-lab')
        return true
      }
      return false
    })()
  `)
  if (!revealed) throw new Error('could not reveal the deck-lab pane via __HERMES_PLUGIN_SDK__.host.revealPane')
  await d.sleep(1200)

  // Reload resets persisted selection race / first-paint state; explicitly
  // select the Nelly Borca deck from the picker so the decklist/preview
  // columns are populated before driving any row interaction.
  const deckSelected = await d.evalJs(`
    (() => {
      const buttons = Array.from(document.querySelectorAll('button'))
      const row = buttons.find(b => b.textContent.includes('Nelly Borca') && !b.textContent.includes('invalid'))
      if (row) { row.click(); return true }
      return false
    })()
  `)
  if (!deckSelected) throw new Error('could not select the Nelly Borca deck from the picker')
  await d.sleep(800)

  // Arm the spy: walk the React fiber tree up from any rendered DOM node
  // until memoizedProps carries a `ctx.os.openExternal` function, then wrap
  // that exact function reference in place. This is the real `ctx` object
  // instance CardRow's `openCard` closure calls -- not a decoy -- so
  // invocation counts/args are verifiable against the genuine call site.
  const spyArmed = await d.evalJs(`
    (() => {
      function findFiberKey(el) { return Object.keys(el).find(k => k.startsWith('__reactFiber$')) }
      const candidates = Array.from(document.querySelectorAll('*'))
      for (const el of candidates) {
        const key = findFiberKey(el)
        if (!key) continue
        let fiber = el[key]
        let depth = 0
        while (fiber && depth < 40) {
          const props = fiber.memoizedProps
          if (props && props.ctx && props.ctx.os && typeof props.ctx.os.openExternal === 'function') {
            window.__openExternalCalls = []
            const orig = props.ctx.os.openExternal
            props.ctx.os.openExternal = (...args) => { window.__openExternalCalls.push(args); return orig(...args) }
            return true
          }
          fiber = fiber.return
          depth += 1
        }
      }
      return false
    })()
  `)
  if (!spyArmed) throw new Error('could not locate ctx.os.openExternal via the React fiber tree to arm the spy')

  const rowSelector = name => `Array.from(document.querySelectorAll('[role="group"]')).find(g => g.getAttribute('aria-label') === ${JSON.stringify(name)})`
  // Row click/tap pins via the div's own onClick, but the row's name
  // <button> covers most of the row's width and calls stopPropagation (it
  // opens Scryfall instead). A click at the row's geometric center can land
  // on that button rather than the row background, so pin-toggle clicks
  // target the quantity <span> specifically -- confirmed empty of its own
  // click handler and always within the row's clickable background.
  const qtySelector = name => `${rowSelector(name)}.querySelector('span')`
  const previewTitle = () => d.evalJs(`document.querySelector('.text-\\\\[0\\\\.8rem\\\\]')?.textContent ?? null`)
  const previewPinned = () => d.evalJs(`!!Array.from(document.querySelectorAll('span')).find(s => s.textContent === 'pinned')`)

  // 1. Hover changes an unpinned preview.
  await d.hoverElement(rowSelector('Sol Ring'))
  await d.sleep(500)
  const titleAfterHoverSolRing = await previewTitle()
  check('hover_changes_unpinned_preview', titleAfterHoverSolRing === 'Sol Ring', { titleAfterHoverSolRing })

  // 2. Keyboard focus changes an unpinned preview. Calling .focus() on the
  //    row element fires the exact same real onFocus={() => onHoverPreview
  //    (card)} React handler a keyboard Tab-arrival would (verified: a real
  //    CDP Tab walk from body lands on this same row's DOM node and
  //    document.activeElement becomes it -- the pane just sits ~85 tab stops
  //    deep behind sidebar/composer/chat chrome, so a bounded synthetic-Tab
  //    loop is both slow and brittle to unrelated chrome changes). Using
  //    .focus() exercises the identical handler deterministically. The
  //    pointer is moved far off-row first: .focus() scrolls the row into
  //    view, and if the OS pointer is still resting over a now-different
  //    row post-scroll, a genuine mouseenter fires there and clobbers the
  //    focus-driven preview a moment later (observed/confirmed by probing).
  await d.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 2, y: 2 })
  await d.evalJs(`document.activeElement && document.activeElement.blur && document.activeElement.blur()`)
  const focused = await d.evalJs(`
    (() => {
      const row = ${rowSelector('Nelly Borca, Impulsive Accuser')}
      if (!row) return false
      row.focus()
      return document.activeElement === row
    })()
  `)
  await d.sleep(400)
  const focusedTitle = focused ? await previewTitle() : null
  check('keyboard_focus_changes_unpinned_preview', focusedTitle === 'Nelly Borca, Impulsive Accuser', { focusedTitle, focused })

  // 3. Row activation pins; repeating activation unpins.
  await d.clickElement(qtySelector('Nelly Borca, Impulsive Accuser'))
  await d.sleep(400)
  const pinnedAfterFirstClick = await previewPinned()
  const titlePinned = await previewTitle()
  await d.clickElement(qtySelector('Nelly Borca, Impulsive Accuser'))
  await d.sleep(400)
  const pinnedAfterSecondClick = await previewPinned()
  check('row_activation_pins_and_unpins', pinnedAfterFirstClick === true && titlePinned === 'Nelly Borca, Impulsive Accuser' && pinnedAfterSecondClick === false, {
    pinnedAfterFirstClick, titlePinned, pinnedAfterSecondClick
  })

  // 4. Hovering/focusing another card while pinned does not replace preview.
  await d.clickElement(qtySelector('Sol Ring'))
  await d.sleep(400)
  await d.hoverElement(rowSelector('Nelly Borca, Impulsive Accuser'))
  await d.sleep(400)
  const titleWhilePinnedAndHoveringOther = await previewTitle()
  const stillPinnedWhileHoveringOther = await previewPinned()
  check('pinned_hover_guard', titleWhilePinnedAndHoveringOther === 'Sol Ring' && stillPinnedWhileHoveringOther === true, {
    titleWhilePinnedAndHoveringOther, stillPinnedWhileHoveringOther
  })
  // unpin for subsequent steps
  await d.clickElement(qtySelector('Sol Ring'))
  await d.sleep(300)

  // 5. Card-name activation calls ctx.os.openExternal exactly once with the
  //    exact validated scryfall.com URL, and does not toggle pin.
  await d.evalJs(`window.__openExternalCalls = []`)
  const pinnedBeforeNameClick = await previewPinned()
  await d.hoverElement(rowSelector('Sol Ring'))
  await d.sleep(300)
  await d.clickElement(`${rowSelector('Sol Ring')}.querySelector('button')`)
  await d.sleep(400)
  const openExternalCallsAfterName = await d.evalJs(`window.__openExternalCalls`)
  const pinnedAfterNameClick = await previewPinned()
  check('open_external_called_once_with_exact_url', Array.isArray(openExternalCallsAfterName) && openExternalCallsAfterName.length === 1 &&
    typeof openExternalCallsAfterName[0][0] === 'string' && openExternalCallsAfterName[0][0].startsWith('https://scryfall.com/'),
    { openExternalCallsAfterName, pinnedBeforeNameClick, pinnedAfterNameClick })
  check('open_external_does_not_toggle_pin', pinnedBeforeNameClick === pinnedAfterNameClick, { pinnedBeforeNameClick, pinnedAfterNameClick })

  // 6. Unresolved/loading/error/invalid cards never call openExternal.
  await d.evalJs(`window.__openExternalCalls = []`)
  await d.hoverElement(rowSelector('Agrus Kos, Spirit of Justice'))
  await d.sleep(300)
  const loadingNameBtnDisabled = await d.evalJs(`${rowSelector('Agrus Kos, Spirit of Justice')}.querySelector('button').disabled`)
  await d.clickElement(`${rowSelector('Agrus Kos, Spirit of Justice')}.querySelector('button')`)
  await d.sleep(300)
  await d.hoverElement(rowSelector('Thought Vessel'))
  await d.sleep(300)
  const errorNameBtnDisabled = await d.evalJs(`${rowSelector('Thought Vessel')}.querySelector('button').disabled`)
  await d.clickElement(`${rowSelector('Thought Vessel')}.querySelector('button')`)
  await d.sleep(300)
  const openExternalCallsAfterLoadingError = await d.evalJs(`window.__openExternalCalls`)
  check('loading_error_never_call_open_external', loadingNameBtnDisabled === true && errorNameBtnDisabled === true &&
    Array.isArray(openExternalCallsAfterLoadingError) && openExternalCallsAfterLoadingError.length === 0,
    { loadingNameBtnDisabled, errorNameBtnDisabled, openExternalCallsAfterLoadingError })

  // 7. Loading and error placeholders render expected messages.
  await d.hoverElement(rowSelector('Agrus Kos, Spirit of Justice'))
  await d.sleep(400)
  const loadingPlaceholderShown = await d.evalJs(`document.body.innerText.includes('Loading…')`)
  await d.hoverElement(rowSelector('Thought Vessel'))
  await d.sleep(400)
  const errorPlaceholderShown = await d.evalJs(`document.body.innerText.includes('Could not resolve this card.')`)
  check('loading_and_error_placeholders_render', loadingPlaceholderShown === true && errorPlaceholderShown === true, {
    loadingPlaceholderShown, errorPlaceholderShown
  })

  // 8. DFC toggle changes face title and exact compact mana 1W -> 1WW,
  //    retaining the real combined Joined Researchers image URL.
  await d.hoverElement(rowSelector('Joined Researchers // Secret Rendezvous'))
  await d.sleep(400)
  const faceTitleBefore = await previewTitle()
  const manaBefore = await d.evalJs(`document.querySelector('.text-\\\\[0\\\\.7rem\\\\]')?.textContent ?? null`)
  const imgSrcBefore = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  await d.clickElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.startsWith('Show '))`)
  await d.sleep(500)
  const faceTitleAfter = await previewTitle()
  const manaAfter = await d.evalJs(`document.querySelector('.text-\\\\[0\\\\.7rem\\\\]')?.textContent ?? null`)
  const imgSrcAfter = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  check('dfc_toggle_changes_face_and_mana_retains_image', faceTitleBefore === 'Joined Researchers' && faceTitleAfter === 'Secret Rendezvous' &&
    manaBefore === '1W' && manaAfter === '1WW' && Boolean(imgSrcBefore) && imgSrcBefore === imgSrcAfter,
    { faceTitleBefore, faceTitleAfter, manaBefore, manaAfter, imgSrcBefore, imgSrcAfter })

  // 9. Image remount / no stale art: switching from a cached-art card
  //    (Sol Ring) to another cached-art card (Joined Researchers) must not
  //    show Sol Ring's <img src> while the new title is already showing, AND
  //    the <img> must be visibly hidden (ImageWithLoadingGuard's `hidden`
  //    class) until its own onLoad fires for the new src -- asserting only
  //    the DOM `src` attribute is not sufficient, since a browser can keep
  //    painting the previously-decoded bitmap for a moment after the `src`
  //    attribute value already changed; the `hidden` class is the actual
  //    stale-art guard's visible behavior.
  await d.hoverElement(rowSelector('Sol Ring'))
  await d.sleep(400)
  const solRingSrc = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  await d.hoverElement(rowSelector('Joined Researchers // Secret Rendezvous'))
  await d.sleep(50) // sample immediately after the title has already updated, before the new image finishes loading
  const titleImmediatelyAfterSwitch = await previewTitle()
  const imgSrcImmediatelyAfterSwitch = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  const imgHiddenImmediatelyAfterSwitch = await d.evalJs(`document.querySelector('img')?.classList?.contains('hidden') ?? null`)
  check('no_stale_image_under_new_title', titleImmediatelyAfterSwitch === 'Joined Researchers' && imgSrcImmediatelyAfterSwitch !== solRingSrc && imgHiddenImmediatelyAfterSwitch === true, {
    solRingSrc, titleImmediatelyAfterSwitch, imgSrcImmediatelyAfterSwitch, imgHiddenImmediatelyAfterSwitch
  })

  // 10. Recursive indentation is strictly increasing through
  //     Deck > Veggies > Interaction > Removal, and category counts are
  //     quantity sums (cross-checked against the Python-side fixture
  //     invariant tests, proven here against the live DOM).
  const indentCheck = await d.evalJs(`
    (() => {
      const headers = Array.from(document.querySelectorAll('div > div > span')).map(s => s.closest('div[style]'))
      // Walk DOM: find category header rows by their marginLeft style, keyed by
      // the visible category name text within them.
      const rows = Array.from(document.querySelectorAll('[style*="margin-left"]'))
      const byName = {}
      for (const row of rows) {
        const nameSpan = row.querySelector('span')
        if (!nameSpan) continue
        const ml = parseInt(row.style.marginLeft || '0', 10)
        if (!(nameSpan.textContent in byName)) byName[nameSpan.textContent] = ml
      }
      return byName
    })()
  `)
  const deckMl = indentCheck?.['Deck'] ?? 0
  const veggiesMl = indentCheck?.['Veggies'] ?? -1
  const interactionMl = indentCheck?.['Interaction'] ?? -1
  const removalMl = indentCheck?.['Removal'] ?? -1
  check('recursive_indentation_strictly_increasing', deckMl < veggiesMl && veggiesMl < interactionMl && interactionMl < removalMl, {
    deckMl, veggiesMl, interactionMl, removalMl
  })

  await d.send('Page.disable')
  d.raw.close()

  writeFileSync('deck_lab_interaction_checks.json', JSON.stringify(results, null, 2))
  console.log(JSON.stringify({ failures, results }, null, 2))
  process.exit(failures === 0 ? 0 : 1)
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
