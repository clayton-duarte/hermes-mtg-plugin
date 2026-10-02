"""Hermes plugin entrypoint for Deck Lab (card t_b5b4148d).

The real plugin loader (``hermes_cli.plugins_loader``) imports a directory
plugin's root package and calls its ``register(ctx)`` exactly once. This
module is that single seam: it delegates immediately to
``deck_lab.tools.register_tools``, which owns the actual tool list and
schemas. No tool logic lives here.
"""

from __future__ import annotations

from deck_lab.tools import register_tools


def register(ctx) -> None:
    """Entry point called once by the Hermes plugin loader."""
    register_tools(ctx)
