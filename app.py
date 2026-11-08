"""题目复习助手 — a small, offline Windows application."""
from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk
import webbrowser

from review_core import INTERVALS, ReviewError, Store, atomic_json, current_day, parse_day
from i18n import LANGUAGES, get_language, set_language, tr
from scrollbars import RoundedScrollbar

APP_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent)
BG = "#F4F6FA"
WHITE = "#FFFFFF"
INK = "#17253C"
MUTED = "#65738A"
LINE = "#E2E7F0"
BLUE = "#315BD7"
PALE = "#EBF0FF"
GREEN = "#15734D"
AMBER = "#A45E13"
FONT = "Microsoft YaHei UI"
UI_SCALE = 1.0


def px(value):
    """Convert 96-DPI layout distances to native screen pixels; fonts stay in points."""
    if isinstance(value, (tuple, list)):
        return tuple(px(item) for item in value)
    return round(value * UI_SCALE)


def enable_dpi_awareness():
    """The exe declares this in its manifest; also cover direct Python launches."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        # SYSTEM_DPI_AWARE. An existing manifest may have already set this.
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def label(parent, text="", size=10, color=INK, bold=False, bg=WHITE, **kwargs):
    return tk.Label(parent, text=text, font=(FONT, size, "bold" if bold else "normal"),
                    fg=color, bg=bg, **kwargs)


def preferred_language(data_dir):
    try:
        saved = json.loads((Path(data_dir) / "settings.json").read_text(encoding="utf-8"))
        language = saved.get("language", "zh-CN")
        return language if language in LANGUAGES else "zh-CN"
    except (OSError, ValueError, AttributeError):
        return "zh-CN"


class ProblemForm(tk.Toplevel):
    def __init__(self, app, problem=None):
        super().__init__(app.root)
        self.app, self.problem = app, problem
        self.title(tr('编辑题目') if problem else tr('新增题目'))
        self.configure(bg=WHITE)
        self.geometry(f"{px(620)}x{px(650)}")
        self.minsize(px(530), px(560))
        self.transient(app.root)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = tk.Frame(self, bg=WHITE)
        header.grid(row=0, column=0, sticky="ew", padx=px(28), pady=px((24, 16)))
        label(header, tr('编辑题目') if problem else tr('记下一道已理解的题'), 17, bold=True).pack(anchor="w")
        label(header, tr('保存后，程序会自动安排接下来的复习。'), color=MUTED).pack(anchor="w", pady=px((6, 0)))
        body = tk.Frame(self, bg=WHITE)
        body.grid(row=1, column=0, sticky="nsew", padx=px(28))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(7, weight=1)
        self.title_var = tk.StringVar(value=problem["title"] if problem else "")
        self.day_var = tk.StringVar(value=problem["learned_on"] if problem else app.store.today().isoformat())
        self.url_var = tk.StringVar(value=problem["url"] if problem else "")
        label(body, tr('题目名称 *'), bold=True).grid(row=0, column=0, sticky="w", pady=px((0, 7)))
        self.title_entry = ttk.Entry(body, textvariable=self.title_var)
        self.title_entry.grid(row=1, column=0, sticky="ew", ipady=px(5))
        label(body, tr('初次学习日期 *'), bold=True).grid(row=2, column=0, sticky="w", pady=px((18, 7)))
        date_row = tk.Frame(body, bg=WHITE)
        date_row.grid(row=3, column=0, sticky="ew")
        locked = bool(problem and problem["completed_count"])
        self.date_entry = ttk.Entry(date_row, textvariable=self.day_var, width=16,
                                    state="readonly" if locked else "normal")
        self.date_entry.pack(side="left", ipady=px(4))
        if not locked:
            ttk.Button(date_row, text=tr('今天'), style="Small.TButton",
                       command=lambda: self.day_var.set(app.store.today().isoformat())).pack(side="left", padx=px(8))
        label(date_row, tr('已有复习记录，日期保留') if locked else tr('YYYY-MM-DD · 看懂题解的那天'),
              size=9, color=MUTED).pack(side="left", padx=px((8, 0)))
        label(body, tr('题目链接（选填）'), bold=True).grid(row=4, column=0, sticky="w", pady=px((18, 7)))
        ttk.Entry(body, textvariable=self.url_var).grid(row=5, column=0, sticky="ew", ipady=px(5))
        label(body, tr('文字备注（选填）'), bold=True).grid(row=6, column=0, sticky="w", pady=px((18, 7)))
        note_frame = tk.Frame(body, bg=LINE, bd=px(1), relief="solid")
        note_frame.grid(row=7, column=0, sticky="nsew")
        self.notes = tk.Text(note_frame, height=7, wrap="word", undo=True, font=(FONT, 10),
                             bg=WHITE, fg=INK, insertbackground=BLUE, padx=px(10), pady=px(9),
                             relief="flat", highlightthickness=px(0))
        note_scroll = RoundedScrollbar(note_frame, command=self.notes.yview, scale=UI_SCALE)
        self.notes.configure(yscrollcommand=note_scroll.set)
        note_scroll.pack(side="right", fill="y")
        self.notes.pack(side="left", fill="both", expand=True)
        self.notes.insert("1.0", problem["notes"] if problem else "")
        footer = tk.Frame(self, bg=WHITE)
        footer.grid(row=2, column=0, sticky="ew", padx=px(28), pady=px(22))
        ttk.Button(footer, text=tr('保存题目'), style="Primary.TButton",
                   command=lambda: app.run(self.save)).pack(side="right")
        ttk.Button(footer, text=tr('取消'), command=self.destroy).pack(side="right", padx=px(10))
        self.delete_button = None
        if problem:
            self.delete_button = ttk.Button(footer, text=tr('删除题目'), style="Danger.TButton",
                                            command=lambda: app.run(self.delete_problem))
            self.delete_button.pack(side="left")
        label(footer, tr('Ctrl + Enter 保存'), size=9, color=MUTED).pack(
            side="left", padx=px((10 if problem else 0, 0)))
        self.bind("<Control-Return>", lambda event: app.run(self.save))
        self.bind("<Escape>", lambda event: self.destroy())
        self._focus_job = self.after(100, self.title_entry.focus_set)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def destroy(self):
        if getattr(self, "_focus_job", None):
            try:
                self.after_cancel(self._focus_job)
            except tk.TclError:
                pass
            self._focus_job = None
        super().destroy()

    def save(self):
        title, learned = self.title_var.get().strip(), self.day_var.get().strip()
        parse_day(learned)
        for existing in self.app.store.all():
            if existing["title"].casefold() == title.casefold() and (
                    not self.problem or existing["id"] != self.problem["id"]):
                if not messagebox.askyesno(tr('已有同名题目'), tr('列表中已有同名题目，仍然保存这一条吗？'),
                                          parent=self, default="no"):
                    return
                break
        values = (title, learned, self.notes.get("1.0", "end-1c"), self.url_var.get())
        if self.problem:
            pid = self.problem["id"]
            self.app.store.edit(pid, *values)
        else:
            pid = self.app.store.add(*values)
        self.app.page, self.app.scope = "all", "active"
        if self.problem and self.problem["archived"]:
            self.app.scope = "archived"
        self.app.search_var.set("")
        self.app.selected_id = pid
        self.app.after_change(tr('题目已保存。'))
        self.destroy()

    def delete_problem(self):
        if not self.problem:
            return
        problem = self.app.store.get(self.problem["id"])
        if not messagebox.askyesno(
                tr('确认删除题目'),
                tr('是否要删除题目「{v0}」？\n\n将同时删除该题的文字备注及全部复习记录。\n该操作无法恢复。\n\n确定删除吗？', v0=problem['title']),
                parent=self, icon="warning", default="no"):
            return
        self.app.store.delete(problem["id"])
        self.app.selected_id = None
        self.app.after_change(tr('已删除题目「{v0}」。', v0=problem['title'][:24]))
        self.destroy()


class BackupDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title(tr('备份与恢复'))
        self.geometry(f"{px(650)}x{px(540)}")
        self.minsize(px(600), px(520))
        self.configure(bg=WHITE)
        self.transient(app.root)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        body = tk.Frame(self, bg=WHITE)
        body.pack(fill="both", expand=True, padx=px(30), pady=px(26))
        label(body, tr('让题目和记录一起保存'), 17, bold=True).pack(anchor="w")
        label(body, tr('备份包含全部题目、备注、复习进度和历史。'), color=MUTED).pack(anchor="w", pady=px((7, 20)))
        export = tk.Frame(body, bg=BG, padx=px(16), pady=px(14))
        export.pack(fill="x")
        label(export, tr('导出备份'), 11, bold=True, bg=BG).pack(anchor="w")
        label(export, tr('保存为 JSON 文件，可复制到其他位置留存。'), color=MUTED, bg=BG).pack(anchor="w", pady=px(5))
        ttk.Button(export, text=tr('导出备份…'), command=lambda: app.run(self.export)).pack(anchor="w", pady=px((6, 0)))
        restore = tk.Frame(body, bg=BG, padx=px(16), pady=px(14))
        restore.pack(fill="x", pady=px((12, 0)))
        label(restore, tr('恢复备份'), 11, bold=True, bg=BG).pack(anchor="w")
        label(restore, tr('恢复会替换当前数据；替换前会自动保留一份备份。'),
              color=MUTED, bg=BG).pack(anchor="w", pady=px(5))
        ttk.Button(restore, text=tr('选择备份并恢复…'), command=lambda: app.run(self.restore)).pack(anchor="w", pady=px((6, 0)))
        label(body, tr('程序每天自动保留当天快照，完成操作后同步更新。'), size=9,
              color=MUTED).pack(anchor="w", pady=px((18, 8)))
        ttk.Button(body, text=tr('打开自动备份文件夹'), command=lambda: app.run(self.open_folder)).pack(anchor="w")
        self.bind("<Escape>", lambda event: self.destroy())

    def export(self):
        target = filedialog.asksaveasfilename(
            parent=self, title=tr('导出复习备份'), defaultextension=".json",
            initialfile=tr('题目复习备份_{v0}.json', v0=self.app.store.today().isoformat()),
            filetypes=[(tr('复习备份'), "*.json")])
        if target:
            self.app.store.export_file(Path(target))
            messagebox.showinfo(tr('备份已导出'), tr('已保存到：\n{v0}', v0=target), parent=self)

    def restore(self):
        source = filedialog.askopenfilename(
            parent=self, title=tr('选择复习备份'), filetypes=[(tr('复习备份'), "*.json")])
        if not source:
            return
        document = self.app.store.read_backup(Path(source))
        count = len(document["problems"])
        active = sum(1 for review in document["reviews"] if review["undone_at"] is None)
        if not messagebox.askyesno(
                tr('确认恢复备份'),
                tr('备份中有 {v0} 道题、{v1} 次有效复习。\n\n恢复后会替换当前全部题目与进度。\n当前数据会先保存在自动备份文件夹中。\n\n确定恢复吗？', v0=count, v1=active),
                parent=self, default="no"):
            return
        snapshot = self.app.store.restore_document(document)
        self.app.selected_id = None
        self.app.after_change(tr('备份已恢复。'))
        messagebox.showinfo(tr('恢复完成'), tr('题目和复习进度已恢复。\n\n恢复前的数据保存在：\n{v0}', v0=snapshot), parent=self)

    def open_folder(self):
        folder = self.app.store.data_dir / "backups"
        folder.mkdir(exist_ok=True)
        os.startfile(str(folder))


class ReviewApp:
    def __init__(self, root, store, language=None):
        global UI_SCALE
        self.root, self.store = root, store
        set_language(language or preferred_language(store.data_dir))
        # Tk already renders point-sized fonts at the current display DPI.
        # Scale pixel-based geometry by the same factor, without bitmap stretching.
        UI_SCALE = max(0.75, root.winfo_fpixels("1i") / 96.0)
        self.ui_scale = UI_SCALE
        self.page, self.scope = "today", "pending"
        self.selected_id = None
        self.visible_rows = {}
        self._search_job = None
        self._last_day = store.today()
        self._seen_version = -1
        self._compact = None
        self._detail_problem_id = None
        self.detail_view = "notes"
        self.root.title(tr('题目复习助手'))
        self.root.configure(bg=BG)
        logging.info("Display: screen=%sx%s, dpi=%s, tk_scaling=%s",
                     root.winfo_screenwidth(), root.winfo_screenheight(),
                     root.winfo_fpixels("1i"), root.tk.call("tk", "scaling"))
        width = min(px(1220), root.winfo_screenwidth() - px(60))
        height = min(px(820), root.winfo_screenheight() - px(90))
        self.root.geometry(f"{width}x{height}+{max(0, (root.winfo_screenwidth()-width)//2)}+"
                           f"{max(0, (root.winfo_screenheight()-height)//2-px(20))}")
        self.root.minsize(min(px(1050), width), min(px(690), height))
        self.setup_styles()
        self.build_sidebar()
        self.build_main()
        self.search_var.trace_add("write", self.schedule_search)
        self.root.bind("<Control-n>", lambda event: self.new_problem())
        self.root.bind("<F5>", lambda event: self.run(self.refresh))
        self.root.bind("<Control-f>", lambda event: self.search_entry.focus_set())
        self.root.bind("<Configure>", self.responsive_layout)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.report_callback_exception = self.callback_error
        self.refresh()
        self.safe_snapshot()
        self.root.after(30_000, self.check_clock)

    def setup_styles(self):
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            tkfont.nametofont(name).configure(family=FONT, size=10)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=(FONT, 10), background=BG, foreground=INK)
        style.configure("TButton", padding=px((13, 9)), background=WHITE, bordercolor="#ABB7CA",
                        lightcolor="#ABB7CA", darkcolor="#ABB7CA", borderwidth=px(1),
                        relief="solid", focuscolor=BLUE)
        style.map("TButton", background=[("active", "#EAF0FA"), ("disabled", "#EEF1F6")],
                  foreground=[("disabled", "#8E99AB")],
                  bordercolor=[("disabled", "#C5CDDA"), ("active", "#7F96C4")])
        style.configure("Primary.TButton", foreground=WHITE, background=BLUE, bordercolor=BLUE,
                        lightcolor=BLUE, darkcolor=BLUE, padding=px((18, 10)))
        style.map("Primary.TButton", background=[("active", "#244AB8"), ("disabled", "#DDE3EF")],
                  foreground=[("disabled", "#7F8CA4")])
        style.configure("Small.TButton", padding=px((9, 5)), font=(FONT, 9))
        style.configure("Outline.TButton", padding=px((10, 7)), font=(FONT, 9),
                        borderwidth=px(1), relief="solid")
        style.configure("Danger.TButton", foreground="#B42318", background=WHITE,
                        bordercolor="#C84B43", lightcolor="#C84B43", darkcolor="#C84B43",
                        borderwidth=px(1), relief="solid")
        style.map("Danger.TButton", background=[("active", "#FFF0EE"), ("disabled", "#EEF1F6")],
                  foreground=[("disabled", "#8E99AB")],
                  bordercolor=[("disabled", "#C5CDDA"), ("active", "#B42318")])
        style.configure("TEntry", fieldbackground=WHITE, bordercolor=LINE, lightcolor=LINE,
                        darkcolor=LINE, padding=px(7), insertcolor=INK)
        style.map("TEntry", bordercolor=[("focus", BLUE)])
        style.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK,
                        rowheight=px(43), borderwidth=px(0), font=(FONT, 10))
        style.map("Treeview", background=[("selected", PALE)], foreground=[("selected", INK)])
        style.configure("Treeview.Heading", font=(FONT, 9), background="#F8F9FC", foreground=MUTED,
                        padding=px((8, 11)), borderwidth=px(0), relief="flat")
        style.map("Treeview.Heading", background=[("active", "#F1F4F9")])
        style.configure("History.Treeview", rowheight=px(32), font=(FONT, 9))
        style.configure("Vertical.TScrollbar", background="#D4DBE8", troughcolor=WHITE,
                        borderwidth=px(0), arrowsize=px(12))

    def build_sidebar(self):
        self.sidebar = sidebar = tk.Frame(self.root, bg=WHITE, width=px(190))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=WHITE)
        brand.pack(fill="x", padx=px(22), pady=px((31, 32)))
        label(brand, tr('题目复习'), 19, bold=True).pack(anchor="w")
        label(brand, tr('让学过的题，记得更久'), 9, color=MUTED).pack(anchor="w", pady=px((8, 0)))
        self.nav_buttons = {}
        for key, title in (("today", tr('今日复习')), ("all", tr('全部题目'))):
            button = tk.Button(sidebar, text=title, font=(FONT, 11), anchor="w",
                               padx=px(18), pady=px(13), bd=px(0), relief="flat", fg=INK,
                               bg=WHITE, activebackground=PALE, activeforeground=BLUE,
                               cursor="hand2", command=lambda page=key: self.set_page(page))
            button.pack(fill="x", padx=px(14), pady=px(3))
            self.nav_buttons[key] = button
        tk.Frame(sidebar, bg=LINE, height=px(1)).pack(fill="x", padx=px(25), pady=px(22))
        for title, command in ((tr('备份与恢复'), lambda: BackupDialog(self)),
                               (tr('复习规则'), self.show_rules)):
            tk.Button(sidebar, text=title, font=(FONT, 10), anchor="w", padx=px(18), pady=px(12),
                      bg=WHITE, fg=MUTED, activebackground=BG, bd=px(0), cursor="hand2",
                      command=lambda action=command: self.run(action)).pack(fill="x", padx=px(14), pady=px(2))
        bottom = tk.Frame(sidebar, bg=WHITE)
        bottom.pack(side="bottom", fill="x", padx=px(25), pady=px(25))
        label(bottom, tr('●  本机保存'), 9, color=GREEN).pack(anchor="w")
        label(bottom, tr('离线可用 · 数据随时备份'), 8, color=MUTED).pack(anchor="w", pady=px((6, 0)))
        label(bottom, tr('语言 / Language'), 9, color=MUTED).pack(anchor="w", pady=px((20, 7)))
        self.language_var = tk.StringVar(value=LANGUAGES[get_language()])
        self.language_picker = ttk.Combobox(bottom, state="readonly", textvariable=self.language_var,
                                            values=list(LANGUAGES.values()), width=16)
        self.language_picker.pack(fill="x")
        self.language_picker.bind("<<ComboboxSelected>>", lambda event: self.run(
            lambda: self.change_language(next(key for key, value in LANGUAGES.items()
                                              if value == self.language_var.get()))))

    def build_main(self):
        self.main = main = tk.Frame(self.root, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=px(24), pady=px((25, 15)))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        header = tk.Frame(main, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=px((0, 20)))
        self.heading = label(header, tr('今日复习'), 22, bold=True, bg=BG)
        self.heading.pack(anchor="w")
        self.date_label = label(header, "", 9, color=MUTED, bg=BG)
        self.date_label.pack(anchor="w", pady=px((6, 0)))
        ttk.Button(header, text=tr('＋  新增题目'), style="Primary.TButton",
                   command=self.new_problem).place(relx=1.0, rely=0.0, anchor="ne")
        stats = tk.Frame(main, bg=BG)
        self.stats_frame = stats
        stats.grid(row=1, column=0, sticky="ew", pady=px((0, 18)))
        self.stat_values = {}
        for i, (key, title, color) in enumerate((
                ("due", tr('待复习'), BLUE), ("overdue", tr('其中逾期'), AMBER),
                ("done", tr('今日已学习'), GREEN), ("active", tr('进行中题目'), INK))):
            stats.columnconfigure(i, weight=1, uniform="stat")
            card = tk.Frame(stats, bg=WHITE, highlightthickness=px(1), highlightbackground=LINE)
            card.grid(row=0, column=i, sticky="ew", padx=px((0 if i == 0 else 5, 0 if i == 3 else 5)))
            label(card, title, 9, color=MUTED).pack(anchor="w", padx=px(16), pady=px((12, 3)))
            value = label(card, "0", 23, color=color, bold=True)
            value.pack(anchor="w", padx=px(16), pady=px((0, 10)))
            self.stat_values[key] = value
        toolbar = tk.Frame(main, bg=BG)
        toolbar.grid(row=2, column=0, sticky="ew", pady=px((0, 12)))
        self.scope_buttons = []
        for i in range(2):
            button = tk.Button(toolbar, text="", font=(FONT, 10), padx=px(14), pady=px(8),
                               bd=px(0), cursor="hand2", bg=BG, activebackground=PALE,
                               command=lambda index=i: self.set_scope(index))
            button.pack(side="left", padx=px((0, 5)))
            self.scope_buttons.append(button)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=23)
        self.search_entry.pack(side="right")
        label(toolbar, tr('搜索'), 9, color=MUTED, bg=BG).pack(side="right", padx=px((8, 8)))
        area = tk.Frame(main, bg=BG)
        area.grid(row=3, column=0, sticky="nsew")
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        area.columnconfigure(1, minsize=px(320))
        self.list_card = tk.Frame(area, bg=WHITE, highlightthickness=px(1), highlightbackground=LINE)
        self.list_card.grid(row=0, column=0, sticky="nsew", padx=px((0, 14)))
        self.list_card.rowconfigure(0, weight=1)
        self.list_card.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(self.list_card, columns=("title", "status", "next"), show="headings",
                                 selectmode="browse")
        for key, title, width, minimum, stretch in (
                ("title", tr('题目'), 230, 125, True), ("status", tr('学习状态'), 120, 100, False),
                ("next", tr('下次复习'), 110, 102, False)):
            self.tree.heading(key, text=title, anchor="w")
            self.tree.column(key, width=px(width), minwidth=px(minimum), stretch=stretch, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=px((7, 0)), pady=px(7))
        self.list_scrollbar = scroll = RoundedScrollbar(self.list_card, command=self.tree.yview,
                                                        scale=UI_SCALE)
        scroll.grid(row=0, column=1, sticky="ns", pady=px(7))
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure("overdue", foreground=AMBER)
        self.tree.bind("<<TreeviewSelect>>", self.select_row)
        self.tree.bind("<Double-1>", lambda event: self.run(self.edit_selected))
        self.empty_box = tk.Frame(self.list_card, bg=WHITE)
        self.empty_title = label(self.empty_box, "", 13, bold=True)
        self.empty_title.pack()
        self.empty_hint = label(self.empty_box, "", 10, color=MUTED, wraplength=px(350), justify="center")
        self.empty_hint.pack(pady=px((10, 16)))
        self.empty_button = ttk.Button(self.empty_box, text=tr('＋ 新增第一道题'), command=self.new_problem)
        self.empty_button.pack()
        self.detail = tk.Frame(area, bg=WHITE, width=px(320), highlightthickness=px(1), highlightbackground=LINE)
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.detail.grid_propagate(False)
        self.detail.columnconfigure(0, weight=1)
        self.detail.rowconfigure(2, weight=1)
        self.build_detail()
        footer = tk.Frame(main, bg=BG)
        footer.grid(row=4, column=0, sticky="ew", pady=px((12, 0)))
        self.status_label = label(footer, tr('数据自动保存在本机'), 9, color=MUTED, bg=BG, anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        label(footer, tr('F5 刷新'), 9, color=MUTED, bg=BG).pack(side="right")

    def build_detail(self):
        top = tk.Frame(self.detail, bg=WHITE)
        top.grid(row=0, column=0, sticky="ew", padx=px(18), pady=px((18, 12)))
        self.detail_title = tk.Text(top, height=2, wrap="word", font=(FONT, 11, "bold"),
                                   bg=WHITE, fg=INK, bd=px(0), highlightthickness=px(0), cursor="arrow",
                                   padx=px(0), pady=px(0), width=1, state="disabled")
        self.detail_title.pack(fill="x", pady=px((0, 10)))
        controls = tk.Frame(top, bg=WHITE)
        controls.pack(fill="x")
        for column in range(3):
            controls.columnconfigure(column, weight=1, uniform="detail-actions")
        self.edit_button = ttk.Button(controls, text=tr('编辑题目'), style="Outline.TButton",
                                     command=lambda: self.run(self.edit_selected))
        self.edit_button.grid(row=0, column=0, sticky="ew", padx=px((0, 4)))
        self.link_button = ttk.Button(controls, text=tr('打开原题'), style="Outline.TButton",
                                     command=lambda: self.run(self.open_link))
        self.link_button.grid(row=0, column=1, sticky="ew", padx=px(4))
        self.archive_button = ttk.Button(controls, text=tr('归档'), style="Outline.TButton",
                                        command=lambda: self.run(self.archive_selected))
        self.archive_button.grid(row=0, column=2, sticky="ew", padx=px((4, 0)))
        meta = tk.Frame(self.detail, bg=WHITE)
        meta.grid(row=1, column=0, sticky="ew", padx=px(18), pady=px((0, 13)))
        meta.columnconfigure(1, weight=1)
        self.meta_values = {}
        for row, (key, title) in enumerate((("learned", tr('初次学习')), ("count", tr('已复习')),
                                            ("next", tr('下次复习')))):
            label(meta, title, 9, color=MUTED).grid(row=row, column=0, sticky="w", pady=px(3))
            value = label(meta, "", 9, color=BLUE if key == "next" else INK)
            value.grid(row=row, column=1, sticky="e", pady=px(3))
            self.meta_values[key] = value
        self.detail_content = tk.Frame(self.detail, bg=WHITE)
        self.detail_content.grid(row=2, column=0, sticky="nsew", padx=px(17))
        self.detail_content.columnconfigure(0, weight=1)
        self.detail_content.rowconfigure(1, weight=1)
        content_header = tk.Frame(self.detail_content, bg=WHITE)
        content_header.grid(row=0, column=0, sticky="ew", pady=px((0, 10)))
        content_header.columnconfigure(0, weight=1)
        self.content_heading = label(content_header, tr('文字备注'), 11, bold=True)
        self.content_heading.grid(row=0, column=0, sticky="w")
        self.view_switch_button = ttk.Button(content_header, text=tr('查看复习记录'),
                                              style="Outline.TButton", width=16,
                                              command=self.toggle_detail_view)
        self.view_switch_button.grid(row=0, column=1, sticky="e", padx=px((8, 0)))
        self.content_body = tk.Frame(self.detail_content, bg=WHITE,
                                     highlightthickness=px(1), highlightbackground=LINE)
        self.content_body.grid(row=1, column=0, sticky="nsew")
        self.content_body.grid_propagate(False)
        self.content_body.columnconfigure(0, weight=1)
        self.content_body.rowconfigure(0, weight=1)
        self.notes_frame = notes_frame = tk.Frame(self.content_body, bg=WHITE)
        self.history_frame = history_frame = tk.Frame(self.content_body, bg=WHITE)
        notes_frame.grid(row=0, column=0, sticky="nsew")
        history_frame.grid(row=0, column=0, sticky="nsew")
        self.note_text = tk.Text(notes_frame, wrap="word", font=(FONT, 10), state="disabled",
                                 bg=WHITE, fg=INK, relief="flat", highlightthickness=px(0),
                                 padx=px(7), pady=px(10), height=4, width=1)
        notes_scroll = RoundedScrollbar(notes_frame, command=self.note_text.yview, scale=UI_SCALE)
        self.note_text.configure(yscrollcommand=notes_scroll.set)
        notes_scroll.pack(side="right", fill="y")
        self.note_text.pack(side="left", fill="both", expand=True)
        self.history_tree = ttk.Treeview(history_frame, columns=("date", "next", "state"),
                                         show="headings", height=3, style="History.Treeview")
        for key, text, width in (("date", tr('学习日期'), 91), ("next", tr('安排下次'), 91), ("state", tr('状态'), 60)):
            self.history_tree.heading(key, text=text, anchor="w")
            self.history_tree.column(key, width=px(width), minwidth=px(50), stretch=True)
        history_scroll = RoundedScrollbar(history_frame, command=self.history_tree.yview, scale=UI_SCALE)
        self.history_tree.configure(yscrollcommand=history_scroll.set)
        history_scroll.pack(side="right", fill="y")
        self.history_tree.pack(side="left", fill="both", expand=True)
        self.set_detail_view("notes")
        bottom = tk.Frame(self.detail, bg=WHITE)
        bottom.grid(row=3, column=0, sticky="ew", padx=px(18), pady=px((13, 18)))
        self.detail_status = label(bottom, "", 9, color=MUTED)
        self.detail_status.pack(anchor="w", pady=px((0, 9)))
        self.complete_button = ttk.Button(bottom, text=tr('已重新学习，安排下次'), style="Primary.TButton",
                                         command=lambda: self.run(self.complete_selected))
        self.complete_button.pack(fill="x")
        self.undo_button = ttk.Button(bottom, text=tr('撤销今日完成'), style="Small.TButton",
                                     command=lambda: self.run(self.undo_selected))
        self.undo_button.pack(fill="x", pady=px((8, 0)))
        self.detail_empty = tk.Frame(self.detail, bg=WHITE)
        label(self.detail_empty, tr('选择一道题'), 12, bold=True).place(relx=.5, rely=.44, anchor="center")
        label(self.detail_empty, tr('在左侧查看题目和复习安排'), 9, color=MUTED).place(
            relx=.5, rely=.51, anchor="center")

    def responsive_layout(self, event):
        if event.widget is not self.root:
            return
        compact = event.height < px(780)
        if compact != self._compact:
            self._compact = compact
            if compact:
                self.stats_frame.grid_remove()
            else:
                self.stats_frame.grid()

    def set_detail_view(self, view):
        self.detail_view = view
        showing_notes = view == "notes"
        self.content_heading.configure(text=tr('文字备注') if showing_notes else tr('复习记录'))
        self.view_switch_button.configure(text=tr('查看复习记录') if showing_notes else tr('返回文字备注'))
        if showing_notes:
            self.history_frame.grid_remove()
            self.notes_frame.grid()
        else:
            self.notes_frame.grid_remove()
            self.history_frame.grid()

    def change_language(self, language):
        if language == get_language():
            return
        if self.root.grab_current():
            return
        atomic_json(self.store.data_dir / "settings.json", {"language": language})
        query, view = self.search_var.get(), self.detail_view
        if self._search_job:
            self.root.after_cancel(self._search_job)
            self._search_job = None
        self.sidebar.destroy()
        self.main.destroy()
        set_language(language)
        self.root.title(tr("题目复习助手"))
        self._detail_problem_id = None
        self.build_sidebar()
        self.build_main()
        if self._compact:
            self.stats_frame.grid_remove()
        self.search_var.set(query)
        self.search_var.trace_add("write", self.schedule_search)
        self.refresh()
        if self.selected_id:
            self.set_detail_view(view)

    def toggle_detail_view(self):
        self.set_detail_view("history" if self.detail_view == "notes" else "notes")

    def run(self, action):
        try:
            return action()
        except (ReviewError, OSError, sqlite3.Error) as error:
            logging.exception("Operation failed")
            parent = self.root.grab_current() or self.root
            messagebox.showerror(tr('操作未完成'), str(error), parent=parent)

    def callback_error(self, exception, value, traceback):
        logging.error("Unhandled UI error", exc_info=(exception, value, traceback))
        messagebox.showerror(tr('操作未完成'), tr('请重试；详细信息已保存在本地日志。\n\n{v0}', v0=value), parent=self.root)

    def schedule_search(self, *args):
        if self._search_job:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(150, self.search_refresh)

    def search_refresh(self):
        self._search_job = None
        self.run(self.refresh)

    def set_page(self, page):
        self.page = page
        self.scope = "pending" if page == "today" else "active"
        self.search_var.set("")
        self.run(self.refresh)

    def set_scope(self, index):
        self.scope = (("pending", "done") if self.page == "today" else ("active", "archived"))[index]
        self.run(self.refresh)

    def status_for(self, problem, today):
        if problem["archived"]:
            return tr('已归档')
        if problem["last_review_on"] == today.isoformat():
            return tr('今日已学习')
        due = parse_day(problem["next_review_on"])
        if due < today:
            return tr('逾期 {v0} 天', v0=(today - due).days)
        if due == today:
            return tr('今天尚未学习')
        return tr('等待下次复习')

    def refresh(self):
        today = self.store.today()
        self._last_day = today
        self._seen_version = self.store.db.execute("PRAGMA data_version").fetchone()[0]
        if get_language() == "en":
            weekday = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[today.weekday()]
            self.date_label.configure(text=f"{today.isoformat()}  ·  {weekday}  ·  UTC+08:00")
        else:
            weekday = ("一", "二", "三", "四", "五", "六", "日")[today.weekday()]
            self.date_label.configure(text=tr('{v0} 年 {v1} 月 {v2} 日  ·  星期{v3}  ·  北京时间', v0=today.year, v1=today.month, v2=today.day, v3=weekday))
        self.heading.configure(text=tr('今日复习') if self.page == "today" else tr('全部题目'))
        summary = self.store.summary()
        for key, value in self.stat_values.items():
            value.configure(text=str(summary[key]))
        for key, button in self.nav_buttons.items():
            selected = key == self.page
            button.configure(bg=PALE if selected else WHITE, fg=BLUE if selected else MUTED,
                             font=(FONT, 11, "bold" if selected else "normal"))
        scopes = (("pending", tr('待学习')), ("done", tr('今日已学习'))) if self.page == "today" else (
            ("active", tr('进行中')), ("archived", tr('已归档')))
        for button, (key, title) in zip(self.scope_buttons, scopes):
            button.configure(text=title, bg=WHITE if key == self.scope else BG,
                             fg=BLUE if key == self.scope else MUTED)
        problems = self.store.all()
        day = today.isoformat()
        if self.page == "today" and self.scope == "done":
            ids = {row[0] for row in self.store.db.execute(
                "SELECT problem_id FROM reviews WHERE reviewed_on = ? AND undone_at IS NULL", (day,))}
            rows = [problem for problem in problems if problem["id"] in ids]
        elif self.page == "today":
            rows = [problem for problem in problems if not problem["archived"] and problem["next_review_on"] <= day]
        else:
            rows = [problem for problem in problems if bool(problem["archived"]) == (self.scope == "archived")]
        query = self.search_var.get().strip().casefold()
        if query:
            rows = [problem for problem in rows if query in "\n".join(
                (problem["title"], problem["notes"], problem["url"])).casefold()]
        old_selection = self.selected_id
        self.tree.delete(*self.tree.get_children())
        self.visible_rows = {problem["id"]: problem for problem in rows}
        for problem in rows:
            overdue = not problem["archived"] and problem["next_review_on"] < day
            self.tree.insert("", "end", iid=problem["id"],
                             values=(problem["title"], self.status_for(problem, today), problem["next_review_on"]),
                             tags=("overdue",) if overdue else ())
        if rows:
            self.empty_box.place_forget()
            self.selected_id = old_selection if old_selection in self.visible_rows else rows[0]["id"]
            self.tree.selection_set(self.selected_id)
            self.tree.see(self.selected_id)
        else:
            self.selected_id = None
            if query:
                title, hint = tr('没有找到匹配的题目'), tr('试试题目名称、链接或备注中的其他词。')
            elif not problems:
                title, hint = tr('从一道题开始'), tr('记下已经看懂题解的题目，\n下次打开时就能查看复习安排。')
            elif self.page == "all":
                title = tr('还没有归档题目') if self.scope == "archived" else tr('还没有进行中的题目')
                hint = tr('归档会保留题目和记录，随时可以恢复。') if self.scope == "archived" else tr('可以新增题目，或从已归档列表恢复。')
            elif self.scope == "done":
                title, hint = tr('今天还没有完成记录'), tr('在“待学习”中学完一道题，再标记完成。')
            else:
                title = tr('今天的复习已完成') if summary["done"] else tr('今天暂无到期题目')
                upcoming = [problem["next_review_on"] for problem in problems
                            if not problem["archived"] and problem["next_review_on"] > day]
                hint = tr('下次复习：{v0}\n也可以继续记录新题。', v0=min(upcoming)) if upcoming else tr('可以继续记录新题，或查看全部题目。')
            self.empty_title.configure(text=title)
            self.empty_hint.configure(text=hint)
            if not problems:
                self.empty_button.pack()
            else:
                self.empty_button.pack_forget()
            self.empty_box.place(relx=.5, rely=.48, anchor="center")
            self.empty_box.lift()
        self.show_detail()

    def select_row(self, event=None):
        selection = self.tree.selection()
        if selection:
            self.selected_id = selection[0]
            self.run(self.show_detail)

    @staticmethod
    def replace_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def show_detail(self):
        if not self.selected_id or self.selected_id not in self.visible_rows:
            self._detail_problem_id = None
            self.detail_empty.place(x=px(0), y=px(0), relwidth=1, relheight=1)
            self.detail_empty.lift()
            return
        self.detail_empty.place_forget()
        if self._detail_problem_id != self.selected_id:
            self._detail_problem_id = self.selected_id
            self.set_detail_view("notes")
        problem = self.store.get(self.selected_id)
        today = self.store.today().isoformat()
        self.replace_text(self.detail_title, problem["title"])
        self.replace_text(self.note_text, problem["notes"] or tr('还没有备注。点击“编辑题目”记录思路或易错点。'))
        for key, value in (("learned", problem["learned_on"]), ("count", tr('{v0} 次', v0=problem['completed_count'])),
                           ("next", problem["next_review_on"])):
            self.meta_values[key].configure(text=value)
        self.link_button.configure(state="normal" if problem["url"] else "disabled")
        self.archive_button.configure(text=tr('恢复') if problem["archived"] else tr('归档'))
        completed_today = problem["last_review_on"] == today
        due = not problem["archived"] and problem["next_review_on"] <= today
        self.complete_button.configure(state="normal" if due and not completed_today else "disabled")
        self.undo_button.configure(state="normal" if completed_today else "disabled")
        self.complete_button.pack_forget()
        self.undo_button.pack_forget()
        if due and not completed_today:
            self.complete_button.pack(fill="x")
        if completed_today:
            self.undo_button.pack(fill="x")
        self.detail_status.configure(text=self.status_for(problem, self.store.today()),
                                     fg=GREEN if completed_today else MUTED)
        self.history_tree.delete(*self.history_tree.get_children())
        for review in self.store.history(problem["id"]):
            self.history_tree.insert("", "end", values=(review["reviewed_on"], review["next_on"],
                                                       tr('已撤销') if review["undone_at"] else tr('已学习')))

    def new_problem(self):
        self.run(lambda: ProblemForm(self))

    def selected(self):
        if not self.selected_id:
            raise ReviewError(tr('请先选择一道题。'))
        return self.store.get(self.selected_id)

    def edit_selected(self):
        ProblemForm(self, self.selected())

    def open_link(self):
        url = self.selected()["url"]
        if url:
            webbrowser.open(url, new=2)

    def archive_selected(self):
        problem = self.selected()
        self.store.set_archived(problem["id"], not problem["archived"])
        self.after_change(tr('题目已恢复，原来的复习安排继续保留。') if problem["archived"]
                          else tr('题目已归档，题目和历史仍然保留。'))

    def complete_selected(self):
        problem = self.selected()
        changed = self.store.complete(problem["id"])
        next_on = self.store.get(problem["id"])["next_review_on"]
        self.after_change(tr('已学习「{v0}」 · 下次复习 {v1}', v0=problem['title'][:24], v1=next_on) if changed
                          else tr('这道题今天已经记录过，复习进度没有重复推进。'))

    def undo_selected(self):
        problem = self.selected()
        self.store.undo_today(problem["id"])
        self.after_change(tr('已撤销今日完成，恢复原来的复习安排。'))

    def safe_snapshot(self):
        try:
            self.store.automatic_backup()
            return True
        except (OSError, sqlite3.Error):
            logging.exception("Automatic backup failed")
            self.status_label.configure(text=tr('题目已保存；自动备份未成功，可到“备份与恢复”手动导出。'), fg=AMBER)
            return False

    def after_change(self, message):
        self.refresh()
        if self.safe_snapshot():
            self.status_label.configure(text=message, fg=GREEN)

    def show_rules(self):
        messagebox.showinfo(
            tr('复习规则'),
            tr('按北京时间的自然日安排复习。\n\n首次学习后 1 天复习；每完成一轮，下一次间隔依次为：\n3 天 → 7 天 → 14 天 → 30 天 → 60 天。\n到达最后一档后，保持每 60 天复习一次。\n\n间隔从实际完成日期计算。尚未学习就继续保留，\n不会自动跳过，也不会把逾期的同一道题重复列出。\n\n当天完成只计一次；点错可在当天撤销。\n归档会暂停提醒，恢复后沿用原来的复习日期。\n\n这些天数是基于间隔学习原则的初始设置，\n并不是对每个人都最优的固定记忆曲线。'),
            parent=self.root)

    def check_clock(self):
        try:
            version = self.store.db.execute("PRAGMA data_version").fetchone()[0]
            if self.store.today() != self._last_day or version != self._seen_version:
                self.refresh()
                self.safe_snapshot()
        except (OSError, sqlite3.Error):
            logging.exception("Refresh failed")
        finally:
            self.root.after(30_000, self.check_clock)

    def close(self):
        self.safe_snapshot()
        for job in self.root.tk.call("after", "info"):
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self.store.close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=tr('Problem Review / 题目复习助手'))
    parser.add_argument("--data-dir", type=Path, default=APP_DIR / "data", help=tr('本地数据保存目录'))
    parser.add_argument("--language", choices=list(LANGUAGES), help="UI language: en or zh-CN")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(args.data_dir / "app.log", maxBytes=1_000_000,
                                  backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(message)s")
    set_language(args.language or preferred_language(args.data_dir))
    enable_dpi_awareness()
    root = None
    store = None
    try:
        store = Store(args.data_dir)
        root = tk.Tk()
        ReviewApp(root, store, language=get_language())
        root.mainloop()
    except Exception as error:
        logging.exception("Startup or application failure")
        if root is None:
            root = tk.Tk()
            root.withdraw()
        messagebox.showerror(tr('程序未能启动'), tr('请查看数据目录中的 app.log。\n\n{v0}', v0=error), parent=root)
        if store:
            store.close()
        root.destroy()


if __name__ == "__main__":
    main()
