"""Moxfield bulk adapter lane skeleton (t_e5e51273).

Minimal importable parsing only -- enough to reach rows by name, but
deliberately preserves provider-only finish markers (e.g. `*F*`) instead of
stripping them, so the lane's RED test fails at its named assertion rather
than at import or at an unrelated `StopIteration`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ROW_RE = re.compile(r"^(\d+)\s+(.+)$")


@dataclass(frozen=True)
class Card:
    quantity: int
    name: str


@dataclass(frozen=True)
class ImportResult:
    cards: list = field(default_factory=list)


def import_text(text: str) -> ImportResult:
    """Not implemented: splits quantity/name but does not strip
    provider-only finish markers, so the lane's RED test fails at its
    `"*F*" not in arcane_signet.name` assertion."""

    cards = []
    for line in text.splitlines():
        match = _ROW_RE.match(line.strip())
        if match:
            cards.append(Card(quantity=int(match.group(1)), name=match.group(2)))
    return ImportResult(cards=cards)
