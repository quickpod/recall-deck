"""Per-deck study statistics.

All numbers are derived from the card scheduling fields plus the review log, so
the same injected *now* the SRS uses produces stable, testable counts.  A card
is "new" until it has been answered once; "young" while its interval is under
:data:`MATURE_DAYS`; "mature" once it reaches it.  Retention is the share of
logged reviews that were a pass (quality >= 3).
"""

from __future__ import annotations

from .errors import RecallDeckError
from . import srs

MATURE_DAYS = 21  # interval at which a card is considered "mature" (Anki-style)
PASS_QUALITY = 3


def deck_stats(store, deck_ref, now):
    """Return a dict of counts describing *deck* at *now*.

    Keys: ``deck``, ``total``, ``due``, ``new``, ``young``, ``mature``,
    ``reviews``, ``lapses``, ``retention`` (percent, 0..100, ``None`` if no
    reviews yet).
    """
    deck = store.get_deck(deck_ref)
    cards = store.list_cards(deck.id)
    history = store.review_history(deck.id)

    total = len(cards)
    due = new = young = mature = lapses = 0
    for c in cards:
        if srs.is_due(c, now):
            due += 1
        if (c.reps or 0) == 0:
            new += 1
        elif (c.interval_days or 0) >= MATURE_DAYS:
            mature += 1
        else:
            young += 1
        lapses += c.lapses or 0

    reviews = len(history)
    passes = sum(1 for h in history if int(h.get("quality", 0)) >= PASS_QUALITY)
    retention = round(100.0 * passes / reviews, 1) if reviews else None

    return {
        "deck": deck.name,
        "total": total,
        "due": due,
        "new": new,
        "young": young,
        "mature": mature,
        "reviews": reviews,
        "lapses": lapses,
        "retention": retention,
    }


def format_stats(s):
    """Render :func:`deck_stats` output as a short plain-text block."""
    retention = "n/a" if s["retention"] is None else f"{s['retention']:.1f}%"
    return "\n".join([
        f"Deck: {s['deck']}",
        f"  Total cards : {s['total']}",
        f"  Due now     : {s['due']}",
        f"  New         : {s['new']}",
        f"  Young       : {s['young']}",
        f"  Mature      : {s['mature']}",
        f"  Reviews     : {s['reviews']}",
        f"  Lapses      : {s['lapses']}",
        f"  Retention   : {retention}",
    ])
