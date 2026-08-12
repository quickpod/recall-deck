"""CLI end-to-end on a temp db, plus the headless GUI guarantees."""

import os

from recalldeck import __main__ as cli


def run(capsys, *args):
    code = cli.main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_cli_full_flow(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    now = "2026-01-01"

    code, out, _ = run(capsys, "--db", db, "deck", "add", "Spanish")
    assert code == 0 and "Spanish" in out

    code, _, _ = run(capsys, "--db", db, "--now", now, "card", "add", "Spanish",
                     "hola", "hello", "--tags", "greeting")
    assert code == 0

    code, out, _ = run(capsys, "--db", db, "--now", now, "due", "Spanish")
    assert code == 0 and "hola" in out

    code, out, _ = run(capsys, "--db", db, "--now", now, "review", "Spanish",
                       "--grade", "5")
    assert code == 0 and "interval 1d" in out

    code, out, _ = run(capsys, "--db", db, "--now", now, "stats", "Spanish")
    assert code == 0 and "Total cards : 1" in out


def test_cli_error_exits_cleanly(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    code, _, err = run(capsys, "--db", db, "deck", "remove", "Nope")
    assert code == 1 and err.startswith("error:")


def test_cli_import_export_round_trip(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    csvp = str(tmp_path / "d.csv")
    run(capsys, "--db", db, "deck", "add", "A")
    run(capsys, "--db", db, "--now", "2026-01-01", "card", "add", "A", "f", "b")
    code, _, _ = run(capsys, "--db", db, "export", "A", csvp)
    assert code == 0 and os.path.exists(csvp)

    run(capsys, "--db", db, "deck", "add", "B")
    code, out, _ = run(capsys, "--db", db, "import", "B", csvp)
    assert code == 0 and "Imported 1" in out


def test_gui_imports_clean_and_headless_main_returns_zero(monkeypatch):
    # Importing the module must have no side effects and need no display.
    from recalldeck import gui
    assert hasattr(gui, "main")
    # With no DISPLAY, main() must degrade gracefully and return 0.
    monkeypatch.delenv("DISPLAY", raising=False)
    assert gui.main() == 0
