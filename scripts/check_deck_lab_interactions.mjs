// Executable interaction proof for the Deck Lab pane (t_1e429f1c correction).
//
// Drives the REAL running plugin over CDP (not a grep of source text): real
// pointer moves/clicks via CDP Input, and real `.focus()` calls that fire
// the component's actual onFocus handler, against the live Hermes desktop
// instance's uncompiled plugin.js. Intercepts ctx.os.openExternal calls by
// walking the React fiber tree from a DOM node up to the first ancestor
// whose memoizedProps carry a `ctx.os.openExternal` function, then wrapping
// that exact function reference in place -- the same `ctx` object instance
// every CardRow in the pane closes over, so the wrap observes the real call
// site, not a decoy.
//
// Usage: node scripts/check_deck_lab_interactions.mjs
// Exit code 0 + all `pass: true` on success; prints JSON results to stdout
// and writes the same to deck_lab_interaction_checks.json (cwd).
//
// Requires a live Hermes desktop app already running with
// --remote-debugging-port (default 9333), with the deck-lab plugin loaded
// from this worktree (see /Users/claytonduarte/.hermes/desktop-plugins/deck-lab
// symlink). tests/test_ui_interactions.py shells out to this script -- when
// DECK_LAB_LIVE_CDP=1 is set -- and asserts rc == 0 and every named check
// passes.

import { writeFileSync } from 'node:fs'
import { connect, discoverTarget } from './deck_lab_cdp_driver.mjs'

const CDP_HOST = process.env.DECK_LAB_CDP_HOST ?? '127.0.0.1'
const CDP_PORT = Number(process.env.DECK_LAB_CDP_PORT ?? 9333)
const EXACT_JOINED_RESEARCHERS_URL = 'https://scryfall.com/card/sos/23/joined-researchers-secret-rendezvous?utm_source=api'

// Mutation control for the trusted-row-input assertion (required by the
// card): when set, the row-background click/tap step uses the synthetic
// (non-trusted) dispatchEvent path instead of real CDP Input, so the named
// `trusted_row_input_pins_via_card_row_onclick` check must observe
// isTrusted:false and fail -- proving the check actually discriminates real
// pointer input from a bare event dispatch, not merely that pin state
// flipped (which a synthetic dispatch can also produce).
const USE_SYNTHETIC_ROW_CLICK = process.env.DECK_LAB_MUTATION_SYNTHETIC_ROW_CLICK === '1'

// Mutation control for the stale-art guard (required by the card): when
// set, the pane's own localStorage flag is set BEFORE the cold reload, so
// ImageWithLoadingGuard runs in its deliberately-broken mode (always
// visible, onLoad never updates loadedSrc). The named
// `no_stale_image_under_new_title` check must then fail with
// imageGenuinelyNotStale:false, proving the check detects a broken
// visible-image guard rather than merely passing under the correct one.
const USE_STALE_ART_MUTATION = process.env.DECK_LAB_MUTATION_STALE_ART === '1'

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
  if (USE_STALE_ART_MUTATION) {
    await d.evalJs(`localStorage.setItem('DECK_LAB_MUTATION_STALE_ART', '1')`)
  } else {
    await d.evalJs(`localStorage.removeItem('DECK_LAB_MUTATION_STALE_ART')`)
  }
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
  // that exact function reference in place.
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
  // Pinning is done via the row's own dedicated pin/unpin icon button
  // (aria-label "Pin preview" / "Unpin preview"), not by clicking the row
  // background or the card-name button (which opens Scryfall and calls
  // stopPropagation). The pin button is opacity-0 until the row is
  // hovered/focused, but it is always present in the DOM and clickable via
  // real CDP pointer events regardless of its opacity.
  const pinButtonSelector = name =>
    `${rowSelector(name)}.querySelector('button[aria-label="Pin preview"], button[aria-label="Unpin preview"]')`
  const previewTitle = () => d.evalJs(`document.querySelector('.text-\\\\[0\\\\.8rem\\\\]')?.textContent ?? null`)
  const previewPinned = () => d.evalJs(`!!Array.from(document.querySelectorAll('span')).find(s => s.textContent === 'pinned')`)

  // 1. Hover changes an unpinned preview.
  await d.hoverElement(rowSelector('Sol Ring'))
  await d.sleep(500)
  const titleAfterHoverSolRing = await previewTitle()
  check('hover_changes_unpinned_preview', titleAfterHoverSolRing === 'Sol Ring', { titleAfterHoverSolRing })

  // 2. Keyboard focus changes an unpinned preview.
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
  await d.clickElement(pinButtonSelector('Nelly Borca, Impulsive Accuser'))
  await d.sleep(400)
  const pinnedAfterFirstClick = await previewPinned()
  const titlePinned = await previewTitle()
  await d.clickElement(pinButtonSelector('Nelly Borca, Impulsive Accuser'))
  await d.sleep(400)
  const pinnedAfterSecondClick = await previewPinned()
  check('row_activation_pins_and_unpins', pinnedAfterFirstClick === true && titlePinned === 'Nelly Borca, Impulsive Accuser' && pinnedAfterSecondClick === false, {
    pinnedAfterFirstClick, titlePinned, pinnedAfterSecondClick
  })

  // 3b. Row background click/tap (CardRow.onClick / onRowActivate) also
  //     pins/unpins directly, without going through the dedicated pin icon
  //     button -- restores coverage of the row-level click/tap pin path per
  //     architect correction. Arms a native capture-phase click listener on
  //     the row group BEFORE the click so the received event's isTrusted
  //     and closest-group identity can be asserted -- not merely that the
  //     DOM pin state flipped, which a synthetic dispatchEvent can also
  //     produce.
  const armRowClickCapture = async name => {
    await d.evalJs(`
      (() => {
        const row = ${rowSelector(name)}
        if (!row) return false
        window.__rowClickCapture = null
        const handler = event => {
          window.__rowClickCapture = { isTrusted: event.isTrusted, closestGroup: event.currentTarget.getAttribute('aria-label') }
        }
        row.addEventListener('click', handler, { capture: true, once: true })
        return true
      })()
    `)
  }
  await armRowClickCapture('Sol Ring')
  const rowClickFn = USE_SYNTHETIC_ROW_CLICK ? d.clickRowBackgroundSynthetic : d.clickRowBackground
  await rowClickFn(rowSelector('Sol Ring'))
  await d.sleep(400)
  const rowClickCaptureAfterFirst = await d.evalJs(`window.__rowClickCapture`)
  const pinnedAfterRowBackgroundClick = await previewPinned()
  const titlePinnedViaRowBackground = await previewTitle()
  await armRowClickCapture('Sol Ring')
  await rowClickFn(rowSelector('Sol Ring'))
  await d.sleep(400)
  const unpinnedAfterSecondRowBackgroundClick = await previewPinned()
  check('row_background_click_pins_and_unpins', pinnedAfterRowBackgroundClick === true && titlePinnedViaRowBackground === 'Sol Ring' && unpinnedAfterSecondRowBackgroundClick === false, {
    pinnedAfterRowBackgroundClick, titlePinnedViaRowBackground, unpinnedAfterSecondRowBackgroundClick
  })
  check('trusted_row_input_pins_via_card_row_onclick',
    rowClickCaptureAfterFirst?.isTrusted === true && rowClickCaptureAfterFirst?.closestGroup === 'Sol Ring' && pinnedAfterRowBackgroundClick === true,
    { rowClickCaptureAfterFirst, pinnedAfterRowBackgroundClick })

  // 4. Hovering another card while pinned does not replace preview.
  await d.clickElement(pinButtonSelector('Sol Ring'))
  await d.sleep(400)
  await d.hoverElement(rowSelector('Nelly Borca, Impulsive Accuser'))
  await d.sleep(400)
  const titleWhilePinnedAndHoveringOther = await previewTitle()
  const stillPinnedWhileHoveringOther = await previewPinned()
  check('pinned_hover_guard', titleWhilePinnedAndHoveringOther === 'Sol Ring' && stillPinnedWhileHoveringOther === true, {
    titleWhilePinnedAndHoveringOther, stillPinnedWhileHoveringOther
  })

  // 4b. Focusing (keyboard) another card while pinned also does not replace
  //     the preview -- the onFocus handler shares onHoverPreview, but this
  //     exercises the distinct keyboard path end to end, not just hover.
  await d.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 2, y: 2 })
  await d.evalJs(`document.activeElement && document.activeElement.blur && document.activeElement.blur()`)
  const focusedWhilePinned = await d.evalJs(`
    (() => {
      const row = ${rowSelector('Nelly Borca, Impulsive Accuser')}
      if (!row) return false
      row.focus()
      return document.activeElement === row
    })()
  `)
  await d.sleep(400)
  const titleWhilePinnedAndFocusingOther = await previewTitle()
  const stillPinnedWhileFocusingOther = await previewPinned()
  check('pinned_focus_guard', focusedWhilePinned === true && titleWhilePinnedAndFocusingOther === 'Sol Ring' && stillPinnedWhileFocusingOther === true, {
    focusedWhilePinned, titleWhilePinnedAndFocusingOther, stillPinnedWhileFocusingOther
  })
  // unpin for subsequent steps
  await d.clickElement(pinButtonSelector('Sol Ring'))
  await d.sleep(300)

  // 5. Card-name activation calls ctx.os.openExternal exactly once with the
  //    EXACT validated Joined Researchers Scryfall URL, and does not toggle
  //    pin. (Deliberately uses the DFC card, not Sol Ring, and asserts exact
  //    string equality -- not startsWith -- per architect correction.)
  await d.evalJs(`window.__openExternalCalls = []`)
  const pinnedBeforeNameClick = await previewPinned()
  await d.hoverElement(rowSelector('Joined Researchers // Secret Rendezvous'))
  await d.sleep(300)
  await d.clickElement(`${rowSelector('Joined Researchers // Secret Rendezvous')}.querySelector('button')`)
  await d.sleep(400)
  const openExternalCallsAfterName = await d.evalJs(`window.__openExternalCalls`)
  const pinnedAfterNameClick = await previewPinned()
  check('open_external_called_once_with_exact_url', Array.isArray(openExternalCallsAfterName) && openExternalCallsAfterName.length === 1 &&
    openExternalCallsAfterName[0].length === 1 && openExternalCallsAfterName[0][0] === EXACT_JOINED_RESEARCHERS_URL,
    { openExternalCallsAfterName, expected: EXACT_JOINED_RESEARCHERS_URL, pinnedBeforeNameClick, pinnedAfterNameClick })
  check('open_external_does_not_toggle_pin', pinnedBeforeNameClick === pinnedAfterNameClick, { pinnedBeforeNameClick, pinnedAfterNameClick })

  // 6. Unresolved/loading/error/invalid/non-Scryfall cards never call
  //    openExternal.
  //    - Agrus Kos, Spirit of Justice: state=loading
  //    - Thought Vessel: state=error
  //    - Keeper of the Accord: state=cached but scryfall_uri host is NOT
  //      scryfall.com (CardRow's validUrl check must disable/no-op it)
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
  await d.hoverElement(rowSelector('Keeper of the Accord'))
  await d.sleep(300)
  const nonScryfallNameBtnDisabled = await d.evalJs(`${rowSelector('Keeper of the Accord')}.querySelector('button').disabled`)
  await d.clickElement(`${rowSelector('Keeper of the Accord')}.querySelector('button')`)
  await d.sleep(300)
  const openExternalCallsAfterLoadingErrorInvalid = await d.evalJs(`window.__openExternalCalls`)
  check('loading_error_nonscryfall_never_call_open_external', loadingNameBtnDisabled === true && errorNameBtnDisabled === true &&
    nonScryfallNameBtnDisabled === true &&
    Array.isArray(openExternalCallsAfterLoadingErrorInvalid) && openExternalCallsAfterLoadingErrorInvalid.length === 0,
    { loadingNameBtnDisabled, errorNameBtnDisabled, nonScryfallNameBtnDisabled, openExternalCallsAfterLoadingErrorInvalid })

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
  //    show Sol Ring's <img src> while the new title is already showing.
  //    Deterministic (no race-tuned sleep): assert IMMEDIATELY after the
  //    switch that either the <img> is hidden, or it is visible AND its own
  //    `data-loaded-src` (the src whose onLoad actually completed) equals
  //    the new src -- never assume a hidden image implies staleness when
  //    the new art was already cached and loaded synchronously.
  await d.hoverElement(rowSelector('Sol Ring'))
  await d.sleep(400)
  const solRingSrc = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  await d.hoverElement(rowSelector('Joined Researchers // Secret Rendezvous'))
  const immediatelyAfterSwitch = await d.evalJs(`
    (() => {
      const img = document.querySelector('img')
      return {
        title: document.querySelector('.text-\\\\[0\\\\.8rem\\\\]')?.textContent ?? null,
        src: img?.src ?? null,
        hidden: img?.classList?.contains('hidden') ?? null,
        loadedSrc: img?.getAttribute('data-loaded-src') ?? null
      }
    })()
  `)
  const { title: titleImmediatelyAfterSwitch, src: imgSrcImmediatelyAfterSwitch, hidden: imgHiddenImmediatelyAfterSwitch, loadedSrc: loadedSrcImmediatelyAfterSwitch } = immediatelyAfterSwitch
  const imageGenuinelyNotStale = imgHiddenImmediatelyAfterSwitch === true ||
    (imgHiddenImmediatelyAfterSwitch === false && loadedSrcImmediatelyAfterSwitch === imgSrcImmediatelyAfterSwitch)
  await d.sleep(600) // give the real <img> a chance to finish loading
  const imgVisibleEventually = await d.evalJs(`document.querySelector('img')?.classList?.contains('hidden') === false`)
  const imgSrcEventually = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  const statusAfterSettle = await d.evalJs(`
    (() => {
      const hidden = document.querySelector('img')?.classList?.contains('hidden')
      const loadingShown = document.body.innerText.includes('Loading art…')
      return { hidden, loadingShown }
    })()
  `)
  check('no_stale_image_under_new_title', titleImmediatelyAfterSwitch === 'Joined Researchers' && imgSrcImmediatelyAfterSwitch !== solRingSrc && imageGenuinelyNotStale, {
    solRingSrc, titleImmediatelyAfterSwitch, imgSrcImmediatelyAfterSwitch, imgHiddenImmediatelyAfterSwitch, loadedSrcImmediatelyAfterSwitch, imageGenuinelyNotStale
  })
  check('new_image_eventually_visible_or_explicit_status', (imgVisibleEventually === true && imgSrcEventually === imgSrcImmediatelyAfterSwitch) || statusAfterSettle.loadingShown === true, {
    imgVisibleEventually, imgSrcEventually, statusAfterSettle
  })

  // 10. Recursive indentation is strictly increasing through
  //     Deck > Veggies > Interaction > Removal, and category counts are
  //     exact quantity sums (not row counts) -- cross-checked against the
  //     live DOM's own recursive quantity totals.
  const indentAndCounts = await d.evalJs(`
    (() => {
      const rows = Array.from(document.querySelectorAll('[style*="margin-left"]'))
      const byName = {}
      for (const row of rows) {
        const spans = row.querySelectorAll(':scope > div > span')
        if (spans.length < 2) continue
        const nameSpan = spans[0]
        const countSpan = spans[1]
        if (!(nameSpan.textContent in byName)) {
          byName[nameSpan.textContent] = { ml: parseInt(row.style.marginLeft || '0', 10), count: parseInt(countSpan.textContent, 10) }
        }
      }
      return byName
    })()
  `)
  const deckMl = indentAndCounts?.['Deck']?.ml ?? 0
  const veggiesMl = indentAndCounts?.['Veggies']?.ml ?? -1
  const interactionMl = indentAndCounts?.['Interaction']?.ml ?? -1
  const removalMl = indentAndCounts?.['Removal']?.ml ?? -1
  check('recursive_indentation_strictly_increasing', deckMl < veggiesMl && veggiesMl < interactionMl && interactionMl < removalMl, {
    deckMl, veggiesMl, interactionMl, removalMl
  })
  // Removal category sums to exactly 7 (7 distinct 1-ofs: Path to Exile,
  // Swords to Plowshares, Erode, Generous Gift, Chaos Warp, Loran of the
  // Third Path, Requisition Raid) -- quantity sum, not row count, cross
  // checked against tests/test_ui_fixture_invariants.py's golden multiset.
  const removalCount = indentAndCounts?.['Removal']?.count
  const landsCount = indentAndCounts?.['Lands']?.count
  check('category_counts_are_exact_quantity_sums', removalCount === 7 && landsCount === 36, {
    removalCount, landsCount, indentAndCounts
  })

  // 11. Invalid-candidate diagnostics: selecting the malformed/projected
  //     deck surfaces its real error code/message/path (not merely
  //     presence of "invalid" text).
  await d.evalJs(`document.activeElement && document.activeElement.blur && document.activeElement.blur()`)
  await d.clickElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('malformed') && b.textContent.includes('invalid'))`)
  await d.sleep(500)
  const invalidDiagnostics = await d.evalJs(`
    (() => {
      const text = document.body.innerText
      return {
        hasHeading: text.includes('This deck is invalid.'),
        hasCode: text.includes('CARD_QUANTITY_INVALID'),
        hasMessage: text.includes('Quantity must be a positive integer'),
        hasPath: text.includes('tests/fixtures/malformed/card_quantity_invalid_zero.md')
      }
    })()
  `)
  check('invalid_candidate_diagnostics_shown', invalidDiagnostics.hasHeading && invalidDiagnostics.hasCode && invalidDiagnostics.hasMessage && invalidDiagnostics.hasPath, invalidDiagnostics)

  // Re-select Nelly for the remaining checks (long-name truncation measured
  // against the real decklist DOM).
  await d.evalJs(`
    (() => {
      const buttons = Array.from(document.querySelectorAll('button'))
      const row = buttons.find(b => b.textContent.includes('Nelly Borca') && !b.textContent.includes('invalid'))
      if (row) row.click()
    })()
  `)
  await d.sleep(500)

  // 12. Genuine long card name is clipped by measured DOM overflow, not
  //     merely present in the DOM. "Joined Researchers // Secret
  //     Rendezvous" is the longest real in-deck name and its name <button>
  //     measurably overflows its own box (scrollWidth > clientWidth) while
  //     a short name's does not.
  const overflowCheck = await d.evalJs(`
    (() => {
      const longRow = ${rowSelector('Joined Researchers // Secret Rendezvous')}
      const shortRow = ${rowSelector('Sol Ring')}
      const longBtn = longRow?.querySelector('button')
      const shortBtn = shortRow?.querySelector('button')
      if (!longBtn || !shortBtn) return null
      return {
        longOverflows: longBtn.scrollWidth > longBtn.clientWidth,
        longScrollWidth: longBtn.scrollWidth,
        longClientWidth: longBtn.clientWidth,
        shortOverflows: shortBtn.scrollWidth > shortBtn.clientWidth
      }
    })()
  `)
  check('long_card_name_clipped_by_measured_overflow', Boolean(overflowCheck) && overflowCheck.longOverflows === true && overflowCheck.shortOverflows === false, overflowCheck)

  // 13. Driver leaves the decklist scroller's horizontal scroll at zero
  //     (fixed scrollIntoView side effect -- was `inline: 'center'`, now
  //     `inline: 'nearest'`), so the proof harness does not leave the pane
  //     visually clipped after the run.
  const scrollerState = await d.evalJs(`
    (() => {
      const el = Array.from(document.querySelectorAll('div')).find(e => e.className === 'size-full outline-none' && e.scrollWidth > e.clientWidth || e.scrollLeft !== undefined && e.className.includes('size-full outline-none'))
      // Fall back: find the nearest horizontally-scrollable ancestor of a decklist row.
      const row = ${rowSelector('Sol Ring')}
      let node = row
      while (node) {
        if (node.scrollWidth > node.clientWidth) return { scrollLeft: node.scrollLeft, scrollWidth: node.scrollWidth, clientWidth: node.clientWidth }
        node = node.parentElement
      }
      return { scrollLeft: 0, scrollWidth: 0, clientWidth: 0 }
    })()
  `)
  check('decklist_scroller_horizontal_scroll_is_zero', scrollerState.scrollLeft === 0, scrollerState)

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
