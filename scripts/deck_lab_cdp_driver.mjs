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

  // Clicks the row-group element's own quantity `<span>` (its first child,
  // a non-interactive node that is never a <button> and never the
  // `[role=separator]` resize handle) via real CDP
  // Input.dispatchMouseEvent -- an actual OS-level pointer press/release at
  // on-screen coordinates, not a synthetic dispatchEvent. This genuinely
  // exercises the row's own onClick (CardRow.onRowActivate / onPinToggle),
  // because the click lands within the row's bounding box but outside the
  // name/pin <button>s, and React's delegated root listener observes a
  // trusted click the same way it would for a real user. Coordinates come
  // from the unscaled getBoundingClientRect() center of the quantity span
  // (not DOM.getBoxModel, and not scaled by outerWidth/innerWidth), matching
  // the deterministic route proven live for this harness.
  async function clickRowBackground(rowSelectorExpr) {
    // The row itself (the `[role=group]` flex container) only paints as a
    // hit-testable surface in the narrow flex `gap` between its children
    // (it has no padding box of its own outside their bounds, and a
    // column-resize `[role=separator]` overlay from an adjacent column can
    // cover area to its left). Probe every point along the row's own
    // bounding box and use the first that hit-tests back to the row
    // element itself -- never a descendant button/span or an unrelated
    // overlapping element -- so the click unambiguously reaches the row's
    // own onClick (not a coordinate guess).
    const groupCheck = await evalJs(`
      (() => {
        const row = ${rowSelectorExpr}
        if (!row) return { ok: false, reason: 'row not found' }
        if (row.getAttribute('role') !== 'group') return { ok: false, reason: 'selector did not resolve to a [role=group] row' }
        return { ok: true }
      })()
    `)
    if (!groupCheck?.ok) throw new Error(`clickRowBackground: ${groupCheck?.reason ?? 'unknown failure'} for ${rowSelectorExpr}`)
    await evalJs(`
      (() => {
        const row = ${rowSelectorExpr}
        row.scrollIntoView({ block: 'center', inline: 'nearest' })
      })()
    `)
    await sleep(200)
    const rect = await evalJs(`
      (() => {
        const row = ${rowSelectorExpr}
        const r = row.getBoundingClientRect()
        const y = r.y + r.height / 2
        for (let x = r.x + 1; x < r.x + r.width; x += 1) {
          if (document.elementFromPoint(x, y) === row) return { x, y, width: r.width, height: r.height }
        }
        return null
      })()
    `)
    if (!rect) throw new Error(`clickRowBackground: no point along ${rowSelectorExpr}'s own bounding box hit-tests to the row itself (always resolves to a descendant or overlapping element)`)
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: rect.x, y: rect.y, button: 'left', clickCount: 1 })
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: rect.x, y: rect.y, button: 'left', clickCount: 1 })
    return { dispatched: true, box: rect }
  }

  // Synthetic (non-trusted) variant used ONLY by the mutation control for
  // the trusted-row-input assertion -- proves the named check actually
  // discriminates real CDP input from a bare dispatchEvent.
  async function clickRowBackgroundSynthetic(rowSelectorExpr) {
    await evalJs(`
      (() => {
        const el = ${rowSelectorExpr}
        if (el) el.scrollIntoView({ block: 'center', inline: 'nearest' })
      })()
    `)
    await sleep(150)
    const dispatched = await evalJs(`
      (() => {
        const row = ${rowSelectorExpr}
        if (!row) return false
        const opts = { bubbles: true, cancelable: true, view: window, button: 0 }
        row.dispatchEvent(new MouseEvent('mousedown', opts))
        row.dispatchEvent(new MouseEvent('mouseup', opts))
        row.dispatchEvent(new MouseEvent('click', opts))
        return true
      })()
    `)
    if (!dispatched) throw new Error(`clickRowBackgroundSynthetic: row not found for ${rowSelectorExpr}`)
    return { dispatched: true }
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

  return { send, on, sleep, evalJs, boxModelFor, hoverElement, clickElement, clickRowBackground, clickRowBackgroundSynthetic, pressTab, raw: ws }
}
