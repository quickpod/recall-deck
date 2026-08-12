"""Import and export decks as CSV or JSON.

CSV is three columns -- ``front,back,tags`` -- with an optional header row that
is auto-detected and skipped.  JSON is either a bare list of card objects or a
``{"deck": name, "cards": [...]}`` wrapper; export always writes the wrapper so
a round-trip preserves the deck name.  Malformed rows (missing front/back) are
skipped rather than aborting the whole import; unreadable files raise
:class:`RecallDeckError`.
"""

from __future__ import annotations

import csv
import io
import json
import os

from .errors import RecallDeckError

CSV_HEADER = ["front", "back", "tags"]


def _card_dicts(store, deck_ref):
    return [
        {"front": c.front, "back": c.back, "tags": c.tags}
        for c in store.list_cards(deck_ref)
    ]


# -- export ------------------------------------------------------------------
def export_csv(store, deck_ref, path):
    """Write the deck's cards to *path* as ``front,back,tags`` CSV (with header)."""
    cards = _card_dicts(store, deck_ref)
    try:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(CSV_HEADER)
            for c in cards:
                writer.writerow([c["front"], c["back"], c["tags"]])
    except OSError as exc:
        raise RecallDeckError(f"Cannot write {path}: {exc}") from exc
    return len(cards)


def export_json(store, deck_ref, path):
    """Write the deck to *path* as ``{"deck": name, "cards": [...]}`` JSON."""
    deck = store.get_deck(deck_ref)
    payload = {"deck": deck.name, "cards": _card_dicts(store, deck.id)}
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        raise RecallDeckError(f"Cannot write {path}: {exc}") from exc
    return len(payload["cards"])


# -- import ------------------------------------------------------------------
def _add_rows(store, deck_ref, rows, now=None):
    """Insert ``(front, back, tags)`` tuples, skipping malformed ones."""
    added = 0
    for front, back, tags in rows:
        front = (front or "").strip()
        back = (back or "").strip()
        if not front or not back:
            continue  # guard malformed / blank rows
        store.add_card(deck_ref, front, back, tags=(tags or "").strip(), now=now)
        added += 1
    return added


def _looks_like_header(row):
    return [str(c).strip().lower() for c in row[:2]] == ["front", "back"]


def import_csv(store, deck_ref, path, now=None):
    """Import ``front,back,tags`` CSV rows into *deck*.  Returns the count added."""
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        raise RecallDeckError(f"Cannot read {path}: {exc}") from exc
    try:
        reader = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise RecallDeckError(f"Malformed CSV in {path}: {exc}") from exc

    rows = []
    for i, row in enumerate(reader):
        if not row or all(not str(c).strip() for c in row):
            continue
        if i == 0 and _looks_like_header(row):
            continue
        front = row[0] if len(row) > 0 else ""
        back = row[1] if len(row) > 1 else ""
        tags = row[2] if len(row) > 2 else ""
        rows.append((front, back, tags))
    return _add_rows(store, deck_ref, rows, now=now)


def import_json(store, deck_ref, path, now=None):
    """Import cards from a JSON list or ``{"cards": [...]}`` file into *deck*."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise RecallDeckError(f"Cannot read {path}: {exc}") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise RecallDeckError(f"Malformed JSON in {path}: {exc}") from exc

    if isinstance(data, dict):
        cards = data.get("cards", [])
    elif isinstance(data, list):
        cards = data
    else:
        raise RecallDeckError("JSON must be a list of cards or a deck object.")

    rows = []
    for item in cards:
        if not isinstance(item, dict):
            continue  # guard malformed entries
        rows.append((item.get("front", ""), item.get("back", ""), item.get("tags", "")))
    return _add_rows(store, deck_ref, rows, now=now)


def import_file(store, deck_ref, path, now=None):
    """Dispatch to CSV/JSON import based on the file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return import_json(store, deck_ref, path, now=now)
    if ext == ".csv":
        return import_csv(store, deck_ref, path, now=now)
    raise RecallDeckError(f"Unsupported import format: {ext or '(none)'} (use .csv or .json)")


def export_file(store, deck_ref, path):
    """Dispatch to CSV/JSON export based on the file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return export_json(store, deck_ref, path)
    if ext == ".csv":
        return export_csv(store, deck_ref, path)
    raise RecallDeckError(f"Unsupported export format: {ext or '(none)'} (use .csv or .json)")
