"""Class Attendance - graphical app.      Run:  python app.py   (or double-click run_app.bat)"""
import csv
import datetime as dt
import json
import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from attendance_ai.utils import read_image

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)          # database, captures, college_api.json all live in this folder

FONT = "Segoe UI"
PURPLE, BG, WHITE = "#5b2be0", "#e5e7eb", "#ffffff"
GREEN, ORANGE, RED = "#16a34a", "#f59e0b", "#ef4444"
BLUE, VIOLET, MUTED = "#1e40af", "#7c3aed", "#6b7280"
IMG_TYPES = [("Images", "*.jpg *.jpeg *.png *.webp *.bmp"), ("All files", "*.*")]


def make_button(parent, text, cmd, bg=PURPLE, fg="white", **kw):
    return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, relief="flat",
                     activebackground=bg, activeforeground=fg, cursor="hand2",
                     font=(FONT, 10, "bold"), padx=14, pady=7, bd=0, **kw)


# ----------------------------------------------------------------------------------------
class StudentPicker(tk.Toplevel):
    """Popup: who is this face?  result = roll | '' (clear) | None (cancel)"""

    def __init__(self, parent, candidates, students):
        super().__init__(parent)
        self.title("Who is this?")
        self.geometry("360x480")
        self.transient(parent)
        self.configure(bg=WHITE)
        self.result = None
        self.students = students
        self.view = []
        tk.Label(self, text="Who is this student?", font=(FONT, 13, "bold"),
                 bg=WHITE).pack(anchor="w", padx=14, pady=(12, 4))
        names = {s.roll: s.name for s in students}
        guesses = [(r, s) for r, s in candidates if r in names]
        if guesses:
            tk.Label(self, text="Best guesses", fg=MUTED, bg=WHITE).pack(anchor="w", padx=14)
            for roll, sim in guesses:
                tk.Button(self, text=f"{names[roll]}   (Roll {roll}, match {sim:.2f})", anchor="w",
                          relief="flat", bg="#ede9fe", cursor="hand2",
                          command=lambda r=roll: self._done(r)).pack(fill="x", padx=14, pady=2)
        tk.Label(self, text="Or search all students", fg=MUTED, bg=WHITE).pack(
            anchor="w", padx=14, pady=(10, 0))
        self.q = tk.StringVar()
        e = tk.Entry(self, textvariable=self.q)
        e.pack(fill="x", padx=14, pady=4)
        e.focus_set()
        self.q.trace_add("write", lambda *a: self._fill())
        self.lb = tk.Listbox(self, exportselection=False, height=8)
        self.lb.pack(fill="both", expand=True, padx=14)
        self.lb.bind("<Double-Button-1>", lambda e: self._pick_list())
        row = tk.Frame(self, bg=WHITE)
        row.pack(fill="x", padx=14, pady=10)
        make_button(row, "Select", self._pick_list, GREEN).pack(side="left")
        make_button(row, "Not a student", lambda: self._done(""), "#9ca3af").pack(side="left", padx=6)
        make_button(row, "Cancel", lambda: self._done(None), "#9ca3af").pack(side="right")
        self._fill()
        self.grab_set()
        self.wait_window()

    def _fill(self):
        q = self.q.get().lower().strip()
        self.view = [s for s in self.students if q in s.name.lower() or q in s.roll.lower()]
        self.lb.delete(0, "end")
        for s in self.view:
            self.lb.insert("end", f"{s.name}   ({s.roll})")

    def _pick_list(self):
        sel = self.lb.curselection()
        if sel:
            self._done(self.view[sel[0]].roll)

    def _done(self, value):
        self.result = value
        self.destroy()


class AddStudentDialog(tk.Toplevel):
    """result = (roll, name, section, 'files'|'webcam') or None"""

    def __init__(self, parent, sections, default_section):
        super().__init__(parent)
        self.title("Add student")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=WHITE, padx=18, pady=14)
        self.result = None
        self.roll, self.name, self.sec = tk.StringVar(), tk.StringVar(), tk.StringVar(value=default_section)
        for i, (label, var) in enumerate([("Roll number", self.roll), ("Name", self.name)]):
            tk.Label(self, text=label, bg=WHITE).grid(row=i, column=0, sticky="w", pady=4)
            tk.Entry(self, textvariable=var, width=30).grid(row=i, column=1, pady=4, padx=8)
        tk.Label(self, text="Section / class", bg=WHITE).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(self, textvariable=self.sec, values=sections, width=28).grid(row=2, column=1, padx=8)
        tk.Label(self, text="Next: add 5-10 clear photos of the face (different angles).",
                 fg=MUTED, bg=WHITE).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
        bar = tk.Frame(self, bg=WHITE)
        bar.grid(row=4, column=0, columnspan=2, pady=6)
        make_button(bar, "Choose photo files", lambda: self._ok("files")).pack(side="left", padx=4)
        make_button(bar, "Use webcam", lambda: self._ok("webcam"), VIOLET).pack(side="left", padx=4)
        make_button(bar, "Cancel", self.destroy, "#9ca3af").pack(side="left", padx=4)
        self.grab_set()
        self.wait_window()

    def _ok(self, mode):
        roll, name, sec = self.roll.get().strip(), self.name.get().strip(), self.sec.get().strip()
        if not (roll and name and sec):
            messagebox.showwarning("Missing details", "Please fill roll number, name and section.", parent=self)
            return
        self.result = (roll, name, sec, mode)
        self.destroy()


# ----------------------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self, system_factory=None):
        super().__init__()
        self.title("Class Attendance")
        self.geometry("1320x820")
        self.minsize(1150, 720)
        self.configure(bg=BG)
        self.system = None
        self.result = None
        self.photo_idx = 0
        self.rows = {}
        self.cards = {}
        self._view = (0, 0, 1.0)
        self._tk_img = None
        self._pil_cache = {}
        self.q = queue.Queue()
        self.busy = 0
        self.section = tk.StringVar()
        self.date = tk.StringVar(value=dt.date.today().isoformat())
        self.search = tk.StringVar()
        self.status = tk.StringVar(value="Loading face model... (first time may take a minute)")
        self._factory = system_factory or self._default_factory
        self._style()
        self._build_header()
        self._build_tabs()
        self._build_status()
        self.section.trace_add("write", lambda *a: self._on_section())
        self.search.trace_add("write", lambda *a: self.apply_filter())
        self.after(100, self._poll)
        self.run_bg(self._factory, self._system_ready, self._fatal, "Loading face model...")

    # ---------- plumbing ----------
    @staticmethod
    def _default_factory():
        from attendance_ai.config import Config
        from attendance_ai.pipeline import AttendanceSystem
        return AttendanceSystem(Config())

    def run_bg(self, fn, ok=None, err=None, msg="Working..."):
        """Run fn in a thread so the window never freezes; callbacks run on the UI thread."""
        self.busy += 1
        self._busy_ui(msg)

        def work():
            try:
                self.q.put(("ok", ok, fn()))
            except Exception as e:                      # noqa
                traceback.print_exc()
                self.q.put(("err", err, e))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, cb, payload = self.q.get_nowait()
                self.busy -= 1
                if self.busy <= 0:
                    self.busy = 0
                    self._busy_ui(None)
                if kind == "ok" and cb:
                    cb(payload)
                elif kind == "err":
                    (cb or self._show_error)(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _busy_ui(self, msg):
        if msg:
            self.status.set(msg)
            self.progress.start(12)
        else:
            self.progress.stop()

    def _show_error(self, e):
        self.status.set("Error: " + str(e))
        messagebox.showerror("Something went wrong", str(e))

    def _fatal(self, e):
        self.status.set("Could not start the face model.")
        messagebox.showerror(
            "Face model failed to load",
            f"{e}\n\nRun  python check_setup.py  in the project folder to find the problem.")

    def _system_ready(self, system):
        self.system = system
        self.status.set("Ready")
        self.refresh_sections()
        self.refresh_students()
        self.draw_photo()

    def need_system(self):
        if self.system is None:
            messagebox.showinfo("Please wait", "The face model is still loading.")
            return False
        return True

    # ---------- layout ----------
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", font=(FONT, 11, "bold"), padding=(18, 8))
        st.map("TNotebook.Tab", background=[("selected", WHITE)], foreground=[("selected", PURPLE)])
        st.configure("Treeview", font=(FONT, 10), rowheight=28)
        st.configure("Treeview.Heading", font=(FONT, 10, "bold"))

    def _build_header(self):
        h = tk.Frame(self, bg=PURPLE)
        h.pack(fill="x")
        c = tk.Canvas(h, width=56, height=56, bg=PURPLE, highlightthickness=0)
        c.create_oval(4, 4, 52, 52, fill="white", outline="")
        c.create_line(17, 29, 25, 38, 40, 18, fill=PURPLE, width=5, capstyle="round", joinstyle="round")
        c.pack(side="left", padx=(16, 10), pady=12)
        t = tk.Frame(h, bg=PURPLE)
        t.pack(side="left")
        tk.Label(t, text="Class Attendance", font=(FONT, 20, "bold"), fg="white", bg=PURPLE).pack(anchor="w")
        tk.Label(t, text="Take attendance from a class photo in seconds", font=(FONT, 10),
                 fg="#ddd6fe", bg=PURPLE).pack(anchor="w")
        tk.Label(h, text=dt.date.today().strftime("%A, %d %B %Y"), font=(FONT, 12, "bold"),
                 fg="white", bg=PURPLE).pack(side="right", padx=20)

    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(10, 0))
        self.tab_take, self.tab_students, self.tab_report = (tk.Frame(nb, bg=BG) for _ in range(3))
        nb.add(self.tab_take, text="Take attendance")
        nb.add(self.tab_students, text="Students")
        nb.add(self.tab_report, text="Report")
        nb.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed(nb))
        self._build_take(self.tab_take)
        self._build_students(self.tab_students)
        self._build_report(self.tab_report)

    def _build_status(self):
        b = tk.Frame(self, bg="#f3f4f6")
        b.pack(fill="x", side="bottom")
        tk.Label(b, textvariable=self.status, bg="#f3f4f6", font=(FONT, 10), anchor="w").pack(
            side="left", padx=12, pady=4)
        self.progress = ttk.Progressbar(b, mode="indeterminate", length=140)
        self.progress.pack(side="right", padx=12)

    def _tab_changed(self, nb):
        if nb.index("current") == 2:
            self.refresh_report()
        elif nb.index("current") == 1:
            self.refresh_students()

    # ---------- tab 1: take attendance ----------
    def _build_take(self, tab):
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=4, pady=(10, 6))
        tk.Label(bar, text="Section", bg=BG, font=(FONT, 10)).pack(side="left")
        self.cb_take = ttk.Combobox(bar, textvariable=self.section, width=12, state="readonly")
        self.cb_take.pack(side="left", padx=(4, 12))
        make_button(bar, "<", lambda: self.shift_date(-1), WHITE, PURPLE).pack(side="left")
        tk.Entry(bar, textvariable=self.date, width=11, justify="center",
                 font=(FONT, 12, "bold"), relief="flat").pack(side="left", padx=4, ipady=6)
        make_button(bar, ">", lambda: self.shift_date(1), WHITE, PURPLE).pack(side="left")
        make_button(bar, "Choose class photo(s)", self.choose_photos).pack(side="left", padx=(14, 6))
        make_button(bar, "Use camera", self.use_camera, VIOLET).pack(side="left")
        make_button(bar, "Save attendance", self.save, GREEN).pack(side="right")
        make_button(bar, "Upload to college", self.upload, VIOLET).pack(side="right", padx=8)
        make_button(bar, "Export CSV", self.export_csv, WHITE, BLUE).pack(side="right")

        cards = tk.Frame(tab, bg=BG)
        cards.pack(fill="x", padx=4, pady=6)
        for key, cap, color in [("students", "STUDENTS", BLUE), ("present", "PRESENT", GREEN),
                                ("absent", "ABSENT", RED), ("check", "PLEASE CHECK", ORANGE),
                                ("pct", "TODAY %", VIOLET)]:
            f = tk.Frame(cards, bg=color, width=160, height=82)
            f.pack(side="left", padx=(0, 10))
            f.pack_propagate(False)
            v = tk.StringVar(value="0")
            self.cards[key] = v
            tk.Label(f, textvariable=v, font=(FONT, 26, "bold"), bg=color, fg="white").pack(
                anchor="w", padx=12, pady=(6, 0))
            tk.Label(f, text=cap, font=(FONT, 9, "bold"), bg=color, fg="white").pack(anchor="w", padx=12)

        main = tk.Frame(tab, bg=BG)
        main.pack(fill="both", expand=True, padx=4, pady=(4, 10))
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=1, minsize=400)
        main.rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=WHITE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        top = tk.Frame(left, bg=WHITE)
        top.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(top, text="Class photo", font=(FONT, 14, "bold"), bg=WHITE).pack(side="left")
        make_button(top, ">", lambda: self.shift_photo(1), "#ede9fe", PURPLE).pack(side="right")
        self.photo_lbl = tk.Label(top, text="", bg=WHITE, fg=MUTED)
        self.photo_lbl.pack(side="right", padx=6)
        make_button(top, "<", lambda: self.shift_photo(-1), "#ede9fe", PURPLE).pack(side="right")
        self.canvas = tk.Canvas(left, bg="#f1f1fb", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=14)
        self.canvas.bind("<Configure>", lambda e: self.draw_photo())
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        leg = tk.Frame(left, bg=WHITE)
        leg.pack(fill="x", padx=14, pady=8)
        for color, text in [(GREEN, "Matched"), (ORANGE, "Please check"),
                            (RED, "Unknown - click the face to assign")]:
            tk.Frame(leg, bg=color, width=18, height=18).pack(side="left")
            tk.Label(leg, text=text, bg=WHITE, fg=MUTED).pack(side="left", padx=(4, 16))

        right = tk.Frame(main, bg=WHITE)
        right.grid(row=0, column=1, sticky="nsew")
        tk.Label(right, text="Students", font=(FONT, 14, "bold"), bg=WHITE).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Entry(right, textvariable=self.search, relief="solid", bd=1,
                 font=(FONT, 10)).pack(fill="x", padx=14, ipady=6)
        wrap = tk.Frame(right, bg=WHITE)
        wrap.pack(fill="both", expand=True, padx=(14, 4), pady=8)
        self.lcanvas = tk.Canvas(wrap, bg=WHITE, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.lcanvas.yview)
        self.lcanvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.lcanvas.pack(side="left", fill="both", expand=True)
        self.linner = tk.Frame(self.lcanvas, bg=WHITE)
        self.linner.columnconfigure(0, weight=1)
        win = self.lcanvas.create_window((0, 0), window=self.linner, anchor="nw")
        self.linner.bind("<Configure>", lambda e: self.lcanvas.configure(scrollregion=self.lcanvas.bbox("all")))
        self.lcanvas.bind("<Configure>", lambda e: self.lcanvas.itemconfigure(win, width=e.width))
        self.lcanvas.bind("<Enter>", lambda e: self.lcanvas.bind_all("<MouseWheel>", self._wheel))
        self.lcanvas.bind("<Leave>", lambda e: self.lcanvas.unbind_all("<MouseWheel>"))
        bot = tk.Frame(right, bg=WHITE)
        bot.pack(fill="x", padx=14, pady=(0, 10))
        make_button(bot, "Mark all present", lambda: self.mark_all("present"), "#dcfce7", GREEN).pack(side="left")
        make_button(bot, "Mark all absent", lambda: self.mark_all("absent"), "#fee2e2", RED).pack(side="left", padx=8)

    def _wheel(self, e):
        self.lcanvas.yview_scroll(int(-e.delta / 120), "units")

    # ---------- tab 2: students ----------
    def _build_students(self, tab):
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=4, pady=10)
        tk.Label(bar, text="Section", bg=BG).pack(side="left")
        self.cb_students = ttk.Combobox(bar, textvariable=self.section, width=12, state="readonly")
        self.cb_students.pack(side="left", padx=(4, 14))
        make_button(bar, "+ Add student", self.add_student).pack(side="left")
        make_button(bar, "Add photos to selected", self.add_photos_selected, VIOLET).pack(side="left", padx=8)
        make_button(bar, "Import folder", self.import_folder, BLUE).pack(side="left")
        make_button(bar, "Delete selected", self.delete_student, "#fee2e2", RED).pack(side="right")
        self.tree_st = ttk.Treeview(tab, columns=("roll", "name", "photos"), show="headings", height=18)
        for col, text, w in [("roll", "Roll", 120), ("name", "Name", 380), ("photos", "Face photos enrolled", 180)]:
            self.tree_st.heading(col, text=text)
            self.tree_st.column(col, width=w, anchor="w")
        self.tree_st.tag_configure("low", foreground=RED)
        self.tree_st.pack(fill="both", expand=True, padx=4)
        self.lbl_students = tk.Label(tab, text="", bg=BG, fg=MUTED, anchor="w")
        self.lbl_students.pack(fill="x", padx=6, pady=6)

    # ---------- tab 3: report ----------
    def _build_report(self, tab):
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", padx=4, pady=10)
        tk.Label(bar, text="Section", bg=BG).pack(side="left")
        self.cb_report = ttk.Combobox(bar, textvariable=self.section, width=12, state="readonly")
        self.cb_report.pack(side="left", padx=(4, 14))
        make_button(bar, "Refresh", self.refresh_report, WHITE, PURPLE).pack(side="left")
        make_button(bar, "Export summary CSV", self.export_report, BLUE).pack(side="right")
        make_button(bar, "Export day-wise CSV", self.export_matrix, VIOLET).pack(side="right", padx=8)
        cols = ("roll", "name", "present", "total", "pct")
        self.tree_rp = ttk.Treeview(tab, columns=cols, show="headings", height=18)
        for col, text, w in [("roll", "Roll", 110), ("name", "Name", 340), ("present", "Days present", 120),
                             ("total", "Days recorded", 120), ("pct", "Attendance %", 120)]:
            self.tree_rp.heading(col, text=text)
            self.tree_rp.column(col, width=w, anchor="w")
        self.tree_rp.tag_configure("short", foreground=RED)
        self.tree_rp.pack(fill="both", expand=True, padx=4)
        self.lbl_report = tk.Label(tab, text="Red = below 75%", bg=BG, fg=MUTED, anchor="w")
        self.lbl_report.pack(fill="x", padx=6, pady=6)

    # ---------- sections ----------
    def refresh_sections(self, select=None):
        if not self.system:
            return
        vals = self.system.store.sections()
        for cb in (self.cb_take, self.cb_students, self.cb_report):
            cb["values"] = vals
        cur = select or self.section.get()
        self.section.set(cur if cur in vals else (vals[0] if vals else ""))

    def _on_section(self):
        self.result = None
        self.rows = {}
        for w in self.linner.winfo_children():
            w.destroy()
        self.update_stats()
        self.draw_photo()
        if self.system:
            self.refresh_students()
            self.refresh_report()

    # ---------- date ----------
    def _get_date(self):
        try:
            return dt.datetime.strptime(self.date.get().strip(), "%Y-%m-%d").date().isoformat()
        except ValueError:
            messagebox.showwarning("Date", "Please type the date like 2026-10-15.")
            return None

    def shift_date(self, d):
        cur = self._get_date()
        if cur:
            self.date.set((dt.date.fromisoformat(cur) + dt.timedelta(days=d)).isoformat())

    # ---------- scanning ----------
    def _ready_to_scan(self):
        """Common checks before scanning. Returns (section, date) or None."""
        if not self.need_system():
            return None
        sec = self.section.get()
        roster = self.system.store.roster(sec) if sec else []
        if not roster:
            messagebox.showinfo("No students", "Open the Students tab and add students first.")
            return None
        if all(self.system.store.embedding_count(r) == 0 for r, _ in roster):
            messagebox.showinfo("No face photos", "Students have no face photos yet. "
                                "Add photos in the Students tab first.")
            return None
        date = self._get_date()
        return (sec, date) if date else None

    def choose_photos(self):
        ready = self._ready_to_scan()
        if not ready:
            return
        paths = filedialog.askopenfilenames(title="Choose class photo(s) - full-size photos work best",
                                            filetypes=IMG_TYPES)
        if paths:
            self._scan(list(paths), *ready)

    def use_camera(self):
        """Take the class photo(s) with a camera instead of choosing a file."""
        ready = self._ready_to_scan()
        if not ready:
            return
        messagebox.showinfo(
            "Class photo with camera",
            "A camera window will open.\n\n"
            "SPACE = take a photo (take 2-3 if the class is wide: left, centre, right)\n"
            "C = switch to another camera (phone webcam, USB camera)\n"
            "ESC = finish and scan")
        frames = self.capture_webcam(hi_res=True)
        if not frames:
            return
        self._scan(self._save_captures(frames), *ready)

    def _save_captures(self, frames):
        folder = os.path.join(APP_DIR, "captures")
        os.makedirs(folder, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        paths = []
        for i, fr in enumerate(frames, 1):
            p = os.path.join(folder, f"class_{stamp}_{i}.jpg")
            ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if ok:
                buf.tofile(p)
                paths.append(p)
        return paths

    def _scan(self, paths, sec, date):
        self.run_bg(lambda: self.system.take_attendance(paths, sec, date), self._got_result,
                    msg="Scanning faces... this takes 10-30 seconds")

    def _got_result(self, res):
        self.result, self.photo_idx = res, 0
        self.build_rows()
        self.update_stats()
        self.draw_photo()
        faces = sum(len(p.faces) for p in res.photos)
        self.status.set(f"Found {faces} faces. Present {len(res.present)}, "
                        f"please check {len(res.review)}, absent {len(res.absent)}. "
                        "Click red faces to assign them, then Save.")

    # ---------- photo canvas ----------
    def _load_pil(self, path):
        if path not in self._pil_cache:
            bgr = read_image(path)
            if bgr is None:
                return None
            h, w = bgr.shape[:2]
            if max(h, w) > 2400:
                s = 2400 / max(h, w)
                bgr = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            self._pil_cache = {path: Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))}
        return self._pil_cache[path]

    def shift_photo(self, d):
        if self.result and len(self.result.photos) > 1:
            self.photo_idx = (self.photo_idx + d) % len(self.result.photos)
            self.draw_photo()

    def draw_photo(self):
        c = self.canvas
        c.delete("all")
        cw, ch = max(c.winfo_width(), 10), max(c.winfo_height(), 10)
        if self.result is None or not self.result.photos:
            msg = "Choose a class photo to take attendance"
            if self.system and not self.system.store.sections():
                msg = "Open the Students tab and add students first"
            c.create_text(cw // 2, ch // 2, text=msg, fill=MUTED, font=(FONT, 14))
            self.photo_lbl.config(text="")
            return
        ph = self.result.photos[self.photo_idx]
        self.photo_lbl.config(text=f"Photo {self.photo_idx + 1} of {len(self.result.photos)}")
        pil = self._load_pil(ph.path)
        h0, w0 = ph.size
        s = min(cw / w0, ch / h0)
        dw, dh = max(1, int(w0 * s)), max(1, int(h0 * s))
        if pil is not None:
            self._tk_img = ImageTk.PhotoImage(pil.resize((dw, dh), Image.BILINEAR))
            ox, oy = (cw - dw) // 2, (ch - dh) // 2
            c.create_image(ox, oy, image=self._tk_img, anchor="nw")
        else:
            ox = oy = 0
        self._view = (ox, oy, s)
        by_face = {(r.photo_idx, r.face_idx): r for r in self.result.students if r.photo_idx >= 0}
        for i, f in enumerate(ph.faces):
            r = by_face.get((self.photo_idx, i))
            color, label = RED, "?"
            if r is not None and r.status == "present":
                color, label = GREEN, r.name
            elif r is not None and r.status == "review":
                color, label = ORANGE, r.name + " ?"
            x1, y1, x2, y2 = (ox + f.bbox[0] * s, oy + f.bbox[1] * s, ox + f.bbox[2] * s, oy + f.bbox[3] * s)
            c.create_rectangle(x1, y1, x2, y2, outline=color, width=2)
            if label != "?":
                t = c.create_text(x1, y1 - 2, text=label, anchor="sw", fill="white", font=(FONT, 9, "bold"))
                bb = c.bbox(t)
                bg = c.create_rectangle(bb[0] - 2, bb[1], bb[2] + 2, bb[3], fill=color, outline="")
                c.tag_lower(bg, t)
            elif (x2 - x1) > 14:
                c.create_text((x1 + x2) / 2, y2 + 7, text="?", fill=RED, font=(FONT, 9, "bold"))

    def on_canvas_click(self, ev):
        if not self.result or not self.result.photos:
            return
        ox, oy, s = self._view
        x, y = (ev.x - ox) / s, (ev.y - oy) / s
        faces = self.result.photos[self.photo_idx].faces
        hits = [(i, (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])) for i, f in enumerate(faces)
                if f.bbox[0] <= x <= f.bbox[2] and f.bbox[1] <= y <= f.bbox[3]]
        if not hits:
            return
        i = min(hits, key=lambda t: t[1])[0]
        dlg = StudentPicker(self, faces[i].candidates, self.result.students)
        if dlg.result is None:
            return
        p = self.photo_idx
        for r in self.result.students:                      # free whoever held this face
            if r.photo_idx == p and r.face_idx == i and r.status in ("present", "review"):
                r.status, r.source, r.photo_idx, r.face_idx = "absent", "manual", -1, -1
        if dlg.result:
            self.result.assign_face(p, i, dlg.result)
        self.refresh_all()

    # ---------- student list (right panel) ----------
    def build_rows(self):
        for w in self.linner.winfo_children():
            w.destroy()
        self.rows = {}
        if not self.result:
            return
        for idx, s in enumerate(self.result.students):
            f = tk.Frame(self.linner, bg=WHITE, highlightthickness=1, highlightbackground="#e5e7eb")
            bar = tk.Frame(f, width=5, bg=GREEN)
            bar.pack(side="left", fill="y")
            mid = tk.Frame(f, bg=WHITE)
            mid.pack(side="left", fill="x", expand=True, padx=8, pady=6)
            tk.Label(mid, text=s.name, font=(FONT, 11, "bold"), bg=WHITE, anchor="w").pack(fill="x")
            tk.Label(mid, text=f"Roll {s.roll}", fg=MUTED, bg=WHITE, anchor="w").pack(fill="x")
            badge = tk.Label(f, text="", font=(FONT, 8, "bold"), padx=6)
            badge.pack(side="left", padx=4)
            btn = tk.Button(f, width=10, relief="flat", font=(FONT, 10, "bold"), cursor="hand2",
                            command=lambda r=s.roll: self.toggle(r))
            btn.pack(side="right", padx=8, pady=8)
            f.grid(row=idx, column=0, sticky="ew", pady=2, padx=2)
            self.rows[s.roll] = dict(frame=f, bar=bar, badge=badge, btn=btn, rec=s)
            self.update_row(s)
        self.apply_filter()

    def update_row(self, s):
        w = self.rows.get(s.roll)
        if not w:
            return
        look = {"present": (GREEN, "Present", GREEN, "white"),
                "review": (ORANGE, "Check", "#fef3c7", "#92400e"),
                "absent": ("#fca5a5", "Absent", "#fee2e2", RED)}[s.status]
        w["bar"].config(bg=look[0])
        w["btn"].config(text=("✔ " if s.status == "present" else "") + look[1], bg=look[2],
                        fg=look[3], activebackground=look[2], activeforeground=look[3])
        if s.source == "manual":
            w["badge"].config(text="Manual", bg="#e0e7ff", fg=BLUE)
        elif s.status == "present":
            w["badge"].config(text="High", bg="#dcfce7", fg=GREEN)
        elif s.status == "review":
            w["badge"].config(text=f"{s.similarity:.2f}", bg="#fef3c7", fg="#92400e")
        else:
            w["badge"].config(text="", bg=WHITE)

    def apply_filter(self):
        q = self.search.get().lower().strip()
        for roll, w in self.rows.items():
            r = w["rec"]
            if q in r.name.lower() or q in r.roll.lower():
                w["frame"].grid()
            else:
                w["frame"].grid_remove()

    def toggle(self, roll):
        r = self.rows[roll]["rec"]
        self.result.mark(roll, "absent" if r.status == "present" else "present")
        self.refresh_all()

    def mark_all(self, status):
        if not self.result:
            return
        for s in self.result.students:
            self.result.mark(s.roll, status)
        self.refresh_all()

    def refresh_all(self):
        for w in self.rows.values():
            self.update_row(w["rec"])
        self.update_stats()
        self.draw_photo()

    def update_stats(self):
        r = self.result
        n = len(r.students) if r else 0
        vals = dict(students=n, present=len(r.present) if r else 0, absent=len(r.absent) if r else 0,
                    check=len(r.review) if r else 0,
                    pct=f"{round(100 * len(r.present) / n)}%" if r and n else "0%")
        for k, v in vals.items():
            self.cards[k].set(str(v))

    # ---------- save / export / upload ----------
    def _finalize(self):
        """Orange students must be decided before saving. Returns date or None."""
        if not self.result:
            messagebox.showinfo("Nothing to save", "Choose a class photo first.")
            return None
        date = self._get_date()
        if not date:
            return None
        if self.result.review:
            ans = messagebox.askyesnocancel(
                "Students still marked 'Check'",
                f"{len(self.result.review)} student(s) are still orange (not sure).\n\n"
                "Yes = mark them ABSENT.   No = mark them PRESENT.   Cancel = go back and check them.")
            if ans is None:
                return None
            for s in list(self.result.review):
                self.result.mark(s.roll, "present" if ans is False else "absent")
            self.refresh_all()
        self.result.date = date
        return date

    def save(self):
        date = self._finalize()
        if not date:
            return
        sec = self.section.get()
        if self.system.store.has_attendance(date, sec) and not messagebox.askyesno(
                "Already saved", f"Attendance for {sec} on {date} was already saved.\nReplace it?"):
            return
        recs = [(s.roll, "present" if s.status == "present" else "absent", s.similarity, s.source)
                for s in self.result.students]
        self.system.store.save_attendance(date, sec, recs)
        self.status.set(f"Attendance saved for {date}")
        messagebox.showinfo("Saved", f"Attendance saved for {sec} on {date}.\n"
                            f"Present: {len(self.result.present)}   Absent: {len(self.result.absent)}")

    def export_csv(self):
        date = self._finalize()
        if not date:
            return
        from attendance_ai.export import to_csv
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"attendance_{date}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if path:
            to_csv(self.result, path, unresolved="absent")
            self.status.set(f"Exported {path}")

    def upload(self):
        date = self._finalize()
        if not date:
            return
        cfg_path = "college_api.json"
        if not os.path.exists(cfg_path):
            messagebox.showinfo(
                "Upload not set up yet",
                "Ask the college for their attendance API address, then create a file named\n"
                "college_api.json in this folder:\n\n"
                '{"url": "https://college.example/api/attendance", "token": "YOUR_TOKEN"}\n\n'
                "Until then, use Export CSV and upload that file.")
            return
        from attendance_ai.export import CollegeClient, to_payload
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        payload = to_payload(self.result, unresolved="absent", teacher_id=cfg.get("teacher_id", ""))
        client = CollegeClient(cfg["url"], cfg.get("token"))
        self.run_bg(lambda: client.push(payload),
                    lambda r: messagebox.showinfo("Uploaded", f"College server replied: {r[0]}"),
                    msg="Uploading to college...")

    # ---------- students tab actions ----------
    def refresh_students(self):
        if not self.system:
            return
        self.tree_st.delete(*self.tree_st.get_children())
        sec = self.section.get()
        low = 0
        for roll, name in (self.system.store.roster(sec) if sec else []):
            n = self.system.store.embedding_count(roll)
            if n < 3:
                low += 1
            self.tree_st.insert("", "end", iid=roll, values=(roll, name, n), tags=("low",) if n < 3 else ())
        total = len(self.tree_st.get_children())
        self.lbl_students.config(text=f"{total} students.   Red = fewer than 3 photos "
                                 f"({low} need more). 5-10 clear photos per student works best.")

    def _read_files(self, paths):
        return [im for im in (read_image(p) for p in paths) if im is not None]

    def _open_camera(self, idx, hi_res):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            return None
        if hi_res:                                   # ask for the biggest picture the camera offers
            for w, h in [(3840, 2160), (2560, 1440), (1920, 1080), (1280, 720)]:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                if cap.get(cv2.CAP_PROP_FRAME_WIDTH) >= w * 0.95:
                    break
        for _ in range(8):                           # first frames are often dark
            cap.read()
        return cap

    def capture_webcam(self, hi_res=False):
        """Live preview. SPACE = take photo, C = next camera, ESC = done. Returns full-size frames."""
        idx, cap = 0, None
        for i in range(3):
            cap = self._open_camera(i, hi_res)
            if cap is not None:
                idx = i
                break
        if cap is None:
            messagebox.showerror("Camera", "Could not open any camera.\n"
                                 "Close other apps using the camera and try again.")
            return []
        frames, win = [], "Camera"
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            view = frame
            if frame.shape[1] > 960:
                view = cv2.resize(frame, (960, int(frame.shape[0] * 960 / frame.shape[1])))
            view = view.copy()
            cv2.putText(view, f"Photos: {len(frames)}  SPACE=take  C=switch camera  ESC=done  "
                        f"({frame.shape[1]}x{frame.shape[0]})", (10, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow(win, view)
            k = cv2.waitKey(1) & 0xFF
            if k == 27:
                break
            if k == 32:
                frames.append(frame.copy())
            if k in (ord("c"), ord("C")):
                cap.release()
                idx = (idx + 1) % 3
                cap = self._open_camera(idx, hi_res) or self._open_camera(0, hi_res)
                if cap is None:
                    break
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        return frames

    def _enroll(self, roll, name, sec, images):
        if not images:
            return

        def work():
            return [self.system.enroll_image(roll, name, sec, im) for im in images]

        def done(out):
            good = sum(1 for ok, _ in out if ok)
            notes = sorted({m for ok, m in out if (not ok) or "warning" in m})
            text = f"{name}: {good} of {len(out)} photos accepted."
            if good < 3:
                text += "\nAdd more photos - at least 3, ideally 5-10."
            if notes:
                text += "\n\nNotes:\n- " + "\n- ".join(notes)
            messagebox.showinfo("Enrollment", text)
            self.refresh_sections(select=sec)
            self.refresh_students()
        self.run_bg(work, done, msg=f"Adding photos for {name}...")

    def add_student(self):
        if not self.need_system():
            return
        dlg = AddStudentDialog(self, self.system.store.sections(), self.section.get())
        if not dlg.result:
            return
        roll, name, sec, mode = dlg.result
        if mode == "files":
            paths = filedialog.askopenfilenames(title=f"Choose 5-10 photos of {name}", filetypes=IMG_TYPES)
            images = self._read_files(paths) if paths else []
        else:
            images = self.capture_webcam()
        self._enroll(roll, name, sec, images)

    def add_photos_selected(self):
        sel = self.tree_st.selection()
        if not sel or not self.need_system():
            messagebox.showinfo("Select a student", "Click a student in the list first.")
            return
        roll = sel[0]
        name = self.tree_st.item(roll, "values")[1]
        mode = messagebox.askyesno("Add photos", "Yes = choose photo files\nNo = use webcam")
        if mode:
            paths = filedialog.askopenfilenames(title=f"Photos of {name}", filetypes=IMG_TYPES)
            images = self._read_files(paths) if paths else []
        else:
            images = self.capture_webcam()
        self._enroll(roll, name, self.section.get(), images)

    def import_folder(self):
        if not self.need_system():
            return
        from tkinter import simpledialog
        sec = self.section.get() or simpledialog.askstring(
            "Section", "Section name for these students (e.g. CSE-A):")
        if not sec:
            return
        folder = filedialog.askdirectory(title="Folder containing  roll__name  sub-folders")
        if not folder:
            return
        lines = []

        def done(_):
            messagebox.showinfo("Import finished", "\n".join(lines[-25:]) or "Nothing found.")
            self.refresh_sections(select=sec)
            self.refresh_students()
        self.run_bg(lambda: self.system.enroll_folder(folder, sec, log=lines.append), done,
                    msg="Importing students... please wait")

    def delete_student(self):
        sel = self.tree_st.selection()
        if not sel:
            messagebox.showinfo("Select a student", "Click a student in the list first.")
            return
        if messagebox.askyesno("Delete", f"Delete {sel[0]} and their face data?"):
            self.system.store.delete_student(sel[0])
            self.refresh_sections()
            self.refresh_students()

    # ---------- report tab ----------
    def refresh_report(self):
        if not self.system:
            return
        self.tree_rp.delete(*self.tree_rp.get_children())
        sec = self.section.get()
        if not sec:
            return
        days = 0
        for roll, name, pres, total in self.system.store.report(sec):
            days = max(days, total)
            pct = f"{100 * pres / total:.0f}%" if total else "-"
            self.tree_rp.insert("", "end", values=(roll, name, pres, total, pct),
                                tags=("short",) if total and pres / total < 0.75 else ())
        self.lbl_report.config(text=f"{days} day(s) recorded.   Red = below 75% attendance.")

    def export_report(self):
        sec = self.section.get()
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"report_{sec}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["roll", "name", "days_present", "days_recorded", "percent"])
            for roll, name, pres, total in self.system.store.report(sec):
                w.writerow([roll, name, pres, total, round(100 * pres / total, 1) if total else ""])
        self.status.set(f"Exported {path}")

    def export_matrix(self):
        sec = self.section.get()
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"daywise_{sec}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        dates, rows = self.system.store.matrix(sec)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["roll", "name"] + dates)
            for roll, name, sts in rows:
                w.writerow([roll, name] + [{"present": "P", "absent": "A"}.get(s, "") for s in sts])
        self.status.set(f"Exported {path}")


if __name__ == "__main__":
    App().mainloop()
