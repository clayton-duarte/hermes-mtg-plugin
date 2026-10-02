"""Executable host-shaped tests for the Deck Lab pane's live wiring
(card t_f0bff516).

These tests actually EXECUTE the real functions shipped in
desktop/plugin.js (restQuery, buildCategoryTree) with real inputs via a
Node harness, instead of grepping source text for expected substrings. A
source grep can stay green while the generated URL is malformed (the
exact defect PR #11 review caught at 6366e3a: restQuery blindly
concatenated a second `?`, swallowing `workspace_root` into
`board_path`) -- an executed check against the real function body cannot.

A few structural/config assertions that have no runtime behavior to
execute (cadence constant, absence of a leaked hand-rolled timer, the
payload-vs-top-level-name read site for tool.complete) remain source
checks; they are not claimed as behavioral proof.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JS = REPO_ROOT / "desktop" / "plugin.js"
RESTQUERY_CHECK = REPO_ROOT / "scripts" / "check_restquery_workspace_root.mjs"
CATEGORY_TREE_CHECK = REPO_ROOT / "scripts" / "check_build_category_tree.mjs"


def _source() -> str:
    return PLUGIN_JS.read_text()


def _run_node_check(script: Path, env_overrides: dict[str, str] | None = None) -> dict:
    import os

    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.run(
        ["node", str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        raise AssertionError(
            f"{script.name} produced non-JSON stdout (rc={proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        ) from exc
    return {"returncode": proc.returncode, "payload": payload}


# --- restQuery(): real execution against two focused roots -----------------


def test_restquery_never_produces_a_second_question_mark():
    """Executes the real restQuery() from desktop/plugin.js against a path
    that already has a query string (the exact /deck?path=...&board_path=...
    shape that previously swallowed workspace_root into board_path at
    6366e3a) and asserts the generated URL parses to distinct, correct
    path/board_path/workspace_root params."""
    result = _run_node_check(RESTQUERY_CHECK)
    assert result["returncode"] == 0, result["payload"]
    results = result["payload"]["results"]
    assert results, result["payload"]
    failed = {k: v for k, v in results.items() if not v["pass"]}
    assert not failed, f"restQuery check(s) failed: {json.dumps(failed, indent=2)}"


def test_restquery_two_focused_roots_produce_distinct_workspace_root_params():
    """The same check run above also asserts two distinct workspace roots
    produce two distinct, correct workspace_root query values -- proving
    requests are focused per-root rather than reading a shared/implicit cwd.
    """
    result = _run_node_check(RESTQUERY_CHECK)
    assert result["returncode"] == 0, result["payload"]
    check = result["payload"]["results"]["two_roots_produce_distinct_workspace_root"]
    assert check["pass"], check


def test_restquery_mutation_control_reproduces_the_rejected_defect():
    """Deletion check: a naive `path + '?' + params` restQuery (the exact
    code shipped at the rejected head 6366e3a) must make this check's own
    named assertion fail -- proving the check discriminates the real bug,
    not just always-passes."""
    result = _run_node_check(
        RESTQUERY_CHECK, env_overrides={"CHECK_RESTQUERY_MUTATE": "1"}
    )
    assert result["returncode"] == 0, result["payload"]
    check = result["payload"]["results"]["mutation_reproduces_swallowed_workspace_root"]
    assert check["pass"], (
        "mutation control did not reproduce the rejected defect -- the "
        f"restQuery check may not actually discriminate it: {check}"
    )


# --- buildCategoryTree(): real execution turning /deck's flat card list -----
# --- into the nested shape DecklistColumn renders ---------------------------


def test_build_category_tree_renders_real_nested_categories_from_flat_cards():
    """Executes the real buildCategoryTree() from desktop/plugin.js against
    a realistic flat `/deck` cards list (each carrying category_path) and
    asserts the nested category/subcategory/card tree DecklistColumn expects
    comes out correct -- list-to-detail rendering, proven by execution."""
    result = _run_node_check(CATEGORY_TREE_CHECK)
    assert result["returncode"] == 0, result["payload"]
    results = result["payload"]["results"]
    failed = {k: v for k, v in results.items() if not v["pass"]}
    assert not failed, f"buildCategoryTree check(s) failed: {json.dumps(failed, indent=2)}"


def test_build_category_tree_mutation_control_catches_a_flattened_tree():
    result = _run_node_check(
        CATEGORY_TREE_CHECK, env_overrides={"CHECK_CATEGORY_TREE_MUTATE": "1"}
    )
    assert result["returncode"] == 0, result["payload"]
    check = result["payload"]["results"]["mutation_loses_ramp_subcategory"]
    assert check["pass"], check


# --- Structural checks with no independent runtime behavior to execute -----


def test_decks_query_fetches_through_ctx_rest_not_the_bundled_fixture():
    src = _source()
    assert "ctx.rest(" in src or "ctx?.rest(" in src, (
        "expected the pane to fetch decks via ctx.rest(...); "
        "found no ctx.rest(...) call in desktop/plugin.js"
    )
    assert "queryFn: () => Promise.resolve(FIXTURE)" not in src, (
        "the decks query must no longer resolve the static bundled FIXTURE "
        "as its live data source"
    )
    assert "placeholderData: FIXTURE" not in src, (
        "the pane must not show the bundled FIXTURE as placeholder/initial "
        "data in production"
    )


def test_decks_query_polls_on_a_cheap_two_second_interval():
    src = _source()
    match = re.search(r"refetchInterval:\s*(\d+)", src)
    assert match is not None, "expected a refetchInterval on the revision query"
    interval_ms = int(match.group(1))
    assert 1500 <= interval_ms <= 3000, (
        f"refetchInterval {interval_ms}ms is not an ~2s cheap poll"
    )
    # The authoritative poll must be on /revision (cheap), not /decks
    # (a full scan/parse route) -- see review finding 3 at 6366e3a.
    assert "queryFn: () => ctx.rest(restQuery('/revision'))" in src, (
        "expected the 2s poll to target /revision, not re-poll the "
        "expensive /decks scan route directly"
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
    assert "setInterval(" not in src, (
        "hand-rolled setInterval found; use useQuery's refetchInterval "
        "(owned/cleared by the shared QueryClient) instead"
    )


def test_tool_complete_handler_reads_the_tool_name_from_the_payload():
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


def test_revision_change_invalidates_decks_and_deck_queries():
    src = _source()
    assert "if (revision === null) return" in src, (
        "expected the revision-change effect to bail out before the first "
        "revision has been observed"
    )
    assert "qc.invalidateQueries({ queryKey: [ID, 'decks', workspaceRoot] })" in src
    assert "qc.invalidateQueries({ queryKey: [ID, 'deck', workspaceRoot] })" in src


def test_selection_is_reset_and_reloaded_on_repository_change():
    src = _source()
    assert "storageKeyFor" in src, (
        "expected a storage-key helper keyed by repository identity"
    )
    assert "revisionData?.repository_id" in src, (
        "expected selection persistence to key off the live repository_id, "
        "not just workspaceRoot (two cwds can resolve to the same repo, and "
        "a repo can move cwd across reloads)"
    )
    # The reset effect must clear board/pin/hover/face state, not just
    # selectedPath, when the repository identity changes.
    assert "setBoardIndex(0)" in src and "setPinnedCard(null)" in src and "setHoveredCard(null)" in src and "setFaceIndex(0)" in src


def test_repository_and_board_loading_error_empty_states_are_distinct():
    src = _source()
    for testid in (
        "repository-error",
        "repository-loading",
        "repository-empty",
        "board-error",
        "board-loading",
        "board-empty",
    ):
        assert f"'{testid}'" in src or f'"{testid}"' in src, (
            f"expected a distinct data-testid={testid!r} state so a network "
            "failure/loading/empty-repo never collapse into the same "
            "'Select a deck' placeholder"
        )
