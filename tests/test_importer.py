"""CSV and JSON import/export round-trips (and malformed-row guarding)."""

from datetime import date

from recalldeck import importer


NOW = date(2026, 1, 1)


def _fronts(store, deck):
    return [(c.front, c.back, c.tags) for c in store.list_cards(deck)]


def test_csv_round_trip(store, tmp_path):
    store.add_deck("Src")
    store.add_card("Src", "hola", "hello", tags="greeting", now=NOW)
    store.add_card("Src", "adios", "bye", tags="greeting", now=NOW)

    path = tmp_path / "deck.csv"
    assert importer.export_csv(store, "Src", str(path)) == 2

    store.add_deck("Dst")
    assert importer.import_csv(store, "Dst", str(path), now=NOW) == 2
    assert _fronts(store, "Dst") == _fronts(store, "Src")


def test_json_round_trip(store, tmp_path):
    store.add_deck("Src")
    store.add_card("Src", "uno", "one", tags="num", now=NOW)
    store.add_card("Src", "dos", "two", tags="num", now=NOW)

    path = tmp_path / "deck.json"
    assert importer.export_json(store, "Src", str(path)) == 2

    store.add_deck("Dst")
    assert importer.import_json(store, "Dst", str(path), now=NOW) == 2
    assert _fronts(store, "Dst") == _fronts(store, "Src")


def test_import_file_dispatch_by_extension(store, tmp_path):
    store.add_deck("Src")
    store.add_card("Src", "a", "b", now=NOW)
    csvp = tmp_path / "d.csv"
    jsonp = tmp_path / "d.json"
    importer.export_file(store, "Src", str(csvp))
    importer.export_file(store, "Src", str(jsonp))

    store.add_deck("D1")
    store.add_deck("D2")
    assert importer.import_file(store, "D1", str(csvp), now=NOW) == 1
    assert importer.import_file(store, "D2", str(jsonp), now=NOW) == 1


def test_csv_skips_malformed_rows(store, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("front,back,tags\n"
                    "good,answer,tag\n"
                    "onlyfront\n"      # missing back -> skipped
                    ",,\n"             # blank -> skipped
                    "second,ok,\n",
                    encoding="utf-8")
    store.add_deck("D")
    assert importer.import_csv(store, "D", str(path), now=NOW) == 2
    assert [c.front for c in store.list_cards("D")] == ["good", "second"]


def test_json_list_form_and_malformed_entries(store, tmp_path):
    path = tmp_path / "list.json"
    path.write_text(
        '[{"front": "x", "back": "y", "tags": "t"}, '
        '{"front": "", "back": "nope"}, '
        '"garbage"]',
        encoding="utf-8")
    store.add_deck("D")
    assert importer.import_json(store, "D", str(path), now=NOW) == 1
    assert [c.front for c in store.list_cards("D")] == ["x"]
