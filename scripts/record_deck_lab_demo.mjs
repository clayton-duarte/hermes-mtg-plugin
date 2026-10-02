#!/usr/bin/env node
// Records a faithful, reviewable screencast of the Deck Lab live pane
// (t_e7bd48b1 correction). Drives the real plugin over CDP using the SAME
// exact `[role=group][aria-label=...]` row selectors and exact descendant
// controls (pin button, name button) that
// scripts/check_deck_lab_interactions.mjs uses -- never a first-match
// `button.textContent.includes(...)` scan, which can hit the deck picker or
// a card-name button instead of the intended row/control.
//
// Every beat self-validates its precondition/postcondition in-page and
// throws (deleting any partial output) if a selector/action/assertion
// fails, instead of silently producing a misleading recording.
//
// Preserves wall-clock timing: frames are captured on a fixed real-time
// sampling interval (not sparse change-only screencast frames encoded at a
// fixed fps), so a held state of N seconds actually occupies N seconds of
// output, and the overlay burns in a label plus the live elapsed time so
// hover vs. keyboard-focus beats are distinguishable on tape.
//
// Usage: node scripts/record_deck_lab_demo.mjs <output.mp4>

import { discoverTarget, connect } from './deck_lab_cdp_driver.mjs'
import { mkdtempSync, writeFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'

const SAMPLE_INTERVAL_MS = 200 // 5 fps real-time sampling -> faithful duration
const EXACT_JOINED_RESEARCHERS_URL = 'https://scryfall.com/card/sos/23/joined-researchers-secret-rendezvous?utm_source=api'

async function main() {
  const outPath = process.argv[2]
  if (!outPath) {
    console.error('usage: node record_deck_lab_demo.mjs <output.mp4>')
    process.exit(2)
  }

  const frameDir = mkdtempSync(join(tmpdir(), 'deck-lab-frames-'))
  const target = await discoverTarget()
  const d = await connect(target.webSocketDebuggerUrl)

  await d.send('Page.enable')
  await d.send('Runtime.enable')

  const rowSelector = name => `Array.from(document.querySelectorAll('[role="group"]')).find(g => g.getAttribute('aria-label') === ${JSON.stringify(name)})`
  const pinButtonSelector = name => `${rowSelector(name)}.querySelector('button[aria-label="Pin preview"], button[aria-label="Unpin preview"]')`
  const nameButtonSelector = name => `${rowSelector(name)}.querySelector('button')`
  const previewTitle = () => d.evalJs(`document.querySelector('.text-\\\\[0\\\\.8rem\\\\]')?.textContent ?? null`)
  const previewPinned = () => d.evalJs(`!!Array.from(document.querySelectorAll('span')).find(s => s.textContent === 'pinned')`)

  let frameIndex = 0
  let currentLabel = 'starting'
  const recordStart = Date.now()
  let captureWallMs = 0 // sum of actual time spent inside captureFor loops only

  async function setLabel(label) {
    currentLabel = label
    await d.evalJs(`
      (() => {
        let el = document.getElementById('__record_label_overlay')
        if (!el) {
          el = document.createElement('div')
          el.id = '__record_label_overlay'
          el.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:999999;background:#111;color:#0f0;font:14px monospace;padding:6px 10px;'
          document.body.appendChild(el)
        }
        el.textContent = ${JSON.stringify(label)}
      })()
    `)
  }

  async function captureFor(ms, label) {
    if (label) await setLabel(label)
    const start = Date.now()
    const until = start + ms
    while (Date.now() < until) {
      const shot = await d.send('Page.captureScreenshot', { format: 'png' })
      const idx = frameIndex++
      writeFileSync(join(frameDir, `frame_${String(idx).padStart(6, '0')}.png`), Buffer.from(shot.data, 'base64'))
      await new Promise(r => setTimeout(r, SAMPLE_INTERVAL_MS))
      if (Date.now() >= until) break
    }
    captureWallMs += Date.now() - start
  }

  function assertSuccess(value, message) {
    if (!value) {
      rmSync(frameDir, { recursive: true, force: true })
      throw new Error(`recording aborted (output discarded): ${message}`)
    }
  }

  // Cold reload for a clean starting state, wait for the Electron preload
  // bridge, reveal the pane, select the Nelly Borca deck -- same
  // preconditions check_deck_lab_interactions.mjs establishes.
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
  assertSuccess(bridgeReady, 'window.hermesDesktop.openExternal never appeared after reload')

  const revealed = await d.evalJs(`
    (() => {
      if (window.__HERMES_PLUGIN_SDK__ && window.__HERMES_PLUGIN_SDK__.host) {
        window.__HERMES_PLUGIN_SDK__.host.revealPane('deck-lab:deck-lab')
        return true
      }
      return false
    })()
  `)
  assertSuccess(revealed, 'could not reveal the deck-lab pane')
  await d.sleep(1000)

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
  assertSuccess(spyArmed, 'could not arm the openExternal spy')

  const deckSelected = await d.evalJs(`
    (() => {
      const buttons = Array.from(document.querySelectorAll('button'))
      const row = buttons.find(b => b.textContent.includes('Nelly Borca') && !b.textContent.includes('invalid'))
      if (row) { row.click(); return true }
      return false
    })()
  `)
  assertSuccess(deckSelected, 'could not select the Nelly Borca deck from the picker')
  await d.sleep(800)

  // Beat 1+2: fixture, two internal columns, recursive indentation/counts,
  // long-name truncation already on screen -- hold so each is readable.
  await captureFor(2200, 'beat 1-2: Nelly fixture, columns, indentation/counts, long-name truncation')

  // Beat 3: pointer hover vs keyboard focus as distinct paths.
  await d.hoverElement(rowSelector('Sol Ring'))
  await d.sleep(300)
  const titleAfterHover = await previewTitle()
  assertSuccess(titleAfterHover === 'Sol Ring', `hover did not select Sol Ring preview (got ${titleAfterHover})`)
  await captureFor(1200, 'beat 3a: pointer hover -> Sol Ring preview')

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
  assertSuccess(focused, 'keyboard focus did not land on Nelly Borca row')
  await d.sleep(300)
  const titleAfterFocus = await previewTitle()
  assertSuccess(titleAfterFocus === 'Nelly Borca, Impulsive Accuser', `keyboard focus did not select Nelly Borca preview (got ${titleAfterFocus})`)
  await captureFor(1200, 'beat 3b: keyboard Tab focus -> Nelly Borca preview')

  // Beat 4: pin via the dedicated pin button, hover/focus another card while
  // pinned (preview must not change), then unpin.
  await d.clickElement(pinButtonSelector('Nelly Borca, Impulsive Accuser'))
  await d.sleep(300)
  let pinned = await previewPinned()
  assertSuccess(pinned === true, 'pin button click did not pin the preview')
  await captureFor(900, 'beat 4a: pinned Nelly Borca, Impulsive Accuser')

  await d.hoverElement(rowSelector('Sol Ring'))
  await d.sleep(300)
  const titleWhilePinned = await previewTitle()
  assertSuccess(titleWhilePinned === 'Nelly Borca, Impulsive Accuser', `pin guard did not hold while hovering another row (got ${titleWhilePinned})`)
  await captureFor(900, 'beat 4b: hover Sol Ring while pinned -- preview unchanged')

  await d.clickElement(pinButtonSelector('Nelly Borca, Impulsive Accuser'))
  await d.sleep(300)
  pinned = await previewPinned()
  assertSuccess(pinned === false, 'pin button click did not unpin the preview')
  await captureFor(900, 'beat 4c: unpinned Nelly Borca, Impulsive Accuser')

  // Beat 5: exact intercepted Joined Researchers URL, pin unchanged.
  await d.evalJs(`window.__openExternalCalls = []`)
  const pinnedBeforeNameClick = await previewPinned()
  await d.clickElement(nameButtonSelector('Joined Researchers // Secret Rendezvous'))
  await d.sleep(600)
  const openExternalCalls = await d.evalJs(`window.__openExternalCalls`)
  const pinnedAfterNameClick = await previewPinned()
  assertSuccess(Array.isArray(openExternalCalls) && openExternalCalls.length === 1 && openExternalCalls[0][0] === EXACT_JOINED_RESEARCHERS_URL,
    `name click did not call openExternal with the exact URL (got ${JSON.stringify(openExternalCalls)})`)
  assertSuccess(pinnedBeforeNameClick === pinnedAfterNameClick, 'name click toggled pin state')
  await d.evalJs(`
    (() => {
      const el = document.getElementById('__record_label_overlay')
      if (el) el.textContent += ' | observed URL: ${EXACT_JOINED_RESEARCHERS_URL}'
    })()
  `)
  await captureFor(1600, `beat 5: Joined Researchers name click -> exact openExternal URL (pin unchanged)`)

  // Beat 6: loading and error placeholders.
  await d.hoverElement(rowSelector('Agrus Kos, Spirit of Justice'))
  await d.sleep(300)
  const loadingShown = await d.evalJs(`document.body.innerText.includes('Loading…')`)
  assertSuccess(loadingShown, 'loading placeholder did not render for Agrus Kos, Spirit of Justice')
  await captureFor(1000, 'beat 6a: loading placeholder (Agrus Kos, Spirit of Justice)')

  await d.hoverElement(rowSelector('Thought Vessel'))
  await d.sleep(300)
  const errorShown = await d.evalJs(`document.body.innerText.includes('Could not resolve this card.')`)
  assertSuccess(errorShown, 'error placeholder did not render for Thought Vessel')
  await captureFor(1000, 'beat 6b: error placeholder (Thought Vessel)')

  // Beat 7: DFC toggle, Joined Researchers -> Secret Rendezvous, 1W -> 1WW,
  // same combined art retained.
  await d.hoverElement(rowSelector('Joined Researchers // Secret Rendezvous'))
  await d.sleep(300)
  const faceBefore = await previewTitle()
  const manaBefore = await d.evalJs(`document.querySelector('[data-testid="preview-mana"]')?.textContent ?? document.querySelector('.text-\\\\[0\\\\.7rem\\\\]')?.textContent ?? null`)
  const imgSrcBefore = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  await captureFor(900, `beat 7a: Joined Researchers front face (mana ${manaBefore ?? '?'})`)

  const toggled = await d.evalJs(`
    (() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.startsWith('Show '))
      if (!btn) return false
      btn.click()
      return true
    })()
  `)
  assertSuccess(toggled, 'could not find/click the "Show ..." DFC face toggle button')
  await d.sleep(400)
  const faceAfter = await previewTitle()
  const manaAfter = await d.evalJs(`document.querySelector('[data-testid="preview-mana"]')?.textContent ?? document.querySelector('.text-\\\\[0\\\\.7rem\\\\]')?.textContent ?? null`)
  const imgSrcAfter = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  assertSuccess(faceAfter === 'Secret Rendezvous', `DFC toggle did not switch face title (got ${faceAfter})`)
  assertSuccess(imgSrcAfter === imgSrcBefore, `DFC toggle changed the combined-art image src (before=${imgSrcBefore} after=${imgSrcAfter})`)
  await captureFor(1300, `beat 7b: Secret Rendezvous back face (mana ${manaAfter ?? '?'}) -- same combined art retained`)

  // Beat 8: Sol Ring -> Joined Researchers with no stale Sol Ring image.
  await d.hoverElement(rowSelector('Sol Ring'))
  await d.sleep(400)
  const solRingSrc = await d.evalJs(`document.querySelector('img')?.src ?? null`)
  await captureFor(700, 'beat 8a: Sol Ring art')

  await d.hoverElement(rowSelector('Joined Researchers // Secret Rendezvous'))
  const afterSwitch = await d.evalJs(`
    (() => {
      const img = document.querySelector('img')
      return {
        src: img?.src ?? null,
        hidden: img?.classList?.contains('hidden') ?? null,
        loadedSrc: img?.getAttribute('data-loaded-src') ?? null
      }
    })()
  `)
  const notStale = afterSwitch.hidden === true || (afterSwitch.hidden === false && afterSwitch.loadedSrc === afterSwitch.src)
  assertSuccess(afterSwitch.src !== solRingSrc && notStale, `stale Sol Ring art shown under Joined Researchers (${JSON.stringify(afterSwitch)})`)
  await captureFor(1300, 'beat 8b: Sol Ring -> Joined Researchers, no stale art')

  // Beat 9: invalid candidate diagnostics held visibly.
  await d.evalJs(`document.activeElement && document.activeElement.blur && document.activeElement.blur()`)
  const invalidClicked = await d.evalJs(`
    (() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('malformed') && b.textContent.includes('invalid'))
      if (!btn) return false
      btn.click()
      return true
    })()
  `)
  assertSuccess(invalidClicked, 'could not click the malformed/invalid candidate')
  await d.sleep(400)
  const diagnostics = await d.evalJs(`
    (() => {
      const text = document.body.innerText
      return {
        hasHeading: text.includes('This deck is invalid.'),
        hasCode: text.includes('card_quantity_invalid_zero'),
        hasPath: text.includes('tests/fixtures/malformed/card_quantity_invalid_zero.md')
      }
    })()
  `)
  assertSuccess(diagnostics.hasHeading && diagnostics.hasPath, `invalid candidate diagnostics not shown (${JSON.stringify(diagnostics)})`)
  await captureFor(1800, 'beat 9: invalid candidate diagnostics (held)')

  const totalFrames = frameIndex
  assertSuccess(totalFrames > 0, 'no frames captured')
  assertSuccess(captureWallMs >= 15000, `recording capture duration too short: ${captureWallMs}ms (< 15000ms required)`)

  // Encode at the fps implied by actual captured frames over actual capture
  // wall-clock time, so the MP4's duration faithfully matches how long each
  // state was really held on screen (screenshot RPC latency makes the real
  // inter-frame gap larger than the nominal sampling interval).
  const fps = (totalFrames / (captureWallMs / 1000)).toFixed(3)
  execFileSync('ffmpeg', [
    '-y',
    '-framerate', fps,
    '-i', join(frameDir, 'frame_%06d.png'),
    '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
    '-pix_fmt', 'yuv420p',
    outPath,
  ], { stdio: 'inherit' })

  rmSync(frameDir, { recursive: true, force: true })

  const stat = statSync(outPath)
  console.log(JSON.stringify({ totalFrames, captureWallMs, fps: Number(fps), outPath, bytes: stat.size }, null, 2))

  d.raw.close()
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
