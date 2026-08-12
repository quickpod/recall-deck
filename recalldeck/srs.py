"""The SM-2 spaced-repetition algorithm.

Pure and deterministic: :func:`review` takes a card's current scheduling state
plus the answer *quality* (0..5) and an injected *now*, and returns the updated
state.  Nothing here reads the clock or touches a database -- callers pass the
time in and persist the result, which keeps the maths fully unit-testable.

Reference: SuperMemo 2 (Wozniak).  Interval for a repetition is computed with
the *current* ease factor, then the ease factor itself is updated afterwards.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .errors import RecallDeckError

DEFAULT_EASE = 2.5
MIN_EASE = 1.3

# Answer qualities used by the GUI grade buttons (SM-2 0..5 scale).
AGAIN, HARD, GOOD, EASY = 2, 3, 4, 5


def _as_date(value):
    """Coerce *value* (``date``/``datetime``/ISO string) to a ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise RecallDeckError(f"Invalid date: {value!r}") from exc
    raise RecallDeckError(f"Unsupported date value: {value!r}")


def _get(card, name, default):
    """Read *name* from a Card dataclass or a plain mapping."""
    if isinstance(card, dict):
        value = card.get(name, default)
    else:
        value = getattr(card, name, default)
    return default if value is None else value


def review(card, quality, now):
    """Return the updated scheduling state after answering *card*.

    *card* is any object (or dict) exposing ``ease``, ``interval_days``,
    ``reps`` and ``lapses``.  *quality* is an integer 0..5 (>=3 is a pass).
    *now* is the review moment (``date``/``datetime``/ISO string).

    The returned dict has ``ease``, ``interval_days``, ``reps``, ``lapses`` and
    ``due_date`` (a ``date``).  The input *card* is never mutated.
    """
    try:
        q = int(quality)
    except (TypeError, ValueError) as exc:
        raise RecallDeckError(f"Grade must be an integer 0-5, got {quality!r}") from exc
    if not 0 <= q <= 5:
        raise RecallDeckError(f"Grade must be between 0 and 5, got {q}")

    ease = float(_get(card, "ease", DEFAULT_EASE) or DEFAULT_EASE)
    interval = int(_get(card, "interval_days", 0) or 0)
    reps = int(_get(card, "reps", 0) or 0)
    lapses = int(_get(card, "lapses", 0) or 0)
    now_d = _as_date(now)

    if q < 3:
        # A lapse: reset the repetition streak and interval, count the miss.
        reps = 0
        lapses += 1
        interval = 1
    else:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            interval = int(round(interval * ease))
        if interval < 1:
            interval = 1

    # Update the ease factor (uses the raw quality, after scheduling above).
    ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if ease < MIN_EASE:
        ease = MIN_EASE

    return {
        "ease": round(ease, 4),
        "interval_days": interval,
        "reps": reps,
        "lapses": lapses,
        "due_date": now_d + timedelta(days=interval),
    }


def is_due(card, now):
    """True if *card* is due for review at *now* (``due_date <= now``)."""
    due = _get(card, "due_date", None)
    if due is None:
        return True  # never scheduled -> treat as a new, due card
    return _as_date(due) <= _as_date(now)


def due_cards(cards, now):
    """Return the subset of *cards* whose ``due_date`` is on or before *now*."""
    return [c for c in cards if is_due(c, now)]
