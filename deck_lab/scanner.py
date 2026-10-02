"""Repository scanner lane skeleton (t_eb91eeab).

Importable sentinel only -- no scanning behavior implemented. Keeps the
lane's RED test failing on its named assertion instead of on import.
"""

from __future__ import annotations

from pathlib import Path


def scan_repository(decks_root: Path):
    """Not implemented: always returns no deck summaries, so the lane's RED
    test fails at its `any(...)` assertion rather than at import."""

    return []
