"""RED contract test for the Scryfall batch resolver lane (t_5d228091).

Fails at import time: `deck_lab.scryfall` does not exist yet. That is the
intended RED signal for this contract card.
"""

from deck_lab.scryfall import resolve_collection  # noqa: F401


def test_resolve_collection_caps_identifiers_at_75_per_request():
    identifiers = [{"name": f"Card {i}"} for i in range(80)]
    batches = resolve_collection(identifiers, http_client=None, dry_run=True)
    assert all(len(batch) <= 75 for batch in batches)
