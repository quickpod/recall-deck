"""Per-deck stats: due/new counts and retention."""

from datetime import date

from recalldeck import stats


NOW = date(2026, 6, 1)


def test_new_and_due_counts(store):
    store.add_deck("D")
    # two brand-new cards, due today
    store.add_card("D", "a", "1", now=NOW)
    store.add_card("D", "b", "2", now=NOW)
    # one card scheduled into the future (not due, not new after a review)
    c = store.add_card("D", "c", "3", now=NOW)
    store.apply_review(c.id, 5, NOW)  # pushes due_date to NOW + 1 day, reps=1

    s = stats.deck_stats(store, "D", NOW)
    assert s["total"] == 3
    assert s["new"] == 2          # only the two un-reviewed cards
    assert s["due"] == 2          # the reviewed card is now scheduled ahead
    assert s["reviews"] == 1


def test_retention_percentage(store):
    store.add_deck("D")
    c = store.add_card("D", "a", "1", now=NOW)
    store.apply_review(c.id, 5, NOW)   # pass
    store.apply_review(c.id, 4, NOW)   # pass
    store.apply_review(c.id, 1, NOW)   # fail (lapse)

    s = stats.deck_stats(store, "D", NOW)
    assert s["reviews"] == 3
    assert s["lapses"] == 1
    assert s["retention"] == round(100 * 2 / 3, 1)


def test_retention_none_without_reviews(store):
    store.add_deck("D")
    store.add_card("D", "a", "1", now=NOW)
    s = stats.deck_stats(store, "D", NOW)
    assert s["retention"] is None
