// Reusable CDP driver for the live Deck Lab pane.
//
// Connects to a running Hermes desktop instance over the Chrome DevTools
// Protocol (default ws target: first "page" at --remote-debugging-port, e.g.
// 127.0.0.1:9333), drives the real plugin render tree with real pointer/
// keyboard input (not synthetic event dispatch that may bypass React's
// delegated handlers), and exposes small helpers used by both:
//   - scripts/check_deck_lab_interactions.mjs (executable interaction proof)
//   - the replacement screencast recording
//
// Exports a `connect(cdpUrl)` that returns a driver object. Intentionally
// framework-free (no puppeteer dependency) so it runs with plain Node's
// built-in fetch + WebSocket globals (Node 22+).

export async function discoverTarget(host = '127.0.0.1', port = 9333) {
  const res = await fetch(`http://${host}:${port}/json`)
  const targets = await res.json()
  const page = targets.find(t => t.type === 'page') ?? targets[0]
  if (!page) throw new Error('no CDP page target found')
  return page
}

export async function connect(wsUrl) {
  const ws = new globalThis.WebSocket(wsUrl)
  let id = 1
  const pending = new Map()
  const eventListeners = new Map()

  ws.addEventListener('message', ev => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      if (msg.error) reject(new Error(JSON.stringify(msg.error)))
      else resolve(msg.result)
      return
    }
    if (msg.method && eventListeners.has(msg.method)) {
      for (const fn of eventListeners.get(msg.method)) fn(msg.params)
    }
  })

  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve)
    ws.addEventListener('error', reject)
  })

  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const thisId = id++
      pending.set(thisId, { resolve, reject })
      ws.send(JSON.stringify({ id: thisId, method, params }))
    })
  }

  function on(method, fn) {
    if (!eventListeners.has(method)) eventListeners.set(method, [])
    eventListeners.get(method).push(fn)
  }

  function sleep(ms) {
    return new Promise(r => setTimeout(r, ms))
  }

  async function evalJs(expr) {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails))
    return r.result?.value
  }

  // Returns the content-box box model {x, y, width, height} for the element
  // matched by `selectorExpr`, a JS expression (evaluated in-page) returning
  // an Element. Used to compute real click/hover coordinates for CDP
  // Input.dispatchMouseEvent, instead of dispatching a synthetic event
  // directly on the node (which can bypass React's delegated listener path).
  // Returns the viewport-relative center point of the element matched by
  // `selectorExpr` (a JS expression evaluated in-page, returning an
  // Element), using getBoundingClientRect -- CSS pixels, the same
  // coordinate space Input.dispatchMouseEvent expects. (DOM.getBoxModel
  // returns device pixels and needs a devicePixelRatio correction that
  // proved fragile across the app's own CSS zoom; getBoundingClientRect
  // sidesteps that entirely.) Scrolls the element into view first so an
  // off-screen row still resolves to a clickable point.
  async function boxModelFor(selectorExpr) {
    const rect = await evalJs(`
      (() => {
        const el = ${selectorExpr}
        if (!el) return null
        el.scrollIntoView({ block: 'center', inline: 'nearest' })
        const r = el.getBoundingClientRect()
        return { x: r.x + r.width / 2, y: r.y + r.height / 2, width: r.width, height: r.height }
      })()
    `)
    return rect
  }

  async function evalNodeId(selectorExpr) {
    const { result } = await send('Runtime.evaluate', { expression: selectorExpr })
    if (!result.objectId) return null
    const { nodeId } = await send('DOM.requestNode', { objectId: result.objectId })
    return nodeId
  }

  // Real OS-level pointer move+hover over the element matched by
  // `selectorExpr`, so React's synthetic onMouseEnter (delegated from a root
  // listener) genuinely fires -- not a bare dispatchEvent('mouseenter') on
  // the node, which can be a no-op for React's event system.
  async function hoverElement(selectorExpr) {
    const box = await boxModelFor(selectorExpr)
    if (!box) throw new Error(`hoverElement: no box model for ${selectorExpr}`)
    // Move away first so the browser's real pointer-tracking sees a genuine
    // enter transition (moving within the same coordinates the pointer is
    // already at does not re-fire mouseenter/mouseover).
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 2, y: 2 })
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x, y: box.y })
    return box
  }

  // Real OS-level left click (mousePressed + mouseReleased) at the element's
  // center, routed through CDP Input -- exercises the same event path a real
  // user click does, unlike a synthetic MouseEvent dispatch.
  async function clickElement(selectorExpr) {
    const box = await boxModelFor(selectorExpr)
    if (!box) throw new Error(`clickElement: no box model for ${selectorExpr}`)
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x, y: box.y, button: 'left', clickCount: 1 })
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x, y: box.y, button: 'left', clickCount: 1 })
    return box
  }

  // Clicks somewhere inside the row-group element matched by `selectorExpr`
  // that is NOT its own name <button> or a `[role=separator]` resize handle
  // overlapping the row's left edge -- both of which the row's geometric
  // center/left edge can land on depending on the live pane's current
  // width. Scans a few candidate x-offsets via elementFromPoint and uses
  // the first one that resolves to the row itself or a non-interactive
  // descendant (not BUTTON, not `[role=separator]`), so the click reaches
  // the row's own onClick (pin toggle) instead of stopPropagation'd or
  // unrelated UI.
  async function clickRowBackground(rowSelectorExpr) {
    const rect = await evalJs(`
      (() => {
        const el = ${rowSelectorExpr}
        if (!el) return null
        el.scrollIntoView({ block: 'center', inline: 'nearest' })
        const r = el.getBoundingClientRect()
        return { x: r.x, y: r.y, width: r.width, height: r.height }
      })()
    `)
    if (!rect) throw new Error(`clickRowBackground: no box model for ${rowSelectorExpr}`)
    const candidateOffsets = [10, 6, rect.width - 8, rect.width * 0.5, rect.width * 0.3]
    for (const dx of candidateOffsets) {
      const px = rect.x + dx
      const py = rect.y + rect.height / 2
      // eslint-disable-next-line no-await-in-loop
      const tag = await evalJs(`document.elementFromPoint(${px}, ${py})?.tagName ?? null`)
      // eslint-disable-next-line no-await-in-loop
      const role = await evalJs(`document.elementFromPoint(${px}, ${py})?.getAttribute?.('role') ?? null`)
      if (tag && tag !== 'BUTTON' && role !== 'separator') {
        await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: px, y: py, button: 'left', clickCount: 1 })
        await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: px, y: py, button: 'left', clickCount: 1 })
        return { x: px, y: py, tag, role }
      }
    }
    throw new Error(`clickRowBackground: no safe click point found for ${rowSelectorExpr}`)
  }

  // Real keyboard Tab presses via CDP Input.dispatchKeyEvent, moving focus
  // forward through the DOM's tab order -- exercises onFocus the same way a
  // keyboard user would, rather than calling element.focus() directly.
  async function pressTab(times = 1) {
    for (let i = 0; i < times; i += 1) {
      await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 })
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 })
    }
  }

  return { send, on, sleep, evalJs, boxModelFor, hoverElement, clickElement, clickRowBackground, pressTab, raw: ws }
}
