"""ManaBox/Arena interchange adapter lane skeleton (t_21314a59).

Importable sentinel only -- no dialect parsing implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportResult:
    cards: list = field(default_factory=list)


def import_text(text: str, dialect: str) -> ImportResult:
    """Not implemented: returns no cards, so the lane's RED test fails at
    its `len(commander_rows) == 1` assertion rather than at import."""

    return ImportResult()
