#!/usr/bin/env python3
r"""RecallDeck -- an Aura (QuickOpen design system) GUI on the ``recalldeck`` engine.

A single Aura window: a left sidebar (Decks, Study, Browse/Edit, Stats,
Import/Export) and a main panel that swaps to the selected section.  Every
operation calls the tested core library (never re-implements SRS or storage);
failures are shown in the Aura status bar as the ``RecallDeckError`` message --
never a raw traceback.

Design goals baked in here (mirrors the QuickOpen house style):
  * built on the vendored ``recalldeck/aura.py`` design system, which layers the
    quickopen.ai look (deep space + light) over CustomTkinter.  Runtime deps:
    ``customtkinter`` (+ ``darkdetect``) -- declared in requirements.txt; the
    PyInstaller build adds ``--collect-all customtkinter``.
  * Importing this module does nothing.  Only :func:`main` builds a root window,
    and it degrades gracefully (prints a message, returns 0) with no display or
    with customtkinter missing.
  * Frozen-exe safe: bundled assets are resolved via ``sys._MEIPASS`` / the exe
    directory when ``sys.frozen`` is set -- never ``__file__``.
  * The SM-2 study/review flow and scheduling are unchanged -- reveal the
    answer, grade Again/Hard/Good/Easy, and every schedule change goes through
    ``store.apply_review`` (SM-2 in ``recalldeck.srs``).

100% AI-built, open source, published on QuickOpen (quickopen.ai).
"""

from __future__ import annotations

import os
import sys
from datetime import date

# NOTE: tkinter/customtkinter are imported lazily inside main()/build_app so
# that merely importing this module (e.g. during packaging or on a headless CI
# box) never fails and has no side effects.

APP_NAME = "RecallDeck"
APP_VERSION = "1.0.0"
WINDOW_TITLE = "RecallDeck — by QuickOpen (quickopen.ai)"
PROJECT_URL = "https://quickopen.ai"
ACCENT = "#5b86f7"      # publish/specs/recall-deck.json "accent": [91, 134, 247]

# Study grade buttons -> SM-2 qualities.
GRADES = [("Again", 2), ("Hard", 3), ("Good", 4), ("Easy", 5)]

# (id, label, DejaVu-safe nav glyph)
SECTIONS = [
    ("decks", "Decks", "⛁"),
    ("study", "Study", "↻"),
    ("browse", "Browse / Edit", "✎"),
    ("stats", "Stats", "▦"),
    ("io", "Import / Export", "⇅"),
]

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
# GUI construction (kept inside a function so import never needs a display and
# never needs customtkinter installed)
# ---------------------------------------------------------------------------
def build_app():
    """Construct and return the App class bound to live GUI imports."""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    import customtkinter as ctk

    from . import aura, guiconfig
    from .errors import RecallDeckError
    from .db import Store
    from . import importer, stats as stats_mod

    def _tok(key):
        """(light, dark) tuple for a TOKENS key -- CustomTkinter auto-switches."""
        return (aura.TOKENS["light"][key], aura.TOKENS["dark"][key])

    class App(aura.AuraApp):
        def __init__(self):
            super().__init__(
                title=WINDOW_TITLE, app_name=APP_NAME, accent=ACCENT,
                theme=guiconfig.get_theme(),
                icon_png=asset_path("recall-deck.png"), version=APP_VERSION,
                tagline="spaced repetition",
                on_theme_change=guiconfig.set_theme,
                size=(1040, 660), min_size=(860, 540))

            self._img_refs_gui = []      # keep PhotoImage refs alive

            # data / study state
            self.store = Store()
            self.current_deck = None     # Deck or None
            self._study_queue = []       # remaining due Cards
            self._study_card = None
            self._answer_shown = False

            self._set_icon()
            self._build_menu()
            for sid, label, glyph in SECTIONS:
                self.add_section(sid, label, glyph,
                                 getattr(self, "_build_" + sid))
            self.show("decks")
            self.set_status("Ready")
            self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- assets / icon
        def _set_icon(self):
            try:
                ico = asset_path("recall-deck.ico")
                if ico and os.name == "nt":
                    self.iconbitmap(ico)
                    return
            except Exception:
                pass
            try:
                png = asset_path("recall-deck.png")
                if png:
                    img = tk.PhotoImage(file=png)
                    self._img_refs_gui.append(img)
                    self.iconphoto(True, img)
            except Exception:
                pass  # icon is cosmetic; never block launch

        # ---- navigation: raise the section, then refresh its dynamic content
        def show(self, sid):
            super().show(sid)
            refresh = getattr(self, "_refresh_" + sid, None)
            if refresh:
                refresh()

        # ---- theme: redraw the manually-coloured stats canvas on a flip
        def set_theme(self, theme):
            super().set_theme(theme)
            if self.active_section == "stats":
                self._draw_stats()

        # ---- menu (native menus stay; theme lives in the sidebar toggle too)
        def _build_menu(self):
            bar = tk.Menu(self)
            filem = tk.Menu(bar, tearoff=0)
            filem.add_command(label="Exit", command=self._on_close)
            bar.add_cascade(label="File", menu=filem)
            viewm = tk.Menu(bar, tearoff=0)
            viewm.add_command(
                label="Toggle dark mode",
                command=lambda: self.set_theme(
                    "light" if self.theme == "dark" else "dark"))
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

        # ---- inline status bar (the Aura status bar is the app's voice)
        def _guard(self, fn, ok_msg=None):
            """Run *fn*; surface RecallDeckError inline, never a traceback."""
            try:
                result = fn()
            except RecallDeckError as exc:
                self.set_error(str(exc))
                return None
            except Exception as exc:  # never leak a traceback to the user
                self.set_error(f"Unexpected error: {exc}")
                return None
            if ok_msg:
                self.set_success(ok_msg)
            return result

        def _deck_names(self):
            return [d.name for d in self.store.list_decks()]

        def _today(self):
            return date.today()

        # =================================================================
        # Section: Decks
        # =================================================================
        def _build_decks(self, frame):
            aura.Caption(frame, SECTION_DESCRIPTIONS["decks"]).pack(
                anchor="w", pady=(0, 14))
            body = ctk.CTkFrame(frame, fg_color="transparent")
            body.pack(fill="both", expand=True)

            left = aura.Card(body, title="Your decks")
            left.pack(side="left", fill="both", expand=True, padx=(0, 14))
            self.deck_list = tk.Listbox(left.body, exportselection=False,
                                        activestyle="none", height=12,
                                        borderwidth=0, highlightthickness=1)
            aura.track(self.deck_list, "listbox")
            self.deck_list.pack(fill="both", expand=True)
            self.deck_list.bind("<<ListboxSelect>>", self._on_deck_pick)

            right = ctk.CTkFrame(body, fg_color="transparent", width=180)
            right.pack(side="left", fill="y")
            aura.AuraButton(right, "New deck…",
                            command=self._deck_new).pack(fill="x", pady=3)
            aura.AuraButton(right, "Rename…", kind="secondary",
                            command=self._deck_rename).pack(fill="x", pady=3)
            aura.AuraButton(right, "Delete", kind="danger",
                            command=self._deck_delete).pack(fill="x", pady=3)
            aura.AuraButton(right, "Study this deck", kind="secondary",
                            command=lambda: self._go_deck("study")).pack(
                fill="x", pady=(16, 3))
            aura.AuraButton(right, "Browse cards", kind="secondary",
                            command=lambda: self._go_deck("browse")).pack(
                fill="x", pady=3)

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
                self.set_error("Select a deck to rename.")
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
                self.set_error("Select a deck to delete.")
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
                self.set_error("Select a deck first.")
                return
            self.current_deck = self._guard(lambda: self.store.get_deck(name))
            self.show(section)

        # =================================================================
        # Section: Study
        # =================================================================
        def _build_study(self, frame):
            aura.Caption(frame, SECTION_DESCRIPTIONS["study"]).pack(
                anchor="w", pady=(0, 14))
            bar = ctk.CTkFrame(frame, fg_color="transparent")
            bar.pack(fill="x")
            ctk.CTkLabel(bar, text="Deck", font=aura.font(),
                         text_color=_tok("muted")).pack(side="left")
            self.study_deck = tk.StringVar()
            self.study_menu = aura.AuraCombo(bar, variable=self.study_deck,
                                             values=[], state="readonly",
                                             width=240)
            self.study_menu.pack(side="left", padx=(8, 8))
            aura.AuraButton(bar, "Start",
                            command=self._study_start).pack(side="left")
            self.study_progress = aura.Caption(bar, "")
            self.study_progress.pack(side="right")

            face = aura.Card(frame)
            face.pack(fill="both", expand=True, pady=12)
            self.card_front = ctk.CTkLabel(
                face.body, text="Press Start to begin.", font=aura.font(18),
                wraplength=640, justify="center")
            self.card_front.pack(fill="x", expand=True, pady=(20, 8))
            ctk.CTkFrame(face.body, height=1, fg_color=_tok("border")).pack(
                fill="x", pady=6)
            self.card_back = ctk.CTkLabel(
                face.body, text="", font=aura.font(18),
                text_color=_tok("muted"), wraplength=640, justify="center")
            self.card_back.pack(fill="x", expand=True, pady=(8, 20))

            ctrl = ctk.CTkFrame(frame, fg_color="transparent")
            ctrl.pack(fill="x")
            self.show_btn = aura.AuraButton(ctrl, "Show Answer",
                                            command=self._study_reveal)
            self.show_btn.pack()
            self.grade_frame = ctk.CTkFrame(frame, fg_color="transparent")
            self.grade_frame.pack(fill="x", pady=6)
            grade_kind = {2: "danger", 3: "secondary", 4: "primary",
                          5: "secondary"}
            for label, q in GRADES:
                aura.AuraButton(
                    self.grade_frame, label, kind=grade_kind.get(q, "secondary"),
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
                self.set_error("Pick a deck to study.")
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
                self.set_success("Study session complete.")
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
        def _build_browse(self, frame):
            aura.Caption(frame, SECTION_DESCRIPTIONS["browse"]).pack(
                anchor="w", pady=(0, 14))
            bar = ctk.CTkFrame(frame, fg_color="transparent")
            bar.pack(fill="x")
            ctk.CTkLabel(bar, text="Deck", font=aura.font(),
                         text_color=_tok("muted")).pack(side="left")
            self.browse_deck = tk.StringVar()
            self.browse_menu = aura.AuraCombo(
                bar, variable=self.browse_deck, values=[], state="readonly",
                width=240, command=lambda _v: self._browse_load())
            self.browse_menu.pack(side="left", padx=(8, 8))
            aura.AuraButton(bar, "Add card…",
                            command=self._card_add).pack(side="left")
            aura.AuraButton(bar, "Edit…", kind="secondary",
                            command=self._card_edit).pack(side="left", padx=8)
            aura.AuraButton(bar, "Delete", kind="danger",
                            command=self._card_delete).pack(side="left")

            body = ctk.CTkFrame(frame, fg_color="transparent")
            body.pack(fill="both", expand=True, pady=(10, 0))
            cols = ("front", "back", "tags", "due")
            self.card_tree = ttk.Treeview(body, columns=cols, show="headings",
                                          selectmode="browse")
            for c, label, w in (("front", "Front", 240), ("back", "Back", 240),
                                ("tags", "Tags", 120), ("due", "Due", 100)):
                self.card_tree.heading(c, text=aura.spaced(label), anchor="w")
                self.card_tree.column(c, width=w, anchor="w")
            sb = ttk.Scrollbar(body, orient="vertical",
                               command=self.card_tree.yview)
            self.card_tree.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            self.card_tree.pack(side="left", fill="both", expand=True)
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
            win.configure(bg=aura.P("bg"))
            win.transient(self)
            result = {}
            frm = ctk.CTkFrame(win, fg_color="transparent")
            frm.pack(fill="both", expand=True, padx=16, pady=16)
            entries = {}
            for i, (lbl, val) in enumerate((("Front", front), ("Back", back),
                                            ("Tags", tags))):
                ctk.CTkLabel(frm, text=lbl, font=aura.font(),
                             text_color=_tok("muted")).grid(
                    row=i, column=0, sticky="w", pady=6, padx=(0, 10))
                ent = aura.AuraEntry(frm, width=320)
                if val:
                    ent.insert(0, val)
                ent.grid(row=i, column=1, pady=6)
                entries[lbl.lower()] = ent
            btns = ctk.CTkFrame(frm, fg_color="transparent")
            btns.grid(row=3, column=0, columnspan=2, pady=(12, 0), sticky="e")

            def ok():
                result["front"] = entries["front"].get()
                result["back"] = entries["back"].get()
                result["tags"] = entries["tags"].get()
                win.destroy()

            aura.AuraButton(btns, "Save", command=ok).pack(side="left",
                                                           padx=(0, 8))
            aura.AuraButton(btns, "Cancel", kind="secondary",
                            command=win.destroy).pack(side="left")
            win.grab_set()
            self.wait_window(win)
            return result or None

        def _card_add(self):
            name = self.browse_deck.get()
            if not name:
                self.set_error("Pick a deck first.")
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
                self.set_error("Select a card to edit.")
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
                self.set_error("Select a card to delete.")
                return
            if not messagebox.askyesno("Delete card", "Delete this card?"):
                return
            if self._guard(lambda: self.store.remove_card(cid),
                           ok_msg="Card deleted.") is not None:
                self._browse_load()

        # =================================================================
        # Section: Stats
        # =================================================================
        def _build_stats(self, frame):
            aura.Caption(frame, SECTION_DESCRIPTIONS["stats"]).pack(
                anchor="w", pady=(0, 14))
            bar = ctk.CTkFrame(frame, fg_color="transparent")
            bar.pack(fill="x")
            ctk.CTkLabel(bar, text="Deck", font=aura.font(),
                         text_color=_tok("muted")).pack(side="left")
            self.stats_deck = tk.StringVar()
            self.stats_menu = aura.AuraCombo(
                bar, variable=self.stats_deck, values=[], state="readonly",
                width=240, command=lambda _v: self._refresh_stats())
            self.stats_menu.pack(side="left", padx=(8, 8))
            self.stats_canvas = tk.Canvas(frame, height=320, bd=0,
                                          highlightthickness=1)
            aura.track(self.stats_canvas, "canvas")
            self.stats_canvas.pack(fill="both", expand=True, pady=(12, 0))

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
            c = getattr(self, "stats_canvas", None)
            if c is None:
                return
            c.delete("all")
            name = self.stats_deck.get()
            if not name:
                return
            s = self._guard(lambda: stats_mod.deck_stats(
                self.store, name, self._today()))
            if not s:
                return
            accent, text, muted = aura.P("accent"), aura.P("text"), aura.P("muted")
            bars = [("Total", s["total"]), ("Due", s["due"]), ("New", s["new"]),
                    ("Young", s["young"]), ("Mature", s["mature"]),
                    ("Lapses", s["lapses"])]
            top = max([v for _, v in bars] + [1])
            x, base, bw, gap, maxh = 40, 250, 60, 40, 200
            for label, val in bars:
                h = int(maxh * val / top)
                c.create_rectangle(x, base - h, x + bw, base,
                                   fill=accent, outline=accent)
                c.create_text(x + bw / 2, base - h - 12, text=str(val),
                              fill=text, font=aura.font(10, "bold"))
                c.create_text(x + bw / 2, base + 14, text=label, fill=muted,
                              font=aura.font(9))
                x += bw + gap
            retention = "n/a" if s["retention"] is None else f"{s['retention']:.1f}%"
            c.create_text(40, 30, anchor="w", fill=text, font=aura.font(13, "bold"),
                          text=f"{name}  —  retention {retention}  ·  "
                               f"{s['reviews']} reviews")

        # =================================================================
        # Section: Import / Export
        # =================================================================
        def _build_io(self, frame):
            aura.Caption(frame, SECTION_DESCRIPTIONS["io"]).pack(
                anchor="w", pady=(0, 14))
            bar = ctk.CTkFrame(frame, fg_color="transparent")
            bar.pack(fill="x")
            ctk.CTkLabel(bar, text="Deck", font=aura.font(),
                         text_color=_tok("muted")).pack(side="left")
            self.io_deck = tk.StringVar()
            self.io_menu = aura.AuraCombo(bar, variable=self.io_deck, values=[],
                                          state="readonly", width=240)
            self.io_menu.pack(side="left", padx=(8, 8))

            imp = aura.Card(frame, title="Import")
            imp.pack(fill="x", pady=(16, 8))
            ctk.CTkLabel(
                imp.body, justify="left", anchor="w", font=aura.font(),
                text_color=_tok("muted"),
                text="Add cards from a CSV (front,back,tags) or JSON file.").pack(
                anchor="w")
            aura.AuraButton(imp.body, "Choose file & import…",
                            command=self._do_import).pack(anchor="w",
                                                          pady=(10, 0))

            exp = aura.Card(frame, title="Export")
            exp.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(
                exp.body, justify="left", anchor="w", font=aura.font(),
                text_color=_tok("muted"),
                text="Save this deck's cards to a CSV or JSON file.").pack(
                anchor="w")
            aura.AuraButton(exp.body, "Choose destination & export…",
                            kind="secondary",
                            command=self._do_export).pack(anchor="w",
                                                          pady=(10, 0))

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
                self.set_error("Pick a deck to import into.")
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
                self.set_success(f"Imported {n} card(s) into {name!r}.")

        def _do_export(self):
            name = self.io_deck.get()
            if not name:
                self.set_error("Pick a deck to export.")
                return
            path = filedialog.asksaveasfilename(
                title="Export deck", defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("JSON", "*.json")])
            if not path:
                return
            n = self._guard(lambda: importer.export_file(self.store, name, path))
            if n is not None:
                self.set_success(
                    f"Exported {n} card(s) to {os.path.basename(path)}.")

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
    With no display (e.g. a server) or without customtkinter installed, it
    prints a friendly note and returns 0 instead of raising, so callers can
    rely on a clean exit code.
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
    except ImportError as exc:
        print(f"{APP_NAME}: the GUI needs the 'customtkinter' package "
              f"({exc}). Install it with:  pip install customtkinter")
        return 0
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
