"""Scryfall batch resolver lane skeleton (t_5d228091).

Importable sentinel only -- no batching/network behavior implemented.
"""

from __future__ import annotations


def resolve_collection(identifiers, http_client=None, dry_run=False):
    """Not implemented: returns a single oversized batch (no 75-cap logic),
    so the lane's RED test fails at its `len(batch) <= 75` assertion."""

    return [list(identifiers)]
