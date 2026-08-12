# RecallDeck

A fast, **offline**, **100% open-source** spaced-repetition flashcards for Windows. Nothing is uploaded anywhere. Built entirely by AI with human testing and guidance, and published on [QuickOpen](https://quickopen.ai/projects/recall-deck).

> **100% AI-built and open source.** Apache-2.0.

## What it does

Learn efficiently with an Anki-style spaced-repetition system (SM-2 scheduling). Create decks and cards (with images), review what's due, track retention and streak statistics, and import/export decks as CSV/JSON. Fully offline; your study data stays local.

## Install

Download **`RecallDeck-Setup.exe`** from the [QuickOpen page](https://quickopen.ai/projects/recall-deck) or the [GitHub release](https://github.com/quickpod/recall-deck/releases/latest) and double-click it. It installs per-user, adds Desktop and Start Menu shortcuts, and can optionally trust the QuickOpen Root CA. Authenticode-signed by the QuickOpen Code Signing CA — verify at [quickopen.ai/trust](https://quickopen.ai/trust).

## Run from source

```sh
python recall_deck_app.py          # GUI
python -m recalldeck --help    # CLI
```


## Features

- **SM-2 spaced repetition** — the proven SuperMemo-2 scheduler decides when each card comes back. Correct answers stretch the interval and ease; lapses reset the interval and are tracked.
- **Decks & cards** — organise cards into named decks, each card with a front, back, comma-separated tags and an optional media path.
- **Study sessions** — the GUI walks the due queue one card at a time: read the front, *Show Answer*, then grade **Again / Hard / Good / Easy**.
- **Statistics** — per-deck counts of total, due, new, young and mature cards, lapses, and retention (share of passing reviews).
- **Import / Export** — round-trip decks as CSV (`front,back,tags`) or JSON; malformed rows are skipped rather than aborting.
- **Dark mode** — a QuickOpen-palette light/dark theme, remembered between runs.
- **Fully offline, zero dependencies** — pure Python standard library plus SQLite. Your study data stays in a local database under your per-user app-data folder.

## CLI examples

```sh
# decks
python -m recalldeck deck add Spanish
python -m recalldeck deck list
python -m recalldeck deck remove Spanish

# cards
python -m recalldeck card add Spanish "hola" "hello" --tags greeting
python -m recalldeck card list Spanish

# study
python -m recalldeck due Spanish              # what's due now
python -m recalldeck review Spanish           # interactive review
python -m recalldeck review Spanish --grade 5 # grade next due card (scripting/tests)
python -m recalldeck stats Spanish            # deck statistics

# import / export (format chosen by file extension)
python -m recalldeck export Spanish deck.csv
python -m recalldeck import Spanish deck.json

# options: --db PATH picks a database file; --now YYYY-MM-DD fixes "today"
python -m recalldeck --db mydeck.db --now 2026-01-01 due Spanish
```

## License

Apache-2.0 — see [LICENSE](LICENSE). A 100% AI-built project published on QuickOpen.
