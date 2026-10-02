"""Mechanically compares deck_lab.ui.fixture.FIXTURE against the golden Nelly
Borca README/mainboard Markdown (t_d80e077c architect review).

Deliberately does NOT import deck_lab.parser / deck_lab.scanner -- those lanes
are separate, unfinished cards. This reads the golden Markdown directly with
a small purpose-built regex walk, so the invariant holds even while the
production parser is still being built.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from deck_lab.ui.fixture import FIXTURE

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "nelly-borca" / "decks" / "commander" / "nelly-borca"
README_PATH = FIXTURES_ROOT / "README.md"
MAINBOARD_PATH = FIXTURES_ROOT / "mainboard.md"

HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
CARD_ROW_RE = re.compile(r"^(\d+)\s+(.+?)\s*$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    assert m, "golden fixture missing frontmatter"
    out = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def _parse_mainboard(text: str) -> list[tuple[list[str], list[tuple[int, str]]]]:
    """Walk heading levels 2..6 as a category path stack; within a
    ```decklist fenced block, collect (quantity, name) rows. Returns a list
    of (path, cards) per leaf-with-cards category, in document order."""
    lines = text.splitlines()
    stack: list[tuple[int, str]] = []  # (level, name), level relative (## = 2)
    out: list[tuple[list[str], list[tuple[int, str]]]] = []
    in_fence = False
    current_cards: list[tuple[int, str]] = []

    def path_for_stack() -> list[str]:
        return [name for _, name in stack]

    for line in lines:
        if line.strip() == "```decklist":
            in_fence = True
            current_cards = []
            continue
        if line.strip() == "```" and in_fence:
            in_fence = False
            if current_cards:
                out.append((path_for_stack(), current_cards))
            continue
        if in_fence:
            m = CARD_ROW_RE.match(line)
            if m:
                current_cards.append((int(m.group(1)), m.group(2)))
            continue
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            name = m.group(2)
            if level == 1:
                continue  # document title, not a category
            while stack and stack[-1][0] >= level:
                stack.pop()
            # Collapse a subheading that merely repeats its parent's name
            # (e.g. "## Commander" > "### Commander") into one path segment --
            # the real category path has no duplicate consecutive names.
            if stack and stack[-1][1] == name:
                stack[-1] = (level, name)
            else:
                stack.append((level, name))
    return out


def _golden_card_multiset() -> set[tuple[int, str]]:
    text = MAINBOARD_PATH.read_text()
    categories = _parse_mainboard(text)
    multiset: set[tuple[int, str]] = set()
    for _path, cards in categories:
        for qty, name in cards:
            multiset.add((qty, name))
    return multiset


def _golden_category_paths() -> set[tuple[str, ...]]:
    text = MAINBOARD_PATH.read_text()
    categories = _parse_mainboard(text)
    return {tuple(path) for path, _cards in categories}


def _fixture_mainboard_categories():
    mainboard = FIXTURE["decks"][0]["boards"][0]

    def walk(categories):
        for cat in categories:
            if cat.get("cards"):
                yield cat["path"], cat["cards"]
            yield from walk(cat.get("subcategories", []))

    return list(walk(mainboard["categories"]))


def test_golden_mainboard_file_exists():
    assert MAINBOARD_PATH.is_file()
    assert README_PATH.is_file()


def test_fixture_card_multiset_matches_golden_markdown_exactly():
    golden = _golden_card_multiset()
    fixture_cards = set()
    for _path, cards in _fixture_mainboard_categories():
        for card in cards:
            fixture_cards.add((card["quantity"], card["name"]))
    assert fixture_cards == golden


def test_fixture_category_paths_match_golden_markdown_exactly():
    golden_paths = _golden_category_paths()
    fixture_paths = {tuple(path) for path, _cards in _fixture_mainboard_categories()}
    assert fixture_paths == golden_paths


def test_fixture_board_count_matches_golden_single_mainboard():
    nelly = next(d for d in FIXTURE["decks"] if d["name"] == "Nelly Borca")
    assert len(nelly["boards"]) == 1
    assert nelly["boards"][0]["kind"] == "mainboard"


def test_fixture_status_and_tags_match_golden_readme_frontmatter():
    fm = _frontmatter(README_PATH.read_text())
    readme_text = README_PATH.read_text()
    nelly = next(d for d in FIXTURE["decks"] if d["name"] == "Nelly Borca")
    assert nelly["status"] == fm["status"]
    tags_block = re.search(r"tags:\n((?:\s*-\s*.+\n?)+)", readme_text)
    assert tags_block
    golden_tags = re.findall(r"-\s*(\S+)", tags_block.group(1))
    assert nelly["tags"] == golden_tags


@pytest.mark.parametrize(
    "path,quantity",
    [
        (("Deck", "Veggies", "Interaction", "Removal"), 7),
        (("Commander",), 1),
    ],
)
def test_golden_parser_finds_expected_leaf_categories(path, quantity):
    golden = dict(
        (tuple(p), sum(q for q, _ in cards)) for p, cards in _parse_mainboard(MAINBOARD_PATH.read_text())
    )
    assert golden[path] == quantity
