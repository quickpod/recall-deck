"""recalldeck -- a pure-stdlib, offline spaced-repetition flashcard engine.

Everything is built on Python's standard library plus SQLite; there are no
third-party runtime dependencies.  The public surface is small::

    from recalldeck import Store, srs, stats
    store = Store("cards.db")
    deck = store.add_deck("Spanish")
    store.add_card(deck.id, "hola", "hello", tags="greeting")

The SM-2 scheduler in :mod:`recalldeck.srs` is pure and deterministic (inject
``now``); the CLI lives in :mod:`recalldeck.__main__` and the tkinter GUI in
:mod:`recalldeck.gui`.  Every recoverable failure raises
:class:`RecallDeckError`.

100% AI-built, open source, published on QuickOpen (quickopen.ai).
"""

from __future__ import annotations

from .errors import RecallDeckError
from .db import Store, Deck, Card, default_db_path
from . import srs, stats, importer

__version__ = "1.0.0"

__all__ = [
    "RecallDeckError",
    "Store",
    "Deck",
    "Card",
    "default_db_path",
    "srs",
    "stats",
    "importer",
]
