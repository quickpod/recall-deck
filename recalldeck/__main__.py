"""Command-line interface: ``python -m recalldeck <command> ...``.

Commands mirror the GUI: manage decks and cards, review what's due (interactive
or, for scripting/tests, with ``--grade``), inspect what's due, print stats and
import/export decks.  Every command exits cleanly (code 1, a one-line message)
when a :class:`RecallDeckError` is raised -- never a traceback.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from .errors import RecallDeckError
from .db import Store
from . import importer, stats as stats_mod
from . import srs

# Map the GUI grade buttons to SM-2 qualities (documented for --help readers).
GRADE_LABELS = {2: "Again", 3: "Hard", 4: "Good", 5: "Easy"}


def _today(args):
    """Resolve the effective 'now' (``--now YYYY-MM-DD`` or today)."""
    if getattr(args, "now", None):
        try:
            return date.fromisoformat(args.now)
        except ValueError as exc:
            raise RecallDeckError(f"Invalid --now date: {args.now!r}") from exc
    return date.today()


# --- command handlers -------------------------------------------------------
def cmd_deck_add(store, args):
    deck = store.add_deck(args.name)
    print(f"Added deck {deck.name!r} (id {deck.id})")


def cmd_deck_list(store, args):
    decks = store.list_decks()
    if not decks:
        print("No decks yet. Add one with: recalldeck deck add <name>")
        return
    now = _today(args)
    for d in decks:
        due = len(store.due_cards(d.id, now))
        total = len(store.list_cards(d.id))
        print(f"{d.id:>3}  {d.name}  ({total} cards, {due} due)")


def cmd_deck_remove(store, args):
    deck = store.remove_deck(args.name)
    print(f"Removed deck {deck.name!r}")


def cmd_card_add(store, args):
    card = store.add_card(args.deck, args.front, args.back, tags=args.tags or "",
                          now=_today(args))
    print(f"Added card {card.id} to {args.deck!r}")


def cmd_card_list(store, args):
    cards = store.list_cards(args.deck)
    if not cards:
        print("(no cards)")
        return
    for c in cards:
        tags = f"  [{c.tags}]" if c.tags else ""
        print(f"{c.id:>4}  {c.front}  ->  {c.back}{tags}")


def cmd_due(store, args):
    now = _today(args)
    cards = store.due_cards(args.deck, now)
    if not cards:
        print("Nothing due. ")
        return
    print(f"{len(cards)} card(s) due in {args.deck!r}:")
    for c in cards:
        print(f"{c.id:>4}  {c.front}")


def cmd_review(store, args):
    now = _today(args)
    queue = store.due_cards(args.deck, now)
    if not queue:
        print("Nothing due. ")
        return

    if args.grade is not None:
        # Non-interactive: grade the next due card, or the whole queue with --all.
        targets = queue if args.all else queue[:1]
        for c in targets:
            updated = store.apply_review(c.id, args.grade, now)
            print(f"Reviewed card {updated.id} (grade {args.grade}): "
                  f"interval {updated.interval_days}d, due {updated.due_date}, "
                  f"ease {updated.ease}")
        return

    # Interactive: walk the due queue, revealing the back and reading a grade.
    reviewed = 0
    for c in queue:
        print("\n" + "-" * 40)
        print(f"Q: {c.front}")
        try:
            input("   [press Enter to reveal answer] ")
            print(f"A: {c.back}")
            raw = input("   grade 0-5 (or 's' to skip, 'q' to quit): ").strip()
        except EOFError:
            break
        if raw.lower() in ("q", "quit"):
            break
        if raw.lower() in ("s", "skip", ""):
            continue
        try:
            grade = int(raw)
        except ValueError:
            print("   not a number 0-5; skipping.")
            continue
        updated = store.apply_review(c.id, grade, now)
        reviewed += 1
        print(f"   -> next due {updated.due_date} (interval {updated.interval_days}d)")
    print(f"\nDone. Reviewed {reviewed} card(s).")


def cmd_stats(store, args):
    s = stats_mod.deck_stats(store, args.deck, _today(args))
    print(stats_mod.format_stats(s))


def cmd_import(store, args):
    n = importer.import_file(store, args.deck, args.file, now=_today(args))
    print(f"Imported {n} card(s) into {args.deck!r} from {args.file}")


def cmd_export(store, args):
    n = importer.export_file(store, args.deck, args.file)
    print(f"Exported {n} card(s) from {args.deck!r} to {args.file}")


# --- parser -----------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="recalldeck",
        description="RecallDeck -- offline SM-2 spaced-repetition flashcards.",
    )
    p.add_argument("--db", metavar="PATH", default=None,
                   help="database file (default: per-user app data)")
    p.add_argument("--now", metavar="YYYY-MM-DD", default=None,
                   help="treat this date as 'today' (for scripting/tests)")
    sub = p.add_subparsers(dest="command", required=True)

    # deck ...
    deck = sub.add_parser("deck", help="manage decks").add_subparsers(
        dest="deck_cmd", required=True)
    d_add = deck.add_parser("add", help="create a deck")
    d_add.add_argument("name")
    d_add.set_defaults(func=cmd_deck_add)
    d_list = deck.add_parser("list", help="list decks")
    d_list.set_defaults(func=cmd_deck_list)
    d_rm = deck.add_parser("remove", help="delete a deck and its cards")
    d_rm.add_argument("name")
    d_rm.set_defaults(func=cmd_deck_remove)

    # card ...
    card = sub.add_parser("card", help="manage cards").add_subparsers(
        dest="card_cmd", required=True)
    c_add = card.add_parser("add", help="add a card to a deck")
    c_add.add_argument("deck")
    c_add.add_argument("front")
    c_add.add_argument("back")
    c_add.add_argument("--tags", default="")
    c_add.set_defaults(func=cmd_card_add)
    c_list = card.add_parser("list", help="list a deck's cards")
    c_list.add_argument("deck")
    c_list.set_defaults(func=cmd_card_list)

    # top-level verbs
    due = sub.add_parser("due", help="show cards due for review")
    due.add_argument("deck")
    due.set_defaults(func=cmd_due)

    rev = sub.add_parser("review", help="review due cards (interactive or --grade)")
    rev.add_argument("deck")
    rev.add_argument("--grade", type=int, default=None,
                     help="grade 0-5 non-interactively (2=Again 3=Hard 4=Good 5=Easy)")
    rev.add_argument("--all", action="store_true",
                     help="with --grade, apply it to every due card")
    rev.set_defaults(func=cmd_review)

    st = sub.add_parser("stats", help="show per-deck statistics")
    st.add_argument("deck")
    st.set_defaults(func=cmd_stats)

    imp = sub.add_parser("import", help="import cards from CSV/JSON")
    imp.add_argument("deck")
    imp.add_argument("file")
    imp.set_defaults(func=cmd_import)

    exp = sub.add_parser("export", help="export cards to CSV/JSON")
    exp.add_argument("deck")
    exp.add_argument("file")
    exp.set_defaults(func=cmd_export)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    store = None
    try:
        store = Store(args.db)
        args.func(store, args)
    except RecallDeckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
