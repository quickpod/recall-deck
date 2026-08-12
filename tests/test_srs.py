"""SM-2 scheduling math (pure, deterministic with an injected 'now')."""

from datetime import date, timedelta

import pytest

from recalldeck import srs, RecallDeckError
from recalldeck.db import Card


NOW = date(2026, 1, 1)


def _card(ease=2.5, interval_days=0, reps=0, lapses=0):
    return Card(id=1, deck_id=1, front="f", back="b", ease=ease,
                interval_days=interval_days, reps=reps, lapses=lapses)


def test_first_second_third_intervals_follow_sm2():
    c = _card()
    r1 = srs.review(c, 5, NOW)
    assert r1["reps"] == 1 and r1["interval_days"] == 1

    c2 = _card(ease=r1["ease"], interval_days=r1["interval_days"], reps=r1["reps"])
    r2 = srs.review(c2, 5, NOW)
    assert r2["reps"] == 2 and r2["interval_days"] == 6

    c3 = _card(ease=r2["ease"], interval_days=r2["interval_days"], reps=r2["reps"])
    r3 = srs.review(c3, 5, NOW)
    # third interval is ease-scaled: round(6 * ease_at_review)
    assert r3["reps"] == 3
    assert r3["interval_days"] == round(6 * r2["ease"])


def test_correct_answer_increases_interval_and_ease():
    # a card already past its second rep
    c = _card(ease=2.6, interval_days=6, reps=2)
    r = srs.review(c, 5, NOW)
    assert r["interval_days"] > 6       # interval grows
    assert r["ease"] > 2.6              # ease grows on a quality-5 answer
    assert r["due_date"] == NOW + timedelta(days=r["interval_days"])


def test_lapse_resets_interval_and_counts_lapse():
    c = _card(ease=2.6, interval_days=40, reps=5, lapses=1)
    r = srs.review(c, 1, NOW)
    assert r["interval_days"] == 1      # interval reset
    assert r["reps"] == 0               # streak reset
    assert r["lapses"] == 2             # lapse counted
    assert r["due_date"] == NOW + timedelta(days=1)


def test_ease_never_drops_below_minimum():
    c = _card(ease=1.3, interval_days=10, reps=3)
    r = srs.review(c, 0, NOW)
    assert r["ease"] >= srs.MIN_EASE


def test_invalid_grade_raises():
    with pytest.raises(RecallDeckError):
        srs.review(_card(), 6, NOW)
    with pytest.raises(RecallDeckError):
        srs.review(_card(), -1, NOW)


def test_due_cards_filters_by_due_date():
    past = Card(id=1, deck_id=1, front="a", back="b", due_date="2025-12-30")
    today = Card(id=2, deck_id=1, front="c", back="d", due_date="2026-01-01")
    future = Card(id=3, deck_id=1, front="e", back="f", due_date="2026-02-01")
    due = srs.due_cards([past, today, future], NOW)
    assert [c.id for c in due] == [1, 2]  # only due_date <= now


def test_review_does_not_mutate_input():
    c = _card(ease=2.5, interval_days=6, reps=2)
    srs.review(c, 5, NOW)
    assert c.ease == 2.5 and c.interval_days == 6 and c.reps == 2
