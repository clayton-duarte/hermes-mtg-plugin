"""RED contract test for wiring the Deck Lab pane to live API data
(card t_f0bff516).

`desktop/plugin.js` renders from a bundled, hardcoded FIXTURE via
`queryFn: () => Promise.resolve(FIXTURE)`. This is a static source check
(same convention as test_ui_fixture_js_parity.py) that the pane instead
goes through the real plugin REST door (`ctx.rest`), polls on an
~2s revision cadence, refetches immediately on cwd change, and never
leaks timers -- without requiring a live Electron/Chrome runtime to
execute the JSX.
"""

from __future__ import annotations

import re
from pathlib import Path

PLUGIN_JS = Path(__file__).parent.parent / "desktop" / "plugin.js"


def _source() -> str:
    return PLUGIN_JS.read_text()


def test_decks_query_fetches_through_ctx_rest_not_the_bundled_fixture():
    src = _source()
    # The decks list query must be driven by ctx.rest, not a hardcoded
    # Promise.resolve(FIXTURE) -- the live-wiring requirement this card adds.
    assert "ctx.rest(" in src or "ctx?.rest(" in src, (
        "expected the pane to fetch decks via ctx.rest(...); "
        "found no ctx.rest(...) call in desktop/plugin.js"
    )
    assert "queryFn: () => Promise.resolve(FIXTURE)" not in src, (
        "the decks query must no longer resolve the static bundled FIXTURE "
        "as its live data source"
    )


def test_decks_query_polls_on_a_cheap_two_second_interval():
    src = _source()
    match = re.search(r"refetchInterval:\s*(\d+)", src)
    assert match is not None, "expected a refetchInterval on the decks query"
    interval_ms = int(match.group(1))
    assert 1500 <= interval_ms <= 3000, (
        f"refetchInterval {interval_ms}ms is not an ~2s cheap poll"
    )


def test_cwd_change_triggers_an_immediate_refetch():
    src = _source()
    assert "host.state.cwd" in src, (
        "expected the pane to subscribe to host.state.cwd so switching the "
        "focused project refetches immediately instead of waiting for the "
        "next poll tick"
    )


def test_no_hand_rolled_timers_leak_past_component_unmount():
    src = _source()
    # The SDK's useQuery/refetchInterval already owns polling; a plugin must
    # not also hand-roll setInterval/setTimeout for the same cadence, which
    # would leak a timer handle past unmount/dispose.
    assert "setInterval(" not in src, (
        "hand-rolled setInterval found; use useQuery's refetchInterval "
        "(owned/cleared by the shared QueryClient) instead"
    )


def test_tool_complete_handler_reads_the_tool_name_from_the_payload():
    # GatewayEvent<'tool.complete'> wraps the real ToolCompletePayload under
    # `.payload` (see apps/shared/src/gateway-events.ts GatewayEvent<K> and
    # ToolCompletePayload.name in gateway-contract.generated.ts) -- the top
    # level event object has no `name` field of its own. Reading `event.name`
    # is always undefined and the deck_import invalidation never fires.
    src = _source()
    assert "event?.payload?.name === 'deck_import'" in src, (
        "expected the tool.complete handler to read the tool name from "
        "event.payload.name (the GatewayEvent<'tool.complete'> contract), "
        "not event.name"
    )
    assert re.search(r"event\?\.name\s*===\s*'deck_import'", src) is None, (
        "tool.complete handler still reads event.name directly; "
        "GatewayEvent has no top-level name field, only event.payload.name"
    )
