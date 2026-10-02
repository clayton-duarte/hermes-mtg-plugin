"""Parser/validator lane skeleton (t_09bc9ceb).

This module exists only so the lane's RED contract test can import
successfully and fail on its named assertion, not on
`ModuleNotFoundError`. No parsing behavior is implemented here -- that is
the parser lane's own job.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParseResult:
    """Sentinel result shape. `cards` is intentionally always empty until
    the parser lane implements real Markdown decklist parsing."""

    cards: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def parse_board(text: str, path: str) -> ParseResult:
    """Not implemented: returns an empty, always-wrong result so the lane's
    RED test fails at its `total == 100` assertion rather than at import."""

    return ParseResult()
