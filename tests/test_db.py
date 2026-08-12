"""Deck and card CRUD against a temp-file SQLite store."""

from datetime import date

import pytest

from recalldeck import RecallDeckError
from recalldeck.db import Store


def test_deck_crud(store):
    d = store.add_deck("Spanish")
    assert d.id > 0 and d.name == "Spanish"
    assert [x.name for x in store.list_decks()] == ["Spanish"]

    store.add_deck("French")
    assert {x.name for x in store.list_decks()} == {"Spanish", "French"}

    store.rename_deck("French", "Français")
    assert store.get_deck("Français").id
    with pytest.raises(RecallDeckError):
        store.get_deck("French")

    store.remove_deck("Spanish")
    assert [x.name for x in store.list_decks()] == ["Français"]


def test_duplicate_deck_rejected(store):
    store.add_deck("Dup")
    with pytest.raises(RecallDeckError):
        store.add_deck("Dup")


def test_empty_deck_name_rejected(store):
    with pytest.raises(RecallDeckError):
        store.add_deck("   ")


def test_card_crud(store):
    store.add_deck("Deck")
    c = store.add_card("Deck", "front", "back", tags="a,b")
    assert c.id > 0 and c.front == "front" and c.tags == "a,b"
    assert c.ease == 2.5 and c.reps == 0 and c.interval_days == 0

    store.update_card(c.id, front="F2", tags="x")
    got = store.get_card(c.id)
    assert got.front == "F2" and got.back == "back" and got.tags == "x"

    assert len(store.list_cards("Deck")) == 1
    store.remove_card(c.id)
    assert store.list_cards("Deck") == []


def test_card_requires_front_and_back(store):
    store.add_deck("Deck")
    with pytest.raises(RecallDeckError):
        store.add_card("Deck", "front", "")


def test_removing_deck_cascades_cards(store):
    store.add_deck("Deck")
    c = store.add_card("Deck", "f", "b")
    store.remove_deck("Deck")
    with pytest.raises(RecallDeckError):
        store.get_card(c.id)


def test_add_card_to_missing_deck(store):
    with pytest.raises(RecallDeckError):
        store.add_card("Nope", "f", "b")


def test_db_path_override(tmp_path):
    path = tmp_path / "custom.db"
    s = Store(str(path))
    s.add_deck("X")
    s.close()
    assert path.exists()
    # reopen and see the persisted deck
    s2 = Store(str(path))
    assert [d.name for d in s2.list_decks()] == ["X"]
    s2.close()
