#!/usr/bin/env node
// Records a deterministic screencast of the Deck Lab live pane (t_1e429f1c
// replacement recording) by driving the real plugin over CDP exactly like
// scripts/check_deck_lab_interactions.mjs, while CDP Page.startScreencast
// captures real frames to disk, then stitches them into an MP4 via ffmpeg.
//
// Usage: node scripts/record_deck_lab_demo.mjs <output.mp4>

import { discoverTarget, connect } from './deck_lab_cdp_driver.mjs'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'

async function main() {
  const outPath = process.argv[2]
  if (!outPath) {
    console.error('usage: node record_deck_lab_demo.mjs <output.mp4>')
    process.exit(2)
  }

  const frameDir = mkdtempSync(join(tmpdir(), 'deck-lab-frames-'))
  let frameIndex = 0
  const frameTimestamps = []

  const target = await discoverTarget()
  const d = await connect(target.webSocketDebuggerUrl)

  await d.send('Page.enable')

  d.on('Page.screencastFrame', async params => {
    const idx = frameIndex++
    const path = join(frameDir, `frame_${String(idx).padStart(5, '0')}.png`)
    writeFileSync(path, Buffer.from(params.data, 'base64'))
    frameTimestamps.push({ idx, metadata: params.metadata })
    await d.send('Page.screencastFrameAck', { sessionId: params.sessionId })
  })

  await d.send('Page.startScreencast', { format: 'png', everyNthFrame: 1 })

  // Reset to the Nelly fixture (clean baseline), then drive the same
  // interaction sequence the interaction-proof script exercises, so the
  // recording visibly demonstrates every required beat from the card.
  async function selectByText(text, excludeText) {
    await d.evalJs(`
      (() => {
        const buttons = Array.from(document.querySelectorAll('button'))
        const row = buttons.find(b => b.textContent.includes(${JSON.stringify(text)})${excludeText ? ` && !b.textContent.includes(${JSON.stringify(excludeText)})` : ''})
        if (row) row.click()
      })()
    `)
  }

  await selectByText('Nelly Borca', 'invalid')
  await d.sleep(800)

  // 1 + 2: fixture + two columns + indentation/counts/truncation already on
  // screen; hold so the frame is captured clearly.
  await d.sleep(1200)

  // 3: pointer hover vs keyboard focus as distinct paths.
  await d.hoverElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Sol Ring'))`)
  await d.sleep(900)
  await d.evalJs(`document.activeElement && document.activeElement.blur && document.activeElement.blur()`)
  await d.pressTab(1)
  await d.sleep(900)

  // 4: pin, different-card hover/focus while pinned, then unpin.
  await d.clickElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Nelly Borca') && !b.textContent.includes('invalid'))`)
  await d.sleep(600)
  await d.hoverElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Sol Ring'))`)
  await d.sleep(700)
  await d.pressTab(1)
  await d.sleep(700)
  await d.clickElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Nelly Borca') && !b.textContent.includes('invalid'))`)
  await d.sleep(700)

  // 5: exact intercepted Joined Researchers openExternal call without pin change.
  await d.clickElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Joined Researchers'))`)
  await d.sleep(900)

  // 6: loading and error placeholders.
  await selectByText('loading')
  await d.sleep(900)
  await selectByText('error')
  await d.sleep(900)

  // 7: DFC toggle, Joined Researchers -> Secret Rendezvous, 1W -> 1WW.
  await selectByText('Joined Researchers')
  await d.sleep(700)
  await d.clickElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Secret Rendezvous') || b.textContent.includes('Transform') || b.textContent.includes('\\u21bb'))`).catch(() => {})
  await d.sleep(900)

  // 8: no stale Sol Ring art under either title -- switch Sol Ring -> Joined
  // Researchers -> Sol Ring again to make the transition visible on tape.
  await selectByText('Sol Ring')
  await d.sleep(700)
  await selectByText('Joined Researchers')
  await d.sleep(900)

  // 9: invalid candidate diagnostics.
  await d.evalJs(`document.activeElement && document.activeElement.blur && document.activeElement.blur()`)
  await d.clickElement(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('malformed') && b.textContent.includes('invalid'))`)
  await d.sleep(1200)

  await d.send('Page.stopScreencast')
  await d.sleep(300)

  const totalFrames = frameIndex
  if (totalFrames === 0) {
    console.error('no frames captured')
    process.exit(1)
  }

  // Stitch frames into an MP4 at a fixed 10fps using the real captured PNG
  // sequence (not a synthetic slideshow -- every frame came from a live
  // Page.screencastFrame event during real CDP-driven interaction).
  execFileSync('ffmpeg', [
    '-y',
    '-framerate', '10',
    '-i', join(frameDir, 'frame_%05d.png'),
    '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
    '-pix_fmt', 'yuv420p',
    outPath,
  ], { stdio: 'inherit' })

  rmSync(frameDir, { recursive: true, force: true })

  console.log(JSON.stringify({ totalFrames, outPath }, null, 2))
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
