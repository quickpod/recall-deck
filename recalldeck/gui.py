#!/usr/bin/env python3
r"""RecallDeck -- a pure-stdlib tkinter GUI on top of the ``recalldeck`` engine.

A single main window: a left sidebar (Decks, Study, Browse/Edit, Stats,
Import/Export) and a main panel that swaps to the selected section.  Every
operation calls the tested core library (never re-implements SRS or storage);
failures are shown in a clear inline bar as the ``RecallDeckError`` message --
never a raw traceback.

Design goals baked in here (mirroring the QuickOpen house style):
  * pure standard-library tkinter/ttk -- NO third-party GUI deps.  Dark mode is
    a ttk-style + palette swap.
  * Importing this module does nothing.  Only :func:`main` builds a root window,
    and it degrades gracefully (prints a message, returns 0) with no display.
  * Frozen-exe safe: bundled assets are resolved via ``sys._MEIPASS`` / the exe
    directory when ``sys.frozen`` is set -- never ``__file__``.

100% AI-built, open source, published on QuickOpen (quickopen.ai).
"""

from __future__ import annotations

import os
import sys
from datetime import date

# NOTE: tkinter is imported lazily inside main()/build_app so that merely
# importing this module (e.g. during packaging or on a headless CI box) never
# fails and has no side effects.

APP_NAME = "RecallDeck"
APP_VERSION = "1.0.0"
WINDOW_TITLE = "RecallDeck — by QuickOpen (quickopen.ai)"
PROJECT_URL = "https://quickopen.ai"

# Study grade buttons -> SM-2 qualities.
GRADES = [("Again", 2), ("Hard", 3), ("Good", 4), ("Easy", 5)]

SECTIONS = [
    ("decks", "Decks"),
    ("study", "Study"),
    ("browse", "Browse / Edit"),
    ("stats", "Stats"),
    ("io", "Import / Export"),
]

# ---- colour palettes (mirror the QuickOpen palette) -------------------------
PALETTES = {
    "light": {
        "bg": "#f5f7fa", "surface": "#ffffff", "text": "#141820",
        "muted": "#5b6472", "primary": "#2f5fe0", "primary_hi": "#2450c8",
        "entry": "#ffffff", "border": "#d5dae2", "sel": "#2f5fe0",
        "sel_fg": "#ffffff", "trough": "#e2e7ef", "ok": "#1f7a3d",
        "err": "#c0392b",
    },
    "dark": {
        "bg": "#0f1115", "surface": "#1a1e24", "text": "#f1f3f7",
        "muted": "#9aa4b2", "primary": "#5b86f7", "primary_hi": "#7098ff",
        "entry": "#1a1e24", "border": "#2a2f38", "sel": "#5b86f7",
        "sel_fg": "#0f1115", "trough": "#2a2f38", "ok": "#5bd68a",
        "err": "#ff6b5e",
    },
}

SECTION_DESCRIPTIONS = {
    "decks": "Create, rename and delete decks. Select a deck to study or browse.",
    "study": "Review cards that are due. Reveal the answer, then grade how well "
             "you recalled it (Again / Hard / Good / Easy).",
    "browse": "See every card in a deck; add, edit or delete cards.",
    "stats": "Counts of due, new, young and mature cards, plus retention.",
    "io": "Import or export a deck as CSV (front,back,tags) or JSON.",
}


# ---------------------------------------------------------------------------
# Asset / frozen handling
# ---------------------------------------------------------------------------
def asset_path(name):
    """Locate a bundled asset from source OR a PyInstaller one-file build.

    For a frozen exe we look only at ``sys._MEIPASS`` and the executable's own
    directory (never ``__file__``).  From source we also consult the package
    dir, the repo root and the CWD.  Returns an absolute path or ``None``.
    """
    roots = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(meipass)
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        roots += [here, os.path.dirname(here), os.getcwd()]
    for root in roots:
        candidate = os.path.join(root, name)
        if os.path.exists(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# GUI construction (kept inside a function so import never needs a display)
# ---------------------------------------------------------------------------
def build_app():
    """Construct and return the App class bound to a live tkinter import."""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog

    from . import guiconfig
    from .errors import RecallDeckError
    from .db import Store
    from . import importer, srs, stats as stats_mod

    FONT = "Segoe UI"

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title(WINDOW_TITLE)
            self.geometry("1040x660")
            self.minsize(860, 540)

            self.theme = guiconfig.get_theme()
            self._tracked = []          # (tk_widget, role) for manual re-theming
            self._img_refs = []         # keep PhotoImage refs alive
            self._panels = {}           # section_id -> built frame (lazy)
            self._current = None

            # data / study state
            self.store = Store()
            self.current_deck = None    # Deck or None
            self._study_queue = []      # remaining due Cards
            self._study_card = None
            self._answer_shown = False

            self._set_icon()
            self._build_menu()
            self._build_layout()
            self._apply_theme()
            self.protocol("WM_DELETE_WINDOW", self._on_close)
            self.after(50, self._select_first_section)

        # ---- assets / icon
        def _set_icon(self):
            try:
                ico = asset_path("recall-deck.ico")
                if ico:
                    self.iconbitmap(ico)
                    return
            except Exception:
                pass
            try:
                png = asset_path("recall-deck.png")
                if png:
                    img = tk.PhotoImage(file=png)
                    self._img_refs.append(img)
                    self.iconphoto(True, img)
            except Exception:
                pass  # icon is cosmetic; never block launch

        # ---- theming
        def track(self, widget, role):
            self._tracked.append((widget, role))

        def _pal(self):
            return PALETTES[self.theme]

        def _apply_theme(self):
            p = self._pal()
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            self.configure(bg=p["bg"])
            style.configure(".", background=p["bg"], foreground=p["text"],
                            fieldbackground=p["entry"], bordercolor=p["border"],
                            font=(FONT, 10))
            style.configure("TFrame", background=p["bg"])
            style.configure("Sidebar.TFrame", background=p["surface"])
            style.configure("Card.TFrame", background=p["surface"])
            style.configure("TLabel", background=p["bg"], foreground=p["text"])
            style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"])
            style.configure("Header.TLabel", background=p["bg"], foreground=p["text"],
                            font=(FONT, 15, "bold"))
            style.configure("Sub.TLabel", background=p["bg"], foreground=p["muted"],
                            font=(FONT, 10))
            style.configure("Brand.TLabel", background=p["surface"],
                            foreground=p["text"], font=(FONT, 12, "bold"))
            style.configure("Status.TLabel", background=p["surface"],
                            foreground=p["muted"])
            style.configure("Face.TLabel", background=p["surface"],
                            foreground=p["text"], font=(FONT, 18))
            style.configure("Big.TLabel", background=p["bg"], foreground=p["text"],
                            font=(FONT, 22, "bold"))
            style.configure("TButton", background=p["surface"], foreground=p["text"],
                            bordercolor=p["border"], focuscolor=p["surface"],
                            padding=(10, 5))
            style.map("TButton",
                      background=[("active", p["trough"]), ("disabled", p["bg"])],
                      foreground=[("disabled", p["muted"])])
            style.configure("Accent.TButton", background=p["primary"],
                            foreground="#ffffff", padding=(12, 6))
            style.map("Accent.TButton",
                      background=[("active", p["primary_hi"]),
                                  ("disabled", p["border"])],
                      foreground=[("disabled", p["muted"])])
            style.configure("Toggle.TButton", background=p["surface"],
                            foreground=p["text"], padding=(8, 4))
            style.configure("TEntry", fieldbackground=p["entry"], foreground=p["text"],
                            insertcolor=p["text"], bordercolor=p["border"])
            style.configure("TCheckbutton", background=p["bg"], foreground=p["text"])
            style.map("TCheckbutton", background=[("active", p["bg"])])
            style.configure("TLabelframe", background=p["bg"], foreground=p["text"],
                            bordercolor=p["border"])
            style.configure("TLabelframe.Label", background=p["bg"],
                            foreground=p["muted"])
            style.configure("Treeview", background=p["surface"],
                            fieldbackground=p["surface"], foreground=p["text"],
                            bordercolor=p["border"], rowheight=24)
            style.map("Treeview", background=[("selected", p["primary"])],
                      foreground=[("selected", p["sel_fg"])])
            style.configure("Sidebar.Treeview", background=p["surface"],
                            fieldbackground=p["surface"])
            style.configure("Bar.Horizontal.TProgressbar", background=p["primary"],
                            troughcolor=p["trough"], bordercolor=p["border"])
            style.configure("TScrollbar", background=p["surface"],
                            troughcolor=p["bg"], bordercolor=p["border"],
                            arrowcolor=p["text"])
            style.configure("TSeparator", background=p["border"])

            for widget, role in list(self._tracked):
                try:
                    if role == "listbox":
                        widget.configure(bg=p["surface"], fg=p["text"],
                                         selectbackground=p["primary"],
                                         selectforeground=p["sel_fg"],
                                         highlightthickness=1,
                                         highlightbackground=p["border"],
                                         borderwidth=0)
                    elif role == "text":
                        widget.configure(bg=p["surface"], fg=p["text"],
                                         insertbackground=p["text"],
                                         highlightthickness=1,
                                         highlightbackground=p["border"],
                                         borderwidth=0)
                    elif role == "canvas":
                        widget.configure(bg=p["surface"], highlightthickness=1,
                                         highlightbackground=p["border"])
                except Exception:
                    pass

        def toggle_theme(self):
            self.theme = "dark" if self.theme == "light" else "light"
            guiconfig.set_theme(self.theme)
            self._apply_theme()
            self._theme_btn.configure(
                text="☀ Light mode" if self.theme == "dark" else "🌙 Dark mode")
            # redraw the stats bars (canvas colours are manual)
            if self._current_id == "stats":
                self._refresh_stats()

        # ---- menu
        def _build_menu(self):
            bar = tk.Menu(self)
            filem = tk.Menu(bar, tearoff=0)
            filem.add_command(label="Exit", command=self._on_close)
            bar.add_cascade(label="File", menu=filem)
            viewm = tk.Menu(bar, tearoff=0)
            viewm.add_command(label="Toggle dark mode", command=self.toggle_theme)
            bar.add_cascade(label="View", menu=viewm)
            helpm = tk.Menu(bar, tearoff=0)
            helpm.add_command(
                label="About",
                command=lambda: messagebox.showinfo(
                    "About " + APP_NAME,
                    f"{APP_NAME} {APP_VERSION}\n"
                    "Offline SM-2 spaced-repetition flashcards.\n"
                    "100% AI-built, open source — quickopen.ai"))
            bar.add_cascade(label="Help", menu=helpm)
            self.config(menu=bar)

        # ---- layout
        def _build_layout(self):
            top = ttk.Frame(self, style="Sidebar.TFrame", padding=(12, 8))
            top.pack(fill="x", side="top")
            ttk.Label(top, text=APP_NAME, style="Brand.TLabel").pack(side="left")
            ttk.Label(top, style="Status.TLabel",
                      text="  offline · open source · by QuickOpen").pack(side="left")
            self._theme_btn = ttk.Button(
                top, style="Toggle.TButton", command=self.toggle_theme,
                text="☀ Light mode" if self.theme == "dark" else "🌙 Dark mode")
            self._theme_btn.pack(side="right")

            body = ttk.Frame(self, style="TFrame")
            body.pack(fill="both", expand=True)

            side = ttk.Frame(body, style="Sidebar.TFrame", width=200)
            side.pack(side="left", fill="y")
            side.pack_propagate(False)
            self.nav = ttk.Treeview(side, show="tree", selectmode="browse",
                                    style="Sidebar.Treeview")
            self.nav.pack(fill="both", expand=True, padx=6, pady=6)
            self._nav_ids = {}
            for sid, label in SECTIONS:
                iid = self.nav.insert("", "end", text="  " + label)
                self._nav_ids[iid] = sid
            self.nav.bind("<<TreeviewSelect>>", self._on_nav_select)

            main = ttk.Frame(body, style="TFrame", padding=(16, 12))
            main.pack(side="left", fill="both", expand=True)

            head = ttk.Frame(main, style="TFrame")
            head.pack(fill="x")
            self.title_lbl = ttk.Label(head, text="Welcome", style="Header.TLabel")
            self.title_lbl.pack(anchor="w")
            self.desc_lbl = ttk.Label(head, text="", style="Sub.TLabel",
                                      wraplength=720, justify="left")
            self.desc_lbl.pack(anchor="w", pady=(2, 8))
            ttk.Separator(main).pack(fill="x")

            self.container = ttk.Frame(main, style="TFrame")
            self.container.pack(fill="both", expand=True, pady=(10, 8))
            self._current_id = None

            # shared inline result / error bar
            bar = ttk.Frame(self, style="Sidebar.TFrame", padding=(12, 6))
            bar.pack(fill="x", side="bottom")
            self.status_lbl = ttk.Label(bar, text="Ready", style="Status.TLabel",
                                        width=14, anchor="w")
            self.status_lbl.pack(side="left")
            self.result_lbl = ttk.Label(bar, text="", style="Status.TLabel",
                                        anchor="w", wraplength=760, justify="left")
            self.result_lbl.pack(side="left", fill="x", expand=True, padx=8)

        # ---- section navigation
        def _select_first_section(self):
            for iid in self._nav_ids:
                self.nav.selection_set(iid)
                self.nav.see(iid)
                break

        def _on_nav_select(self, _e=None):
            sel = self.nav.selection()
            if not sel:
                return
            sid = self._nav_ids.get(sel[0])
            if sid:
                self._show_section(sid)

        def _show_section(self, sid):
            if self._current is not None:
                self._current.pack_forget()
            panel = self._panels.get(sid)
            if panel is None:
                panel = ttk.Frame(self.container, style="TFrame")
                getattr(self, "_build_" + sid)(panel)
                self._panels[sid] = panel
                self._apply_theme()
            panel.pack(fill="both", expand=True)
            self._current = panel
            self._current_id = sid
            label = dict(SECTIONS).get(sid, sid)
            self.title_lbl.configure(text=label)
            self.desc_lbl.configure(text=SECTION_DESCRIPTIONS.get(sid, ""))
            self._clear_result()
            # refresh dynamic content on entry
            refresh = getattr(self, "_refresh_" + sid, None)
            if refresh:
                refresh()

        # ---- inline result bar
        def _set_status(self, text, kind="idle"):
            p = self._pal()
            color = {"ok": p["ok"], "err": p["err"]}.get(kind, p["muted"])
            self.status_lbl.configure(text=text, foreground=color)

        def _clear_result(self):
            self.result_lbl.configure(text="")
            self._set_status("Ready")

        def _show_error(self, message):
            self.result_lbl.configure(text="✕ " + message, foreground=self._pal()["err"])
            self._set_status("error", kind="err")

        def _show_ok(self, message):
            self.result_lbl.configure(text="✓ " + message, foreground=self._pal()["ok"])
            self._set_status("done", kind="ok")

        def _guard(self, fn, ok_msg=None):
            """Run *fn*; surface RecallDeckError inline, never a traceback."""
            try:
                result = fn()
            except RecallDeckError as exc:
                self._show_error(str(exc))
                return None
            except Exception as exc:  # never leak a traceback to the user
                self._show_error(f"Unexpected error: {exc}")
                return None
            if ok_msg:
                self._show_ok(ok_msg)
            return result

        def _deck_names(self):
            return [d.name for d in self.store.list_decks()]

        def _today(self):
            return date.today()

        # =================================================================
        # Section: Decks
        # =================================================================
        def _build_decks(self, panel):
            left = ttk.Frame(panel, style="TFrame")
            left.pack(side="left", fill="both", expand=True)
            self.deck_list = tk.Listbox(left, exportselection=False, activestyle="none")
            self.track(self.deck_list, "listbox")
            self.deck_list.pack(fill="both", expand=True)
            self.deck_list.bind("<<ListboxSelect>>", self._on_deck_pick)

            right = ttk.Frame(panel, style="TFrame", padding=(12, 0))
            right.pack(side="left", fill="y")
            ttk.Button(right, text="New deck…", style="Accent.TButton",
                       command=self._deck_new).pack(fill="x", pady=3)
            ttk.Button(right, text="Rename…", command=self._deck_rename).pack(
                fill="x", pady=3)
            ttk.Button(right, text="Delete", command=self._deck_delete).pack(
                fill="x", pady=3)
            ttk.Separator(right).pack(fill="x", pady=8)
            ttk.Button(right, text="Study this deck",
                       command=lambda: self._go_deck("study")).pack(fill="x", pady=3)
            ttk.Button(right, text="Browse cards",
                       command=lambda: self._go_deck("browse")).pack(fill="x", pady=3)

        def _refresh_decks(self):
            if not hasattr(self, "deck_list"):
                return
            self.deck_list.delete(0, "end")
            for name in self._guard(self._deck_names) or []:
                self.deck_list.insert("end", name)

        def _selected_deck_name(self):
            sel = self.deck_list.curselection()
            if not sel:
                return None
            return self.deck_list.get(sel[0])

        def _on_deck_pick(self, _e=None):
            name = self._selected_deck_name()
            if name:
                self.current_deck = self._guard(lambda: self.store.get_deck(name))

        def _deck_new(self):
            name = simpledialog.askstring("New deck", "Deck name:", parent=self)
            if not name:
                return
            deck = self._guard(lambda: self.store.add_deck(name),
                               ok_msg=f"Created deck {name!r}.")
            if deck:
                self._refresh_decks()

        def _deck_rename(self):
            name = self._selected_deck_name()
            if not name:
                self._show_error("Select a deck to rename.")
                return
            new = simpledialog.askstring("Rename deck", "New name:",
                                         initialvalue=name, parent=self)
            if not new:
                return
            if self._guard(lambda: self.store.rename_deck(name, new),
                           ok_msg=f"Renamed to {new!r}."):
                self._refresh_decks()

        def _deck_delete(self):
            name = self._selected_deck_name()
            if not name:
                self._show_error("Select a deck to delete.")
                return
            if not messagebox.askyesno("Delete deck",
                                       f"Delete {name!r} and all its cards?"):
                return
            if self._guard(lambda: self.store.remove_deck(name),
                           ok_msg=f"Deleted {name!r}.") is not None:
                self.current_deck = None
                self._refresh_decks()

        def _go_deck(self, section):
            name = self._selected_deck_name()
            if not name:
                self._show_error("Select a deck first.")
                return
            self.current_deck = self._guard(lambda: self.store.get_deck(name))
            for iid, sid in self._nav_ids.items():
                if sid == section:
                    self.nav.selection_set(iid)
                    return

        # =================================================================
        # Section: Study
        # =================================================================
        def _build_study(self, panel):
            bar = ttk.Frame(panel, style="TFrame")
            bar.pack(fill="x")
            ttk.Label(bar, text="Deck:", style="Muted.TLabel").pack(side="left")
            self.study_deck = tk.StringVar()
            self.study_menu = ttk.Combobox(bar, textvariable=self.study_deck,
                                           state="readonly", width=28)
            self.study_menu.pack(side="left", padx=6)
            ttk.Button(bar, text="Start", style="Accent.TButton",
                       command=self._study_start).pack(side="left", padx=4)
            self.study_progress = ttk.Label(bar, text="", style="Muted.TLabel")
            self.study_progress.pack(side="right")

            face = ttk.Frame(panel, style="Card.TFrame", padding=20)
            face.pack(fill="both", expand=True, pady=12)
            self.card_front = ttk.Label(face, text="Press Start to begin.",
                                        style="Face.TLabel", wraplength=640,
                                        justify="center", anchor="center")
            self.card_front.pack(fill="x", expand=True, pady=(20, 8))
            ttk.Separator(face).pack(fill="x", pady=6)
            self.card_back = ttk.Label(face, text="", style="Face.TLabel",
                                       wraplength=640, justify="center",
                                       anchor="center", foreground=self._pal()["muted"])
            self.card_back.pack(fill="x", expand=True, pady=(8, 20))

            ctrl = ttk.Frame(panel, style="TFrame")
            ctrl.pack(fill="x")
            self.show_btn = ttk.Button(ctrl, text="Show Answer",
                                       style="Accent.TButton",
                                       command=self._study_reveal)
            self.show_btn.pack()
            self.grade_frame = ttk.Frame(panel, style="TFrame")
            self.grade_frame.pack(fill="x", pady=6)
            for label, q in GRADES:
                ttk.Button(self.grade_frame, text=label,
                           command=lambda qq=q: self._study_grade(qq)).pack(
                    side="left", expand=True, fill="x", padx=3)

        def _refresh_study(self):
            names = self._guard(self._deck_names) or []
            self.study_menu.configure(values=names)
            if self.current_deck and self.current_deck.name in names:
                self.study_deck.set(self.current_deck.name)
            elif names and not self.study_deck.get():
                self.study_deck.set(names[0])
            self._study_reset_face()

        def _study_reset_face(self):
            self._study_queue = []
            self._study_card = None
            self._answer_shown = False
            self.card_front.configure(text="Press Start to begin.")
            self.card_back.configure(text="")
            self.study_progress.configure(text="")
            self._grade_state(False)

        def _grade_state(self, enabled):
            for child in self.grade_frame.winfo_children():
                try:
                    child.state(["!disabled"] if enabled else ["disabled"])
                except Exception:
                    pass

        def _study_start(self):
            name = self.study_deck.get()
            if not name:
                self._show_error("Pick a deck to study.")
                return
            queue = self._guard(lambda: self.store.due_cards(name, self._today()))
            if queue is None:
                return
            self._study_queue = list(queue)
            self._study_deck_name = name
            if not self._study_queue:
                self.card_front.configure(text="Nothing due in this deck. ")
                self.card_back.configure(text="")
                self.study_progress.configure(text="0 due")
                self._grade_state(False)
                return
            self._total_due = len(self._study_queue)
            self._reviewed_count = 0
            self._next_card()

        def _next_card(self):
            if not self._study_queue:
                self.card_front.configure(text="Deck complete! ")
                self.card_back.configure(text="")
                self._answer_shown = False
                self._grade_state(False)
                self.show_btn.state(["disabled"])
                self.study_progress.configure(
                    text=f"{self._reviewed_count} reviewed")
                self._show_ok("Study session complete.")
                return
            self._study_card = self._study_queue.pop(0)
            self._answer_shown = False
            self.card_front.configure(text=self._study_card.front)
            self.card_back.configure(text="")
            self.show_btn.state(["!disabled"])
            self._grade_state(False)
            done = self._reviewed_count
            self.study_progress.configure(
                text=f"{done + 1} / {self._total_due}")

        def _study_reveal(self):
            if not self._study_card:
                return
            self.card_back.configure(text=self._study_card.back)
            self._answer_shown = True
            self.show_btn.state(["disabled"])
            self._grade_state(True)

        def _study_grade(self, quality):
            if not self._study_card or not self._answer_shown:
                return
            card = self._study_card
            updated = self._guard(
                lambda: self.store.apply_review(card.id, quality, self._today()))
            if updated is None:
                return
            self._reviewed_count += 1
            self._next_card()

        # =================================================================
        # Section: Browse / Edit
        # =================================================================
        def _build_browse(self, panel):
            bar = ttk.Frame(panel, style="TFrame")
            bar.pack(fill="x")
            ttk.Label(bar, text="Deck:", style="Muted.TLabel").pack(side="left")
            self.browse_deck = tk.StringVar()
            self.browse_menu = ttk.Combobox(bar, textvariable=self.browse_deck,
                                            state="readonly", width=28)
            self.browse_menu.pack(side="left", padx=6)
            self.browse_menu.bind("<<ComboboxSelected>>",
                                  lambda _e: self._browse_load())
            ttk.Button(bar, text="Add card…", style="Accent.TButton",
                       command=self._card_add).pack(side="left", padx=4)
            ttk.Button(bar, text="Edit…", command=self._card_edit).pack(side="left")
            ttk.Button(bar, text="Delete", command=self._card_delete).pack(
                side="left", padx=4)

            cols = ("front", "back", "tags", "due")
            self.card_tree = ttk.Treeview(panel, columns=cols, show="headings",
                                          selectmode="browse")
            for c, w in zip(cols, (240, 240, 120, 100)):
                self.card_tree.heading(c, text=c.capitalize())
                self.card_tree.column(c, width=w, anchor="w")
            self.card_tree.pack(fill="both", expand=True, pady=(8, 0))
            self._card_row_ids = {}

        def _refresh_browse(self):
            names = self._guard(self._deck_names) or []
            self.browse_menu.configure(values=names)
            if self.current_deck and self.current_deck.name in names:
                self.browse_deck.set(self.current_deck.name)
            elif names and not self.browse_deck.get():
                self.browse_deck.set(names[0])
            self._browse_load()

        def _browse_load(self):
            self.card_tree.delete(*self.card_tree.get_children())
            self._card_row_ids = {}
            name = self.browse_deck.get()
            if not name:
                return
            cards = self._guard(lambda: self.store.list_cards(name)) or []
            for c in cards:
                iid = self.card_tree.insert(
                    "", "end", values=(c.front, c.back, c.tags, c.due_date))
                self._card_row_ids[iid] = c.id

        def _selected_card_id(self):
            sel = self.card_tree.selection()
            if not sel:
                return None
            return self._card_row_ids.get(sel[0])

        def _card_dialog(self, title, front="", back="", tags=""):
            win = tk.Toplevel(self)
            win.title(title)
            win.configure(bg=self._pal()["bg"])
            win.transient(self)
            result = {}
            frm = ttk.Frame(win, style="TFrame", padding=12)
            frm.pack(fill="both", expand=True)
            fv, bv, tv = tk.StringVar(value=front), tk.StringVar(value=back), \
                tk.StringVar(value=tags)
            for i, (lbl, var) in enumerate((("Front", fv), ("Back", bv),
                                            ("Tags", tv))):
                ttk.Label(frm, text=lbl, style="Muted.TLabel").grid(
                    row=i, column=0, sticky="w", pady=4)
                ttk.Entry(frm, textvariable=var, width=40).grid(
                    row=i, column=1, pady=4, padx=6)
            btns = ttk.Frame(frm, style="TFrame")
            btns.grid(row=3, column=0, columnspan=2, pady=(8, 0))

            def ok():
                result["front"] = fv.get()
                result["back"] = bv.get()
                result["tags"] = tv.get()
                win.destroy()

            ttk.Button(btns, text="Save", style="Accent.TButton",
                       command=ok).pack(side="left", padx=4)
            ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left")
            win.grab_set()
            self.wait_window(win)
            return result or None

        def _card_add(self):
            name = self.browse_deck.get()
            if not name:
                self._show_error("Pick a deck first.")
                return
            data = self._card_dialog("Add card")
            if not data:
                return
            if self._guard(lambda: self.store.add_card(
                    name, data["front"], data["back"], tags=data["tags"],
                    now=self._today()), ok_msg="Card added."):
                self._browse_load()

        def _card_edit(self):
            cid = self._selected_card_id()
            if not cid:
                self._show_error("Select a card to edit.")
                return
            card = self._guard(lambda: self.store.get_card(cid))
            if not card:
                return
            data = self._card_dialog("Edit card", card.front, card.back, card.tags)
            if not data:
                return
            if self._guard(lambda: self.store.update_card(
                    cid, front=data["front"], back=data["back"], tags=data["tags"]),
                    ok_msg="Card updated."):
                self._browse_load()

        def _card_delete(self):
            cid = self._selected_card_id()
            if not cid:
                self._show_error("Select a card to delete.")
                return
            if not messagebox.askyesno("Delete card", "Delete this card?"):
                return
            if self._guard(lambda: self.store.remove_card(cid),
                           ok_msg="Card deleted.") is not None:
                self._browse_load()

        # =================================================================
        # Section: Stats
        # =================================================================
        def _build_stats(self, panel):
            bar = ttk.Frame(panel, style="TFrame")
            bar.pack(fill="x")
            ttk.Label(bar, text="Deck:", style="Muted.TLabel").pack(side="left")
            self.stats_deck = tk.StringVar()
            self.stats_menu = ttk.Combobox(bar, textvariable=self.stats_deck,
                                           state="readonly", width=28)
            self.stats_menu.pack(side="left", padx=6)
            self.stats_menu.bind("<<ComboboxSelected>>",
                                 lambda _e: self._refresh_stats())
            self.stats_canvas = tk.Canvas(panel, height=320, highlightthickness=1)
            self.track(self.stats_canvas, "canvas")
            self.stats_canvas.pack(fill="both", expand=True, pady=(10, 0))

        def _refresh_stats(self):
            if not hasattr(self, "stats_menu"):
                return
            names = self._guard(self._deck_names) or []
            self.stats_menu.configure(values=names)
            if self.current_deck and self.current_deck.name in names:
                self.stats_deck.set(self.current_deck.name)
            elif names and not self.stats_deck.get():
                self.stats_deck.set(names[0])
            self._draw_stats()

        def _draw_stats(self):
            c = self.stats_canvas
            c.delete("all")
            name = self.stats_deck.get()
            if not name:
                return
            s = self._guard(lambda: stats_mod.deck_stats(
                self.store, name, self._today()))
            if not s:
                return
            p = self._pal()
            bars = [("Total", s["total"]), ("Due", s["due"]), ("New", s["new"]),
                    ("Young", s["young"]), ("Mature", s["mature"]),
                    ("Lapses", s["lapses"])]
            top = max([v for _, v in bars] + [1])
            x, base, bw, gap, maxh = 40, 250, 60, 40, 200
            for label, val in bars:
                h = int(maxh * val / top)
                c.create_rectangle(x, base - h, x + bw, base,
                                   fill=p["primary"], outline=p["primary"])
                c.create_text(x + bw / 2, base - h - 12, text=str(val),
                              fill=p["text"], font=(FONT, 10, "bold"))
                c.create_text(x + bw / 2, base + 14, text=label, fill=p["muted"],
                              font=(FONT, 9))
                x += bw + gap
            retention = "n/a" if s["retention"] is None else f"{s['retention']:.1f}%"
            c.create_text(40, 30, anchor="w", fill=p["text"], font=(FONT, 13, "bold"),
                          text=f"{name}  —  retention {retention}  ·  "
                               f"{s['reviews']} reviews")

        # =================================================================
        # Section: Import / Export
        # =================================================================
        def _build_io(self, panel):
            bar = ttk.Frame(panel, style="TFrame")
            bar.pack(fill="x")
            ttk.Label(bar, text="Deck:", style="Muted.TLabel").pack(side="left")
            self.io_deck = tk.StringVar()
            self.io_menu = ttk.Combobox(bar, textvariable=self.io_deck,
                                        state="readonly", width=28)
            self.io_menu.pack(side="left", padx=6)

            body = ttk.Frame(panel, style="TFrame", padding=(0, 16))
            body.pack(fill="x")
            imp = ttk.Labelframe(body, text="Import", padding=12)
            imp.pack(fill="x", pady=6)
            ttk.Label(imp, text="Add cards from a CSV (front,back,tags) or JSON file.",
                      style="Muted.TLabel").pack(anchor="w")
            ttk.Button(imp, text="Choose file & import…", style="Accent.TButton",
                       command=self._do_import).pack(anchor="w", pady=(8, 0))

            exp = ttk.Labelframe(body, text="Export", padding=12)
            exp.pack(fill="x", pady=6)
            ttk.Label(exp, text="Save this deck's cards to a CSV or JSON file.",
                      style="Muted.TLabel").pack(anchor="w")
            ttk.Button(exp, text="Choose destination & export…",
                       command=self._do_export).pack(anchor="w", pady=(8, 0))

        def _refresh_io(self):
            names = self._guard(self._deck_names) or []
            self.io_menu.configure(values=names)
            if self.current_deck and self.current_deck.name in names:
                self.io_deck.set(self.current_deck.name)
            elif names and not self.io_deck.get():
                self.io_deck.set(names[0])

        def _do_import(self):
            name = self.io_deck.get()
            if not name:
                self._show_error("Pick a deck to import into.")
                return
            path = filedialog.askopenfilename(
                title="Import cards",
                filetypes=[("Cards", "*.csv *.json"), ("CSV", "*.csv"),
                           ("JSON", "*.json"), ("All files", "*.*")])
            if not path:
                return
            n = self._guard(lambda: importer.import_file(
                self.store, name, path, now=self._today()))
            if n is not None:
                self._show_ok(f"Imported {n} card(s) into {name!r}.")

        def _do_export(self):
            name = self.io_deck.get()
            if not name:
                self._show_error("Pick a deck to export.")
                return
            path = filedialog.asksaveasfilename(
                title="Export deck", defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("JSON", "*.json")])
            if not path:
                return
            n = self._guard(lambda: importer.export_file(self.store, name, path))
            if n is not None:
                self._show_ok(f"Exported {n} card(s) to {os.path.basename(path)}.")

        # ---- shutdown
        def _on_close(self):
            try:
                self.store.close()
            except Exception:
                pass
            self.destroy()

    return App


def main():
    """Entry point: build the root window and run.  Degrades on headless hosts.

    Importing this module does nothing; only this function creates a Tk root.
    With no display (e.g. a server) it prints a friendly note and returns 0
    instead of raising, so callers can rely on a clean exit code.
    """
    try:
        import tkinter as tk
    except Exception as exc:  # tkinter missing entirely
        print(f"{APP_NAME}: a graphical environment with tkinter is required "
              f"to run the GUI ({exc}).")
        return 0

    try:
        App = build_app()
        app = App()
    except tk.TclError as exc:
        # Typically "no display name and no $DISPLAY environment variable".
        print(f"{APP_NAME}: no graphical display available — cannot start the "
              f"GUI here ({exc}). This app is intended for the Windows desktop.")
        return 0
    except Exception as exc:
        print(f"{APP_NAME}: could not start the GUI ({exc}).")
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
