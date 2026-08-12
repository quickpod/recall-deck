"""SQLite-backed store for decks and cards.

The database lives at ``%LOCALAPPDATA%\\RecallDeck\\recalldeck.db`` on Windows
(``~/.recalldeck/recalldeck.db`` elsewhere).  The path is overridable with the
``RECALLDECK_DB`` environment variable or an explicit ``path=`` argument -- the
tests point it at a throwaway file in a temp dir.

A :class:`Store` owns one connection and exposes CRUD for decks and cards plus
the review-scheduling helpers used by the SRS.  Every failure is normalised to
:class:`RecallDeckError` so callers never have to know about ``sqlite3``.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

from .errors import RecallDeckError
from . import srs

APP_DIRNAME = "RecallDeck"
DB_NAME = "recalldeck.db"


def default_db_path():
    r"""Default database location (``%LOCALAPPDATA%\RecallDeck\recalldeck.db``)."""
    env = os.environ.get("RECALLDECK_DB")
    if env:
        return env
    local = os.environ.get("LOCALAPPDATA")
    if local and os.name == "nt":
        base = os.path.join(local, APP_DIRNAME)
    else:
        base = os.path.join(os.path.expanduser("~"), "." + APP_DIRNAME.lower())
    return os.path.join(base, DB_NAME)


@dataclass
class Deck:
    id: int
    name: str
    created_at: str = ""


@dataclass
class Card:
    id: int
    deck_id: int
    front: str
    back: str
    tags: str = ""
    media: str = ""
    ease: float = srs.DEFAULT_EASE
    interval_days: int = 0
    due_date: str = ""
    reps: int = 0
    lapses: int = 0
    created_at: str = ""


SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id       INTEGER NOT NULL,
    front         TEXT NOT NULL,
    back          TEXT NOT NULL,
    tags          TEXT NOT NULL DEFAULT '',
    media         TEXT NOT NULL DEFAULT '',
    ease          REAL NOT NULL DEFAULT 2.5,
    interval_days INTEGER NOT NULL DEFAULT 0,
    due_date      TEXT NOT NULL DEFAULT '',
    reps          INTEGER NOT NULL DEFAULT 0,
    lapses        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (deck_id) REFERENCES decks (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS reviews (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id       INTEGER NOT NULL,
    reviewed_on   TEXT NOT NULL,
    quality       INTEGER NOT NULL,
    interval_days INTEGER NOT NULL,
    FOREIGN KEY (card_id) REFERENCES cards (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cards_deck ON cards (deck_id);
CREATE INDEX IF NOT EXISTS idx_cards_due ON cards (due_date);
CREATE INDEX IF NOT EXISTS idx_reviews_card ON reviews (card_id);
"""


def _iso(value):
    """Normalise a date-ish value to an ISO ``YYYY-MM-DD`` string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


class Store:
    """A connection to the RecallDeck database (create schema on open)."""

    def __init__(self, path=None):
        self.path = path or default_db_path()
        if self.path != ":memory:":
            parent = os.path.dirname(os.path.abspath(self.path))
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError as exc:
                raise RecallDeckError(f"Cannot create data folder: {exc}") from exc
        try:
            self.conn = sqlite3.connect(self.path)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.executescript(SCHEMA)
            self.conn.commit()
        except sqlite3.Error as exc:
            raise RecallDeckError(f"Cannot open database: {exc}") from exc

    # -- lifecycle --------------------------------------------------------
    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    # -- decks ------------------------------------------------------------
    def add_deck(self, name):
        name = (name or "").strip()
        if not name:
            raise RecallDeckError("Deck name cannot be empty.")
        try:
            cur = self.conn.execute(
                "INSERT INTO decks (name, created_at) VALUES (?, ?)",
                (name, _iso(date.today())),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            raise RecallDeckError(f"A deck named {name!r} already exists.") from exc
        return self.get_deck(cur.lastrowid)

    def list_decks(self):
        rows = self.conn.execute(
            "SELECT * FROM decks ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [Deck(r["id"], r["name"], r["created_at"]) for r in rows]

    def get_deck(self, ref):
        """Look a deck up by integer id or by name.  Raises if not found."""
        row = None
        if isinstance(ref, int):
            row = self.conn.execute("SELECT * FROM decks WHERE id = ?", (ref,)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM decks WHERE name = ?", (str(ref),)
            ).fetchone()
        if row is None:
            raise RecallDeckError(f"No such deck: {ref!r}")
        return Deck(row["id"], row["name"], row["created_at"])

    def rename_deck(self, ref, new_name):
        deck = self.get_deck(ref)
        new_name = (new_name or "").strip()
        if not new_name:
            raise RecallDeckError("Deck name cannot be empty.")
        try:
            self.conn.execute(
                "UPDATE decks SET name = ? WHERE id = ?", (new_name, deck.id)
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            raise RecallDeckError(f"A deck named {new_name!r} already exists.") from exc
        return self.get_deck(deck.id)

    def remove_deck(self, ref):
        deck = self.get_deck(ref)
        # Explicit child delete keeps behaviour identical regardless of the
        # foreign-key pragma state on this connection.
        self.conn.execute("DELETE FROM cards WHERE deck_id = ?", (deck.id,))
        self.conn.execute("DELETE FROM decks WHERE id = ?", (deck.id,))
        self.conn.commit()
        return deck

    # -- cards ------------------------------------------------------------
    def _row_to_card(self, r):
        return Card(
            id=r["id"], deck_id=r["deck_id"], front=r["front"], back=r["back"],
            tags=r["tags"], media=r["media"], ease=r["ease"],
            interval_days=r["interval_days"], due_date=r["due_date"],
            reps=r["reps"], lapses=r["lapses"], created_at=r["created_at"],
        )

    def add_card(self, deck_ref, front, back, tags="", media="", now=None):
        deck = self.get_deck(deck_ref)
        front = (front or "").strip()
        back = (back or "").strip()
        if not front or not back:
            raise RecallDeckError("A card needs both a front and a back.")
        due = _iso(now if now is not None else date.today())
        cur = self.conn.execute(
            "INSERT INTO cards (deck_id, front, back, tags, media, ease, "
            "interval_days, due_date, reps, lapses, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (deck.id, front, back, tags or "", media or "", srs.DEFAULT_EASE,
             0, due, 0, 0, _iso(date.today())),
        )
        self.conn.commit()
        return self.get_card(cur.lastrowid)

    def get_card(self, card_id):
        row = self.conn.execute(
            "SELECT * FROM cards WHERE id = ?", (int(card_id),)
        ).fetchone()
        if row is None:
            raise RecallDeckError(f"No such card: {card_id!r}")
        return self._row_to_card(row)

    def list_cards(self, deck_ref):
        deck = self.get_deck(deck_ref)
        rows = self.conn.execute(
            "SELECT * FROM cards WHERE deck_id = ? ORDER BY id", (deck.id,)
        ).fetchall()
        return [self._row_to_card(r) for r in rows]

    def update_card(self, card_id, front=None, back=None, tags=None, media=None):
        card = self.get_card(card_id)
        front = card.front if front is None else (front or "").strip()
        back = card.back if back is None else (back or "").strip()
        if not front or not back:
            raise RecallDeckError("A card needs both a front and a back.")
        tags = card.tags if tags is None else tags
        media = card.media if media is None else media
        self.conn.execute(
            "UPDATE cards SET front = ?, back = ?, tags = ?, media = ? WHERE id = ?",
            (front, back, tags, media, card.id),
        )
        self.conn.commit()
        return self.get_card(card.id)

    def remove_card(self, card_id):
        card = self.get_card(card_id)
        self.conn.execute("DELETE FROM cards WHERE id = ?", (card.id,))
        self.conn.commit()
        return card

    # -- scheduling -------------------------------------------------------
    def apply_review(self, card_id, quality, now):
        """Grade a card via SM-2, persist the new schedule and log the review."""
        card = self.get_card(card_id)
        sched = srs.review(card, quality, now)
        self.conn.execute(
            "UPDATE cards SET ease = ?, interval_days = ?, due_date = ?, "
            "reps = ?, lapses = ? WHERE id = ?",
            (sched["ease"], sched["interval_days"], _iso(sched["due_date"]),
             sched["reps"], sched["lapses"], card.id),
        )
        self.conn.execute(
            "INSERT INTO reviews (card_id, reviewed_on, quality, interval_days) "
            "VALUES (?, ?, ?, ?)",
            (card.id, _iso(now), int(quality), sched["interval_days"]),
        )
        self.conn.commit()
        return self.get_card(card.id)

    def due_cards(self, deck_ref, now):
        """Cards in *deck* whose ``due_date`` is on or before *now* (ISO order)."""
        deck = self.get_deck(deck_ref)
        now_iso = _iso(now)
        rows = self.conn.execute(
            "SELECT * FROM cards WHERE deck_id = ? AND due_date <= ? "
            "ORDER BY due_date, id",
            (deck.id, now_iso),
        ).fetchall()
        return [self._row_to_card(r) for r in rows]

    def review_history(self, deck_ref):
        """All review log rows for a deck (list of dicts, oldest first)."""
        deck = self.get_deck(deck_ref)
        rows = self.conn.execute(
            "SELECT r.reviewed_on, r.quality, r.interval_days FROM reviews r "
            "JOIN cards c ON c.id = r.card_id WHERE c.deck_id = ? "
            "ORDER BY r.reviewed_on, r.id",
            (deck.id,),
        ).fetchall()
        return [dict(r) for r in rows]
