import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
import subprocess, sys, os, json, threading, re

# ── palette ───────────────────────────────────────────────────────────────────
BG       = "#0d0d0f"
SURFACE  = "#16161a"
SURFACE2 = "#1c1c22"
BORDER   = "#2a2a32"
ACCENT   = "#7c6aff"
ACCENT2  = "#ff6a9e"
TEXT     = "#e8e6f0"
TEXT_DIM = "#6b6880"

TILE_COLORS = [
    "#7c6aff","#ff6a9e","#00d4aa","#ff9f43",
    "#54a0ff","#ff6b6b","#a29bfe","#00cec9",
    "#fd79a8","#6c5ce7","#00b894","#e17055",
]
PANEL_PRESETS = [
    "#7c6aff","#ff6a9e","#00d4aa","#ff9f43",
    "#54a0ff","#ff6b6b","#ffffff","#000000",
    "#a29bfe","#00cec9","#fd79a8","#e17055",
]

FONT_TITLE = ("Segoe UI", 11, "bold")
FONT_BODY  = ("Segoe UI", 9)
FONT_SMALL = ("Segoe UI", 8)

DATA_FILE  = os.path.join(os.path.expanduser("~"), ".folder_board.json")
NOTES_FILE = os.path.join(os.path.expanduser("~"), ".folder_board_notes.json")

EXT_ICONS = {
    ".pdf":"PDF",".doc":"DOC",".docx":"DOC",".xls":"XLS",".xlsx":"XLS",
    ".ppt":"PPT",".pptx":"PPT",".txt":"TXT",".md":"MD",
    ".py":"PY",".js":"JS",".ts":"TS",".html":"HTM",".css":"CSS",
    ".json":"JSN",".xml":"XML",".csv":"CSV",
    ".jpg":"IMG",".jpeg":"IMG",".png":"IMG",".gif":"IMG",".svg":"SVG",".webp":"IMG",
    ".mp3":"MP3",".wav":"WAV",".flac":"AUD",".mp4":"MP4",".avi":"AVI",".mkv":"MKV",
    ".zip":"ZIP",".rar":"RAR",".7z":"7Z",".tar":"TAR",".gz":"GZ",
    ".exe":"EXE",".msi":"MSI",".sh":"SH",".bat":"BAT",
}

# Revision suffix order: A < B < ... < Z < 0 < 1 < ... < 9
# Examples: archivo_B.pdf -> rev "B", archivo_B_2.pdf -> rev "B" (last alpha suffix wins),
#           archivo_2.pdf -> rev "2"
def _rev_key(suffix):
    """Key for comparing revision tokens. Single letter < numbers."""
    s = suffix.upper().strip()
    if not s: return (2, 0, s)
    if len(s) == 1 and s.isalpha(): return (0, ord(s), s)   # A=65 … Z=90
    if s.isdigit():                  return (1, int(s),  s)   # 0,1,2…
    # multi-char: try as integer first, else string compare
    try: return (1, int(s), s)
    except ValueError: return (2, 0, s)

def _base_and_rev(stem):
    """
    Extract base name and revision token from a stem.
    Rules (last _token wins as revision if token is alpha or numeric):
      archivo_B     -> ('archivo', 'B')
      archivo_B_2   -> ('archivo_B', '2')   last token is numeric
      archivo_2     -> ('archivo', '2')
      archivo_B2    -> ('archivo', None)     not a clean token
    """
    m = re.match(r'^(.*?)_([A-Za-z])$', stem)       # ends _<single letter>
    if m: return m.group(1), m.group(2)
    m = re.match(r'^(.*?)_([0-9]+)$', stem)          # ends _<digits>
    if m: return m.group(1), m.group(2)
    return stem, None

# Folder priority for deduplication (higher = preferred)
_FOLDER_PRIORITY = [
    "DESARROLLO DE PL & DOC (NATIVOS)",   # highest priority
]
_FOLDER_DEPRIORITY = [
    "EMITIDOS (PDF)",
    "REVISIONES & COMENTARIOS (PDF)",
]

def _folder_priority(absp):
    """Return sort key: (priority_tier, path). Lower tier = more preferred."""
    p = absp.replace("\\", "/")
    for i, name in enumerate(_FOLDER_PRIORITY):
        if name.upper() in p.upper():
            return (0, i, p)   # highest priority
    for i, name in enumerate(_FOLDER_DEPRIORITY):
        if name.upper() in p.upper():
            return (2, i, p)   # lower priority
    return (1, 0, p)           # neutral

def latest_revisions(file_list):
    """
    file_list: list of (rel, abs_path)
    - Excludes files whose stem ends with _CK (case-insensitive)
    - Only includes files whose stem ends with _<single letter> or _<digits>
    - Groups by (base_name, ext) ACROSS all folders
    - Within a group picks the highest revision; ties broken by folder priority
    - Result: one file per (base_name, ext) — no duplicates
    """
    from collections import defaultdict
    # group by (base_name_lower, ext_lower) — cross-folder
    groups = defaultdict(list)
    for rel, absp in file_list:
        fname = os.path.basename(absp)
        stem, ext = os.path.splitext(fname)
        # must end with _CK? skip
        if re.search(r'_CK\b', stem, re.IGNORECASE):
            continue
        # stem must end with _<single letter> OR _<digits>
        base, rev = _base_and_rev(stem)
        if rev is None:
            continue
        groups[(base.lower(), ext.lower())].append((rev, rel, absp))

    result = []
    for (base_key, ext_key), entries in groups.items():
        # Sort: primary = revision descending, secondary = folder priority ascending
        entries.sort(key=lambda x: (_rev_key(x[0]), _folder_priority(x[2])),
                     reverse=False)
        # Find the best revision
        best_rev_key = _rev_key(entries[-1][0])
        # Among entries with the best revision, pick by folder priority
        candidates = [e for e in entries if _rev_key(e[0]) == best_rev_key]
        candidates.sort(key=lambda x: _folder_priority(x[2]))
        best = candidates[0]
        result.append((best[1], best[2]))
    return result


# ── helpers ───────────────────────────────────────────────────────────────────
def hex_lum(c):
    h=c.lstrip("#"); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return 0.299*r+0.587*g+0.114*b

def contrasting(c):
    return "#ffffff" if hex_lum(c)<140 else "#000000"

def darken(c, amt=30):
    h=c.lstrip("#"); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return f"#{max(0,r-amt):02x}{max(0,g-amt):02x}{max(0,b-amt):02x}"

def lighten(c, amt=40):
    h=c.lstrip("#"); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return f"#{min(255,r+amt):02x}{min(255,g+amt):02x}{min(255,b+amt):02x}"

def open_path(path):
    try:
        if sys.platform=="win32": os.startfile(path)
        elif sys.platform=="darwin": subprocess.Popen(["open", path])
        else: subprocess.Popen(["xdg-open", path])
    except Exception as ex:
        messagebox.showerror("Error", str(ex))

def open_folder_of(abs_path):
    folder = os.path.dirname(abs_path)
    open_path(folder)


# ═══════════════════════════════════════════════════════════════════════════════
#  NOTES STORE
# ═══════════════════════════════════════════════════════════════════════════════
class NotesStore:
    """Persistent dict: abs_path -> note string"""
    def __init__(self):
        self._data = {}
        self._load()

    def _load(self):
        if os.path.exists(NOTES_FILE):
            try:
                with open(NOTES_FILE, encoding="utf-8") as f:
                    self._data = json.load(f)
            except: pass

    def _save(self):
        try:
            with open(NOTES_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except: pass

    def get(self, path): return self._data.get(path, "")
    def set(self, path, note):
        self._data[path] = note
        self._save()

NOTES = NotesStore()


# ═══════════════════════════════════════════════════════════════════════════════
#  CUSTOM SCROLLBAR  (canvas-based, fully themed)
# ═══════════════════════════════════════════════════════════════════════════════
class DarkScrollbar(tk.Canvas):
    """A themed scrollbar that actually respects colors on Windows."""
    PAD = 2
    MIN_THUMB = 20

    def __init__(self, master, orient="vertical", command=None, **kw):
        self._orient      = orient
        self._command     = command
        self._thumb_start = 0.0
        self._thumb_end   = 1.0
        self._dragging    = False
        self._drag_offset = 0.0   # cursor offset within thumb at press time

        if orient == "vertical":
            kw.setdefault("width", 12)
        else:
            kw.setdefault("height", 12)

        super().__init__(master, bg="#1a1a20", highlightthickness=0, bd=0, **kw)
        self.create_rectangle(0,0,0,0, fill="#444450", outline="", tags="thumb")
        self.bind("<Configure>",      self._redraw)
        self.bind("<ButtonPress-1>",  self._on_press)
        self.bind("<B1-Motion>",      self._on_drag)
        self.bind("<ButtonRelease-1>",self._on_release)
        self.tag_bind("thumb","<Enter>",  lambda e: self.itemconfig("thumb", fill="#6a6a80"))
        self.tag_bind("thumb","<Leave>",  lambda e: self.itemconfig("thumb", fill="#444450"))

    # ── public API (matches tk.Scrollbar) ──
    def set(self, lo, hi):
        self._thumb_start = float(lo)
        self._thumb_end   = float(hi)
        self._redraw()

    # ── internal ──
    def _track_size(self):
        if self._orient == "vertical":
            return max(1, self.winfo_height() - 2*self.PAD)
        return max(1, self.winfo_width() - 2*self.PAD)

    def _thumb_pixels(self):
        """Return (thumb_start_px, thumb_end_px) in canvas coords."""
        ts = self._track_size()
        t0 = self.PAD + self._thumb_start * ts
        t1 = self.PAD + self._thumb_end   * ts
        # enforce minimum size
        if t1 - t0 < self.MIN_THUMB:
            t1 = t0 + self.MIN_THUMB
        return t0, t1

    def _redraw(self, e=None):
        w = self.winfo_width()  or int(self.cget("width")  if self._orient=="horizontal" else 12)
        h = self.winfo_height() or int(self.cget("height") if self._orient=="vertical"   else 12)
        t0, t1 = self._thumb_pixels()
        if self._orient == "vertical":
            self.coords("thumb", self.PAD, t0, w - self.PAD, t1)
        else:
            self.coords("thumb", t0, self.PAD, t1, h - self.PAD)

    def _pos_to_fraction(self, pos):
        """Convert pixel position to 0..1 fraction along the track."""
        return (pos - self.PAD) / self._track_size()

    def _on_press(self, e):
        pos = e.y if self._orient == "vertical" else e.x
        t0, t1 = self._thumb_pixels()
        if t0 <= pos <= t1:
            # click inside thumb — start drag, record offset from thumb start
            self._dragging    = True
            self._drag_offset = pos - t0
        else:
            # click outside thumb — jump: centre thumb on click position
            self._dragging = False
            if self._command:
                size   = self._thumb_end - self._thumb_start
                new_lo = max(0.0, min(1.0 - size,
                             self._pos_to_fraction(pos) - size / 2))
                self._command("moveto", new_lo)

    def _on_drag(self, e):
        if not self._dragging or not self._command: return
        pos    = e.y if self._orient == "vertical" else e.x
        size   = self._thumb_end - self._thumb_start
        # desired start of thumb in fraction coords
        new_lo = max(0.0, min(1.0 - size,
                     self._pos_to_fraction(pos - self._drag_offset)))
        self._command("moveto", new_lo)

    def _on_release(self, e):
        self._dragging = False

# ═══════════════════════════════════════════════════════════════════════════════
#  FILE BROWSER OVERLAY  (table layout)
# ═══════════════════════════════════════════════════════════════════════════════
class FileBrowser(tk.Frame):

    COL_WIDTHS = {"#":40, "Tipo":55, "Archivo":260, "Carpeta":220, "Notas":200}
    COLS = ["#", "Tipo", "Archivo", "Carpeta", "Notas"]

    def __init__(self, master, tile, close_cb):
        super().__init__(master, bg=SURFACE2,
                         highlightthickness=1, highlightbackground=ACCENT)
        self.tile      = tile
        self.close_cb  = close_cb
        self._all      = []    # list of (rel, abs)
        self._filtered = []
        # per-tile saved filters stored in tile object
        if not hasattr(tile, "saved_filters"):
            tile.saved_filters = []
        if not hasattr(tile, "_active_chip"):
            tile._active_chip = tile.saved_filters[0] if tile.saved_filters else ""
        if not hasattr(tile, "_browser_rev"):    tile._browser_rev = False
        if not hasattr(tile, "_browser_type"):   tile._browser_type = "all"
        if not hasattr(tile, "_browser_sort_col"): tile._browser_sort_col = "Archivo"
        if not hasattr(tile, "_browser_sort_rev"): tile._browser_sort_rev = False
        if not hasattr(tile, "_browser_exclude"): tile._browser_exclude = []  # list of str
        self._build()
        self._qvar.set("")
        self._rebuild_filter_chips()
        self._rebuild_exclude_chips()
        self._scan_async()

    # ── build UI ──────────────────────────────────────────────────────────────
    def _build(self):
        self._style_ttk()

        # ── header bar ──
        hdr = tk.Frame(self, bg=SURFACE, pady=0)
        hdr.pack(fill="x")
        tk.Label(hdr, text="●", bg=SURFACE, fg=self.tile.color,
                 font=("Segoe UI",13)).pack(side="left", padx=(12,4), pady=8)
        tk.Label(hdr, text=self.tile.name, bg=SURFACE, fg=TEXT,
                 font=("Segoe UI",12,"bold")).pack(side="left", pady=8)
        tk.Label(hdr, text=self.tile.path, bg=SURFACE, fg=TEXT_DIM,
                 font=("Segoe UI",8)).pack(side="left", padx=8, pady=8)
        tk.Button(hdr, text="✕", bg=SURFACE, fg=TEXT_DIM,
                  font=("Segoe UI",11,"bold"), bd=0, padx=12, cursor="hand2",
                  activebackground=ACCENT2, activeforeground="#fff",
                  command=self.close_cb).pack(side="right", padx=4, pady=4)

        # ── toolbar ──
        tb = tk.Frame(self, bg=SURFACE2, pady=4)
        tb.pack(fill="x", padx=10)

        # search
        tk.Label(tb, text="🔍", bg=SURFACE2, fg=TEXT_DIM,
                 font=("Segoe UI",10)).pack(side="left")
        self._qvar = tk.StringVar()
        self._qvar.trace_add("write", lambda *_: self._apply_filters())
        se = tk.Entry(tb, textvariable=self._qvar, width=22,
                      bg=BORDER, fg=TEXT, insertbackground=TEXT,
                      relief="flat", font=FONT_BODY)
        se.configure(highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT)
        se.pack(side="left", padx=(4,10))

        # latest-revision toggle — restore saved state
        self._rev_var = tk.BooleanVar(value=self.tile._browser_rev)
        cb_rev = tk.Checkbutton(tb, text="Solo última revisión",
                                variable=self._rev_var,
                                command=self._on_rev_change,
                                bg=SURFACE2, fg=TEXT, selectcolor=BORDER,
                                activebackground=SURFACE2,
                                font=FONT_SMALL)
        cb_rev.pack(side="left", padx=(0,12))

        # type filter buttons — restore saved state
        self._type_filter = tk.StringVar(value=self.tile._browser_type)
        type_frame = tk.Frame(tb, bg=SURFACE2)
        type_frame.pack(side="left", padx=(0,10))
        for label, val in [("Todos","all"),("PDF","pdf"),("Office","office")]:
            tk.Radiobutton(type_frame, text=label, variable=self._type_filter,
                           value=val, command=self._on_type_change,
                           bg=SURFACE2, fg=TEXT, selectcolor=ACCENT,
                           activebackground=SURFACE2, font=FONT_SMALL,
                           indicatoron=0, padx=8, pady=2,
                           relief="flat", cursor="hand2")\
              .pack(side="left", padx=1)

        # saved filters label
        tk.Label(tb, text="Filtros:", bg=SURFACE2, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")

        self._filters_frame = tk.Frame(tb, bg=SURFACE2)
        self._filters_frame.pack(side="left", padx=4)
        self._rebuild_filter_chips()

        # add filter button
        tk.Button(tb, text="＋ Guardar filtro", bg=BORDER, fg=TEXT_DIM,
                  font=FONT_SMALL, bd=0, padx=8, pady=3, cursor="hand2",
                  command=self._save_current_filter)\
          .pack(side="left", padx=4)


        # ── exclude filter row ──
        tb2 = tk.Frame(self, bg=SURFACE2, pady=2)
        tb2.pack(fill="x", padx=10)
        tk.Label(tb2, text="🚫 Excluir:", bg=SURFACE2, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")
        self._excl_var = tk.StringVar()
        ex_entry = tk.Entry(tb2, textvariable=self._excl_var, width=18,
                            bg=BORDER, fg=TEXT, insertbackground=TEXT,
                            relief="flat", font=FONT_BODY)
        ex_entry.configure(highlightthickness=1, highlightbackground=BORDER,
                           highlightcolor=ACCENT2)
        ex_entry.pack(side="left", padx=(4,6))
        tk.Button(tb2, text="＋ Excluir", bg=BORDER, fg=ACCENT2,
                  font=FONT_SMALL, bd=0, padx=8, pady=3, cursor="hand2",
                  command=self._save_exclude_filter)          .pack(side="left", padx=4)
        self._exclude_chips_frame = tk.Frame(tb2, bg=SURFACE2)
        self._exclude_chips_frame.pack(side="left", padx=4)

        # status
        self._status_var = tk.StringVar(value="Escaneando…")
        tk.Label(self, textvariable=self._status_var, bg=SURFACE2,
                 fg=TEXT_DIM, font=FONT_SMALL, anchor="w")\
          .pack(fill="x", padx=12, pady=(0,3))

        # ── table ──
        tf = tk.Frame(self, bg=SURFACE2)
        tf.pack(fill="both", expand=True, padx=6, pady=(0,6))

        vsb = DarkScrollbar(tf, orient="vertical",  command=self._tree_yview_proxy)
        vsb.pack(side="right", fill="y")
        hsb = DarkScrollbar(tf, orient="horizontal", command=self._tree_xview_proxy)
        hsb.pack(side="bottom", fill="x")
        self._vsb = vsb; self._hsb = hsb

        self._tree = ttk.Treeview(tf, columns=self.COLS, show="headings",
                                   style="FB.Treeview",
                                   yscrollcommand=vsb.set,
                                   xscrollcommand=hsb.set,
                                   selectmode="browse")
        self._tree.pack(fill="both", expand=True)

        for col in self.COLS:
            w = self.COL_WIDTHS[col]
            self._tree.heading(col, text=col,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=w, minwidth=30, stretch=(col=="Archivo"))

        self._tree.tag_configure("odd",  background="#191920")
        self._tree.tag_configure("even", background=SURFACE2)

        self._tree.bind("<Double-Button-1>", self._on_double_click)
        self._tree.bind("<Return>",          self._open_selected)
        self._tree.bind("<Button-3>",        self._row_ctx_menu)

        self._sort_col = self.tile._browser_sort_col
        self._sort_rev = self.tile._browser_sort_rev
        # update column heading arrows to reflect restored sort
        for c in self.COLS:
            arrow = (" ▲" if not self._sort_rev else " ▼") if c == self._sort_col else ""
            self._tree.heading(c, text=c+arrow)

    def _tree_yview_proxy(self, *args):
        self._tree.yview(*args)
        self._vsb.set(*self._tree.yview())

    def _tree_xview_proxy(self, *args):
        self._tree.xview(*args)
        self._hsb.set(*self._tree.xview())

    def _style_ttk(self):
        st = ttk.Style()
        st.theme_use("default")
        st.configure("FB.Treeview",
                      background=SURFACE2, foreground=TEXT,
                      fieldbackground=SURFACE2,
                      rowheight=24, font=("Segoe UI",9),
                      borderwidth=0, relief="flat")
        st.configure("FB.Treeview.Heading",
                      background=SURFACE, foreground=TEXT_DIM,
                      font=("Segoe UI",8,"bold"),
                      relief="flat", borderwidth=0)
        st.map("FB.Treeview",
               background=[("selected", ACCENT)],
               foreground=[("selected", "#fff")])
        st.map("FB.Treeview.Heading",
               background=[("active", BORDER)])

    # ── scanning ──────────────────────────────────────────────────────────────
    def _scan_async(self):
        def worker():
            results = []
            root = self.tile.path
            try:
                for dp, dirs, files in os.walk(root):
                    dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                    for fname in sorted(files):
                        if fname.startswith("."): continue
                        absp = os.path.join(dp, fname)
                        relp = os.path.relpath(absp, root)
                        results.append((relp, absp))
            except PermissionError: pass
            results.sort(key=lambda x: x[0].lower())
            self.after(0, lambda: self._on_scan_done(results))
        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, results):
        self._all = results
        self._apply_filters()

    # ── filtering & display ───────────────────────────────────────────────────
    def _apply_filters(self):
        q    = self._qvar.get().lower().strip()
        chip = self.tile._active_chip.lower().strip()
        data = self._all

        if self._rev_var.get():
            data = latest_revisions(data)

        # chip filter always active (AND with search box)
        if chip:
            data = [(r,a) for r,a in data if chip in r.lower()]
        # search box filter on top
        if q:
            data = [(r,a) for r,a in data if q in r.lower()]

        # exclude filter
        for excl in self.tile._browser_exclude:
            if excl:
                data = [(r,a) for r,a in data if excl.lower() not in os.path.basename(a).lower()]

        # type filter
        tf = self._type_filter.get()
        PDF_EXTS    = {".pdf"}
        OFFICE_EXTS = {".doc",".docx",".xls",".xlsx",".ppt",".pptx",".odt",".ods",".odp"}
        if tf == "pdf":
            data = [(r,a) for r,a in data if os.path.splitext(a)[1].lower() in PDF_EXTS]
        elif tf == "office":
            data = [(r,a) for r,a in data if os.path.splitext(a)[1].lower() in OFFICE_EXTS]

        self._filtered = data
        self._populate_table()
        self._update_status()

    def _populate_table(self):
        self._tree.delete(*self._tree.get_children())
        # sort
        col = self._sort_col
        rev = self._sort_rev

        def sort_key(item):
            rel, absp = item
            fname = os.path.basename(absp)
            stem, ext = os.path.splitext(fname)
            folder = os.path.relpath(os.path.dirname(absp), self.tile.path)
            note = NOTES.get(absp)
            mapping = {"#": rel, "Tipo": ext.lower(), "Archivo": fname.lower(),
                       "Carpeta": folder.lower(), "Notas": note.lower()}
            return mapping.get(col, rel.lower())

        sorted_data = sorted(self._filtered, key=sort_key, reverse=rev)

        for i, (rel, absp) in enumerate(sorted_data):
            fname = os.path.basename(absp)
            stem, ext = os.path.splitext(fname)
            tipo = EXT_ICONS.get(ext.lower(), "---")
            folder = os.path.relpath(os.path.dirname(absp), self.tile.path)
            if folder == ".": folder = "(raíz)"
            note = NOTES.get(absp)
            tag = "odd" if i%2 else "even"
            self._tree.insert("", "end",
                               values=(i+1, tipo, fname, folder, note),
                               tags=(tag,), iid=str(i))
        # store sorted data for index lookup
        self._sorted_data = sorted_data

    def _update_status(self):
        n = len(self._filtered)
        total = len(self._all)
        q = self._qvar.get().strip()
        rev = " · solo última rev." if self._rev_var.get() else ""
        if q:
            self._status_var.set(f"{n} de {total} archivos{rev}")
        else:
            self._status_var.set(f"{total} archivos en total{rev}")

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        self.tile._browser_sort_col = self._sort_col
        self.tile._browser_sort_rev = self._sort_rev
        self.tile.board.save()
        for c in self.COLS:
            arrow = ""
            if c == self._sort_col:
                arrow = " ▲" if not self._sort_rev else " ▼"
            self._tree.heading(c, text=c+arrow)
        self._populate_table()

    # ── saved filters (chips) ─────────────────────────────────────────────────
    def _rebuild_filter_chips(self):
        for w in self._filters_frame.winfo_children():
            w.destroy()
        for flt in self.tile.saved_filters:
            active   = (self.tile._active_chip == flt)
            chip_bg  = ACCENT if active else BORDER
            chip_fg  = "#fff"  if active else ACCENT
            del_fg   = "#fff"  if active else TEXT_DIM
            chip_f = tk.Frame(self._filters_frame, bg=chip_bg)
            chip_f.pack(side="left", padx=2)
            tk.Button(chip_f, text=flt, bg=chip_bg, fg=chip_fg,
                      font=FONT_SMALL, bd=0, padx=6, pady=2,
                      cursor="hand2",
                      command=lambda f=flt: self._apply_chip(f))\
              .pack(side="left")
            tk.Button(chip_f, text="×", bg=chip_bg, fg=del_fg,
                      font=FONT_SMALL, bd=0, padx=3, pady=2,
                      cursor="hand2",
                      command=lambda f=flt: self._delete_filter(f))\
              .pack(side="left")

    def _apply_chip(self, flt):
        # Toggle: if already active, deactivate; else activate
        if self.tile._active_chip == flt:
            self.tile._active_chip = ""
        else:
            self.tile._active_chip = flt
        self._qvar.set("")   # clear search box
        self._rebuild_filter_chips()
        self._apply_filters()

    def _save_current_filter(self):
        q = self._qvar.get().strip()
        if not q: return
        if q not in self.tile.saved_filters:
            self.tile.saved_filters.append(q)
            self._rebuild_filter_chips()
            # persist via board save
            self.tile.board.save()

    def _delete_filter(self, flt):
        if flt in self.tile.saved_filters:
            self.tile.saved_filters.remove(flt)
            self._rebuild_filter_chips()
            self.tile.board.save()

    # ── exclude filter chips ──────────────────────────────────────────────────
    def _rebuild_exclude_chips(self):
        for w in self._exclude_chips_frame.winfo_children():
            w.destroy()
        for flt in self.tile._browser_exclude:
            cf = tk.Frame(self._exclude_chips_frame, bg="#3a1a1a")
            cf.pack(side="left", padx=2)
            tk.Button(cf, text=flt, bg="#3a1a1a", fg=ACCENT2,
                      font=FONT_SMALL, bd=0, padx=6, pady=2, cursor="hand2")              .pack(side="left")
            tk.Button(cf, text="×", bg="#3a1a1a", fg=TEXT_DIM,
                      font=FONT_SMALL, bd=0, padx=3, pady=2, cursor="hand2",
                      command=lambda f=flt: self._delete_exclude(f))              .pack(side="left")

    def _save_exclude_filter(self):
        q = self._excl_var.get().strip()
        if not q: return
        if q not in self.tile._browser_exclude:
            self.tile._browser_exclude.append(q)
            self._excl_var.set("")
            self._rebuild_exclude_chips()
            self.tile.board.save()
            self._apply_filters()

    def _delete_exclude(self, flt):
        if flt in self.tile._browser_exclude:
            self.tile._browser_exclude.remove(flt)
            self._rebuild_exclude_chips()
            self.tile.board.save()
            self._apply_filters()

    # ── state persistence callbacks ───────────────────────────────────────────
    def _on_rev_change(self):
        self.tile._browser_rev = self._rev_var.get()
        self.tile.board.save()
        self._apply_filters()

    def _on_type_change(self):
        self.tile._browser_type = self._type_filter.get()
        self.tile.board.save()
        self._apply_filters()

    # ── row interactions ──────────────────────────────────────────────────────
    def _selected_abspath(self):
        sel = self._tree.selection()
        if not sel: return None
        idx = int(sel[0])
        return self._sorted_data[idx][1]

    def _on_double_click(self, e):
        region = self._tree.identify_region(e.x, e.y)
        col_id = self._tree.identify_column(e.x)
        # col #5 = Notas (1-indexed display)
        if col_id == "#5":
            self._edit_note_inline(e)
        else:
            self._open_selected()

    def _open_selected(self, e=None):
        absp = self._selected_abspath()
        if not absp: return
        if not os.path.isfile(absp):
            messagebox.showerror("Error", f"Archivo no encontrado:\n{absp}")
            return
        open_path(absp)

    def _goto_folder(self, absp=None):
        if absp is None: absp = self._selected_abspath()
        if not absp: return
        open_folder_of(absp)

    def _row_ctx_menu(self, e):
        row = self._tree.identify_row(e.y)
        if not row: return
        self._tree.selection_set(row)
        absp = self._selected_abspath()
        if not absp: return
        m = tk.Menu(self, tearoff=0, bg=SURFACE, fg=TEXT,
                    activebackground=ACCENT, activeforeground="#fff",
                    font=FONT_BODY, bd=0, relief="flat")
        m.add_command(label="↗  Abrir archivo",    command=self._open_selected)
        m.add_command(label="📁  Ir a la carpeta", command=lambda: self._goto_folder(absp))
        m.add_command(label="📝  Editar nota",     command=lambda: self._edit_note_dialog(absp))
        try: m.tk_popup(e.x_root, e.y_root)
        finally: m.grab_release()

    # ── note editing ──────────────────────────────────────────────────────────
    def _edit_note_inline(self, e):
        """Popup a tiny entry widget over the Notas cell."""
        row_id = self._tree.identify_row(e.y)
        if not row_id: return
        self._tree.selection_set(row_id)
        absp = self._selected_abspath()
        if not absp: return

        bbox = self._tree.bbox(row_id, column="#5")
        if not bbox: return
        x, y, w, h = bbox

        cur_note = NOTES.get(absp)
        var = tk.StringVar(value=cur_note)
        entry = tk.Entry(self._tree, textvariable=var,
                         bg=darken(ACCENT, 20), fg=TEXT,
                         insertbackground=TEXT, relief="flat",
                         font=FONT_BODY)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, "end")

        def commit(ev=None):
            NOTES.set(absp, var.get().strip())
            entry.destroy()
            self._populate_table()

        entry.bind("<Return>",  commit)
        entry.bind("<Escape>",  lambda ev: entry.destroy())
        entry.bind("<FocusOut>", commit)

    def _edit_note_dialog(self, absp):
        cur = NOTES.get(absp)
        fname = os.path.basename(absp)
        dlg = tk.Toplevel(self)
        dlg.title("Nota"); dlg.configure(bg=SURFACE)
        dlg.resizable(True, False)
        tk.Label(dlg, text=fname, bg=SURFACE, fg=TEXT,
                 font=FONT_TITLE).pack(padx=18, pady=(12,4), anchor="w")
        e = tk.Text(dlg, width=50, height=4, bg=BORDER, fg=TEXT,
                    insertbackground=TEXT, relief="flat",
                    font=FONT_BODY, wrap="word")
        e.pack(padx=18, pady=4, fill="x")
        e.insert("1.0", cur)
        bf = tk.Frame(dlg, bg=SURFACE); bf.pack(pady=10)
        def save():
            NOTES.set(absp, e.get("1.0","end").strip())
            dlg.destroy(); self._populate_table()
        tk.Button(bf, text="Guardar", bg=ACCENT, fg="#fff",
                  font=FONT_SMALL, bd=0, padx=14, pady=5,
                  cursor="hand2", command=save).pack(side="left", padx=6)
        tk.Button(bf, text="Cancelar", bg=BORDER, fg=TEXT_DIM,
                  font=FONT_SMALL, bd=0, padx=14, pady=5,
                  cursor="hand2", command=dlg.destroy).pack(side="left", padx=6)
        dlg.grab_set()
        # center
        dlg.update_idletasks()
        rx = self.winfo_rootx()+self.winfo_width()//2
        ry = self.winfo_rooty()+self.winfo_height()//2
        dlg.geometry(f"+{rx-dlg.winfo_width()//2}+{ry-dlg.winfo_height()//2}")


# ═══════════════════════════════════════════════════════════════════════════════
#  PANEL  — resize via canvas.coords() so item IDs never change during drag
# ═══════════════════════════════════════════════════════════════════════════════
class Panel:
    MIN_W = MIN_H = 40
    HANDLE = 18
    _STIPPLE = {0.25:"gray25", 0.5:"gray50", 0.75:"gray75", 1.0:""}

    def __init__(self, board, pid, color, alpha, x, y, w, h):
        self.board = board
        self.pid   = pid
        self.color = color
        self.alpha = alpha
        self.x, self.y, self.w, self.h = x, y, w, h
        self._body = self._handle = self._arr = None
        self._items = []
        self._prev_ex = self._prev_ey = 0
        self._mode = "idle"
        self.draw()

    def draw(self):
        """Full redraw — only called on create/color-change/edit-mode toggle."""
        c = self.board.canvas
        for i in self._items:
            try: c.delete(i)
            except: pass
        self._items.clear()
        x,y,w,h = self.x,self.y,self.w,self.h
        st = self._STIPPLE.get(self.alpha,"gray50")

        self._body = c.create_rectangle(x,y,x+w,y+h,
                                         fill=self.color,
                                         outline=lighten(self.color,20),
                                         width=1, stipple=st)
        self._items.append(self._body)

        if self.board.edit_mode:
            hx,hy = x+w-self.HANDLE, y+h-self.HANDLE
            self._handle = c.create_rectangle(hx,hy,x+w,y+h,
                                               fill=lighten(self.color,60),
                                               outline="", stipple="")
            self._arr = c.create_text(x+w-7,y+h-7, text="⤡",
                                       font=("Segoe UI",9,"bold"),
                                       fill=darken(self.color,40), anchor="se")
            self._items += [self._handle, self._arr]

        for item in self._items:
            c.tag_bind(item,"<ButtonPress-1>",  self._on_press)
            c.tag_bind(item,"<B1-Motion>",       self._on_motion)
            c.tag_bind(item,"<ButtonRelease-1>", self._on_release)

        for item in self._items: c.tag_lower(item)
        for g in c.find_withtag("grid"): c.tag_lower(g)

    def _update_coords(self):
        """Move/resize existing canvas items in place — no new IDs."""
        c = self.board.canvas
        x,y,w,h = self.x,self.y,self.w,self.h
        c.coords(self._body, x, y, x+w, y+h)
        if self.board.edit_mode and self._handle and self._arr:
            hx,hy = x+w-self.HANDLE, y+h-self.HANDLE
            c.coords(self._handle, hx, hy, x+w, y+h)
            c.coords(self._arr,    x+w-7, y+h-7)

    def _is_resize_zone(self,ex,ey):
        return (self.x+self.w-self.HANDLE<=ex<=self.x+self.w and
                self.y+self.h-self.HANDLE<=ey<=self.y+self.h)

    def _on_press(self,e):
        if not self.board.edit_mode: return
        self._mode = "resize" if self._is_resize_zone(e.x,e.y) else "move"
        self._prev_ex,self._prev_ey = e.x,e.y
        # raise this panel above other panels but keep tiles/labels on top
        for item in self._items: self.board.canvas.tag_raise(item)
        self.board.enforce_zorder()

    def _on_motion(self,e):
        if not self.board.edit_mode: return
        dx,dy = e.x-self._prev_ex, e.y-self._prev_ey
        self._prev_ex,self._prev_ey = e.x,e.y
        if self._mode=="move":
            self.x+=dx; self.y+=dy
        else:
            self.w = max(self.MIN_W, self.w+dx)
            self.h = max(self.MIN_H, self.h+dy)
        self._update_coords()

    def _on_release(self,e):
        if self.board.edit_mode: self._mode="idle"; self.board.save()

    def to_dict(self):
        return {"kind":"panel","pid":self.pid,"color":self.color,
                "alpha":self.alpha,"x":self.x,"y":self.y,"w":self.w,"h":self.h}


# ═══════════════════════════════════════════════════════════════════════════════
#  FREE LABEL
# ═══════════════════════════════════════════════════════════════════════════════
class FreeLabel:
    def __init__(self, board, lid, text, color, size, bold, x, y):
        self.board = board
        self.lid   = lid
        self.text  = text
        self.color = color
        self.size  = size
        self.bold  = bold
        self.x, self.y = x, y
        self._items   = []
        self._prev_ex = self._prev_ey = 0
        self.draw()

    def _font(self):
        return ("Segoe UI", self.size, "bold" if self.bold else "normal")

    HANDLE = 14
    # item indices
    _I_TXT=0; _I_BOX=1; _I_HRECT=2; _I_HARR=3

    def draw(self):
        """Full redraw — called on create, edit-mode toggle, text/color change."""
        c = self.board.canvas
        for i in self._items:
            try: c.delete(i)
            except: pass
        self._items.clear()
        txt = c.create_text(self.x, self.y, text=self.text,
                             font=self._font(), fill=self.color, anchor="nw")
        self._items = [txt]
        if self.board.edit_mode:
            bbox = c.bbox(txt)
            if bbox:
                bx0,by0,bx1,by1 = bbox[0]-4,bbox[1]-4,bbox[2]+4,bbox[3]+4
                box   = c.create_rectangle(bx0,by0,bx1,by1,
                                            outline=ACCENT, fill="", dash=(4,3))
                hrect = c.create_rectangle(bx1-self.HANDLE, by1-self.HANDLE,
                                            bx1, by1, fill=ACCENT, outline="")
                harr  = c.create_text(bx1-6, by1-6, text="⤡",
                                       font=("Segoe UI",7,"bold"),
                                       fill="#fff", anchor="se")
                self._items += [box, hrect, harr]
        for item in self._items:
            c.tag_bind(item,"<ButtonPress-1>",  self._on_press)
            c.tag_bind(item,"<B1-Motion>",       self._on_motion)
            c.tag_bind(item,"<ButtonRelease-1>", self._on_release)

    def _update_handle(self):
        """Reposition the resize handle + box without recreating items."""
        if len(self._items) < 4: return
        c = self.board.canvas
        bbox = c.bbox(self._items[self._I_TXT])
        if not bbox: return
        bx0,by0,bx1,by1 = bbox[0]-4,bbox[1]-4,bbox[2]+4,bbox[3]+4
        c.coords(self._items[self._I_BOX],   bx0,by0,bx1,by1)
        c.coords(self._items[self._I_HRECT], bx1-self.HANDLE,by1-self.HANDLE,bx1,by1)
        c.coords(self._items[self._I_HARR],  bx1-6, by1-6)

    def _bbox_of_text(self):
        c = self.board.canvas
        for i in self._items:
            if c.type(i) == "text":
                return c.bbox(i)
        return None

    def _is_resize_zone(self,ex,ey):
        bbox = self._bbox_of_text()
        if not bbox: return False
        bx1,by1 = bbox[2]+4, bbox[3]+4
        return (bx1-self.HANDLE<=ex<=bx1 and by1-self.HANDLE<=ey<=by1)

    def _on_press(self,e):
        self._prev_ex,self._prev_ey = e.x,e.y
        self._resize_mode = self.board.edit_mode and self._is_resize_zone(e.x,e.y)
        self._size_start  = self.size
        self._drag_acc    = 0   # accumulated pixels for font scaling
        for i in self._items: self.board.canvas.tag_raise(i)

    def _on_motion(self,e):
        if not self.board.edit_mode: return
        dx = e.x - self._prev_ex
        dy = e.y - self._prev_ey
        self._prev_ex,self._prev_ey = e.x,e.y
        if self._resize_mode:
            # accumulate drag distance; every 6px = 1pt size change
            self._drag_acc += dx + dy
            new_sz = max(6, min(120, self._size_start + self._drag_acc // 6))
            if new_sz != self.size:
                self.size = new_sz
                # update font in-place without recreating item
                self.board.canvas.itemconfig(
                    self._items[self._I_TXT], font=self._font())
                self._update_handle()
        else:
            self.x+=dx; self.y+=dy
            for item in self._items: self.board.canvas.move(item,dx,dy)

    def _on_release(self,e):
        if self.board.edit_mode: self.board.save()

    def to_dict(self):
        return {"kind":"label","lid":self.lid,"text":self.text,
                "color":self.color,"size":self.size,"bold":self.bold,
                "x":self.x,"y":self.y}


# ═══════════════════════════════════════════════════════════════════════════════
#  TILE
# ═══════════════════════════════════════════════════════════════════════════════
class Tile:
    DEF_W, DEF_H = 150, 90

    def __init__(self, board, tid, name, path, color, x, y,
                 w=None, h=None, saved_filters=None, tile_type="browser"):
        self.board = board
        self.tid   = tid
        self.name  = name
        self.path  = path
        self.tile_type = tile_type  # "browser" | "folder" | "file"
        self.color = color
        self.x, self.y = x, y
        self.w = w or self.DEF_W
        self.h = h or self.DEF_H
        self.saved_filters = saved_filters or []
        self._items   = []
        self._prev_ex = self._prev_ey = 0
        self.draw()

    HANDLE = 14  # resize handle size
    # item index constants (must match order in draw())
    _I_SH=0; _I_BODY=1; _I_BAR=2; _I_ICON=3; _I_NAME=4; _I_HRECT=5; _I_HARR=6

    def draw(self):
        """Full redraw — called on create, color change, edit-mode toggle."""
        c = self.board.canvas
        for i in self._items:
            try: c.delete(i)
            except: pass
        self._items.clear()
        x,y,w,h = self.x,self.y,self.w,self.h
        fg = contrasting(self.color)

        sh   = c.create_rectangle(x+4,y+4,x+w+4,y+h+4,
                                   fill="#000000",outline="",stipple="gray50")
        body = c.create_rectangle(x,y,x+w,y+h,
                                   fill=self.color,
                                   outline=darken(self.color,20),width=1.5)
        bar  = c.create_rectangle(x,y,x+w,y+4,
                                   fill=darken(self.color,50),outline="")
        # icon — type-dependent glyph, top-left
        icon_sz = max(10, min(22, h//4))
        tt = getattr(self, "tile_type", "browser")
        glyph = {"browser":"🗀", "folder":"📁", "file":"📄"}.get(tt, "🗀")
        folder_icon = c.create_text(x+5, y, text=glyph,
                                     font=("Segoe UI", icon_sz),
                                     fill=darken(fg,20), anchor="nw")
        fsz = max(9, min(16, w//10))
        nl  = c.create_text(x+w//2, y+h//2+8, text=self.name,
                             font=("Segoe UI",fsz,"bold"),
                             fill=fg, anchor="center", width=w-40)
        if self.board.edit_mode:
            hrect = c.create_rectangle(x+w-self.HANDLE, y+h-self.HANDLE,
                                        x+w, y+h,
                                        fill=darken(self.color,30), outline="")
            harr  = c.create_text(x+w-6, y+h-6, text="⤡",
                                   font=("Segoe UI",8,"bold"),
                                   fill=fg, anchor="se")
            self._items = [sh,body,bar,folder_icon,nl,hrect,harr]
        else:
            self._items = [sh,body,bar,folder_icon,nl]

        for item in self._items:
            c.tag_bind(item,"<ButtonPress-1>",  self._on_press)
            c.tag_bind(item,"<B1-Motion>",       self._on_motion)
            c.tag_bind(item,"<ButtonRelease-1>", self._on_release)
            c.tag_bind(item,"<Enter>",           self._on_enter)
            c.tag_bind(item,"<Leave>",           self._on_leave)

    def _update_coords(self):
        """Reposition all canvas items without recreating them (preserves IDs)."""
        c = self.board.canvas
        x,y,w,h = self.x,self.y,self.w,self.h
        fg = contrasting(self.color)
        c.coords(self._items[self._I_SH],   x+4,y+4,x+w+4,y+h+4)
        c.coords(self._items[self._I_BODY], x,y,x+w,y+h)
        c.coords(self._items[self._I_BAR],  x,y,x+w,y+4)
        # icon stays top-left
        icon_sz = max(10, min(22, h//4))
        c.coords(self._items[self._I_ICON], x+5, y)
        c.itemconfig(self._items[self._I_ICON], font=("Segoe UI",icon_sz))
        # name centred
        fsz = max(9, min(16, w//10))
        c.coords(self._items[self._I_NAME], x+w//2, y+h//2+8)
        c.itemconfig(self._items[self._I_NAME],
                     font=("Segoe UI",fsz,"bold"), width=w-40)
        if self.board.edit_mode and len(self._items) > 5:
            c.coords(self._items[self._I_HRECT],
                     x+w-self.HANDLE, y+h-self.HANDLE, x+w, y+h)
            c.coords(self._items[self._I_HARR], x+w-6, y+h-6)

    def _on_enter(self,e):
        if not self.board.edit_mode:
            self.board.canvas.itemconfig(self._items[self._I_BODY],
                                          outline=ACCENT,width=2.5)

    def _on_leave(self,e):
        self.board.canvas.itemconfig(self._items[self._I_BODY],
                                     outline=darken(self.color,20),width=1.5)

    def _is_resize_zone(self,ex,ey):
        return (self.x+self.w-self.HANDLE<=ex<=self.x+self.w and
                self.y+self.h-self.HANDLE<=ey<=self.y+self.h)

    def _on_press(self,e):
        self._prev_ex,self._prev_ey = e.x,e.y
        self._resize_mode = self.board.edit_mode and self._is_resize_zone(e.x,e.y)
        for i in self._items: self.board.canvas.tag_raise(i)

    def _on_motion(self,e):
        if not self.board.edit_mode: return
        dx,dy = e.x-self._prev_ex, e.y-self._prev_ey
        self._prev_ex,self._prev_ey = e.x,e.y
        if self._resize_mode:
            self.w = max(80, self.w+dx)
            self.h = max(60, self.h+dy)
            self._update_coords()   # reposition without recreating items
        else:
            self.x+=dx; self.y+=dy
            for item in self._items: self.board.canvas.move(item,dx,dy)

    def _on_release(self,e):
        if not self.board.edit_mode:
            tt = getattr(self, "tile_type", "browser")
            if tt == "folder":
                if os.path.isdir(self.path): open_path(self.path)
                else: messagebox.showerror("Error", "Carpeta no encontrada:\n"+self.path)
            elif tt == "file":
                if os.path.isfile(self.path): open_path(self.path)
                else: messagebox.showerror("Error", "Archivo no encontrado:\n"+self.path)
            else:
                self.board.open_browser(self)
        else: self.board.save()

    def to_dict(self):
        return {"kind":"tile","tid":self.tid,"name":self.name,
                "path":self.path,"color":self.color,
                "tile_type": getattr(self,"tile_type","browser"),
                "x":self.x,"y":self.y,"w":self.w,"h":self.h,
                "saved_filters":self.saved_filters,
                "active_chip":  getattr(self,"_active_chip",""),
                "browser_rev":  getattr(self,"_browser_rev",False),
                "browser_type": getattr(self,"_browser_type","all"),
                "browser_sort_col": getattr(self,"_browser_sort_col","Archivo"),
                "browser_sort_rev": getattr(self,"_browser_sort_rev",False),
                "browser_exclude":  getattr(self,"_browser_exclude",[])}


# ═══════════════════════════════════════════════════════════════════════════════
#  CHECK ITEM  (interactive checkbox on the canvas)
# ═══════════════════════════════════════════════════════════════════════════════
class CheckItem:
    BOX   = 18   # checkbox box size px
    R     = 3    # corner radius

    def __init__(self, board, cid, label, checked, color, x, y):
        self.board   = board
        self.cid     = cid
        self.label   = label
        self.checked = checked
        self.color   = color
        self.x, self.y = x, y
        self._items    = []
        self._prev_ex = self._prev_ey = 0
        self.draw()

    def draw(self):
        c = self.board.canvas
        for i in self._items:
            try: c.delete(i)
            except: pass
        self._items.clear()

        x, y = self.x, self.y
        B = self.BOX

        # box background
        box = c.create_rectangle(x, y, x+B, y+B,
                                  fill=SURFACE, outline=self.color, width=2)
        self._items.append(box)

        # checkmark if checked
        if self.checked:
            # draw a tick: two lines forming a ✓
            m1 = c.create_line(x+3, y+B//2+1, x+B//2-1, y+B-4,
                                fill=self.color, width=2.5, capstyle="round")
            m2 = c.create_line(x+B//2-1, y+B-4, x+B-3, y+4,
                                fill=self.color, width=2.5, capstyle="round")
            self._items += [m1, m2]

        # label text
        txt = c.create_text(x+B+8, y+B//2, text=self.label,
                             font=("Segoe UI", 10),
                             fill=TEXT if not self.checked else TEXT_DIM,
                             anchor="w")
        if self.checked:
            # strikethrough — draw a line through the text bbox
            bbox = c.bbox(txt)
            if bbox:
                mid_y = (bbox[1]+bbox[3])//2
                stk = c.create_line(bbox[0], mid_y, bbox[2], mid_y,
                                    fill=TEXT_DIM, width=1)
                self._items.append(stk)
        self._items.append(txt)

        # edit-mode handle
        if self.board.edit_mode:
            bbox = c.bbox(txt) or (x, y, x+B+60, y+B)
            box2 = c.create_rectangle(x-3, y-3, bbox[2]+6, y+B+3,
                                       outline=ACCENT, fill="", dash=(3,3))
            self._items.append(box2)

        for item in self._items:
            c.tag_bind(item, "<ButtonPress-1>",  self._on_press)
            c.tag_bind(item, "<B1-Motion>",       self._on_drag)
            c.tag_bind(item, "<ButtonRelease-1>", self._on_release)

    def _on_press(self, e):
        self._prev_ex, self._prev_ey = e.x, e.y
        self._moved = False
        for i in self._items: self.board.canvas.tag_raise(i)

    def _on_drag(self, e):
        if not self.board.edit_mode: return
        dx = e.x - self._prev_ex; dy = e.y - self._prev_ey
        self._prev_ex, self._prev_ey = e.x, e.y
        if abs(dx) > 1 or abs(dy) > 1: self._moved = True
        self.x += dx; self.y += dy
        for item in self._items: self.board.canvas.move(item, dx, dy)

    def _on_release(self, e):
        if self.board.edit_mode:
            self.board.save()
        else:
            if not getattr(self, "_moved", False):
                # toggle check
                self.checked = not self.checked
                self.draw()
                self.board.save()

    def to_dict(self):
        return {"kind":"check","cid":self.cid,"label":self.label,
                "checked":self.checked,"color":self.color,
                "x":self.x,"y":self.y}


# ═══════════════════════════════════════════════════════════════════════════════
#  DIALOGS
# ═══════════════════════════════════════════════════════════════════════════════
class BaseDialog(tk.Toplevel):
    def __init__(self,master,title):
        super().__init__(master)
        self.title(title); self.configure(bg=SURFACE)
        self.resizable(False,False); self.result=None

    def _center(self):
        self.update_idletasks()
        mw=self.master.winfo_rootx()+self.master.winfo_width()//2
        mh=self.master.winfo_rooty()+self.master.winfo_height()//2
        w,h=self.winfo_width(),self.winfo_height()
        self.geometry(f"+{mw-w//2}+{mh-h//2}")

    def _entry(self,parent,width=26):
        e=tk.Entry(parent,width=width,bg=BORDER,fg=TEXT,
                   insertbackground=TEXT,relief="flat",font=FONT_BODY)
        e.configure(highlightthickness=1,highlightbackground=BORDER,
                    highlightcolor=ACCENT)
        return e

    def _lbl(self,parent,text,row):
        tk.Label(parent,text=text,bg=SURFACE,fg=TEXT_DIM,font=FONT_SMALL)\
          .grid(row=row,column=0,sticky="w",padx=18,pady=5)

    def _color_row(self,parent,row,initial,presets):
        self._chosen_color=initial
        self._lbl(parent,"Color",row)
        cf=tk.Frame(parent,bg=SURFACE); cf.grid(row=row,column=1,padx=18,pady=4)
        for i,col in enumerate(presets):
            tk.Button(cf,bg=col,width=2,height=1,bd=0,cursor="hand2",
                      command=lambda c=col:self._pick(c))\
              .grid(row=i//6,column=i%6,padx=2,pady=2)
        tk.Button(cf,text="+",bg=BORDER,fg=TEXT,bd=0,width=2,
                  cursor="hand2",command=self._custom)\
          .grid(row=1,column=6,padx=2,pady=2)
        self._sw=tk.Label(cf,bg=initial,width=4,height=1)
        self._sw.grid(row=0,column=6,padx=2)

    def _pick(self,c): self._chosen_color=c; self._sw.configure(bg=c)

    def _custom(self):
        _,hx=colorchooser.askcolor(color=self._chosen_color)
        if hx: self._pick(hx)

    def _btns(self,parent,row,save_cmd):
        bf=tk.Frame(parent,bg=SURFACE)
        bf.grid(row=row,column=0,columnspan=2,pady=14)
        tk.Button(bf,text="Cancelar",bg=BORDER,fg=TEXT_DIM,font=FONT_SMALL,
                  bd=0,padx=14,pady=6,cursor="hand2",command=self.destroy)\
          .pack(side="left",padx=6)
        tk.Button(bf,text="Guardar",bg=ACCENT,fg="#fff",font=FONT_TITLE,
                  bd=0,padx=14,pady=6,cursor="hand2",command=save_cmd)\
          .pack(side="left",padx=6)


class TileDialog(BaseDialog):
    def __init__(self, master, title="Nuevo acceso", tile=None, tile_type="browser"):
        super().__init__(master, title)
        self._chosen_color = tile.color if tile else TILE_COLORS[0]
        self._tile_type    = getattr(tile, "tile_type", tile_type) if tile else tile_type

        row = 0
        # type selector — only when creating new tile
        if tile is None:
            self._lbl(self, "Tipo", row)
            tf = tk.Frame(self, bg=SURFACE)
            tf.grid(row=row, column=1, padx=18, pady=6, sticky="w")
            self._type_var = tk.StringVar(value=self._tile_type)
            for val, lbl_text in [
                ("browser", "🗀  Explorar directorio"),
                ("folder",  "📁  Abrir carpeta"),
                ("file",    "📄  Abrir archivo"),
            ]:
                tk.Radiobutton(tf, text=lbl_text, variable=self._type_var,
                               value=val, bg=SURFACE, fg=TEXT,
                               selectcolor=BORDER, activebackground=SURFACE,
                               font=FONT_BODY, command=self._on_type_change)                  .pack(anchor="w", pady=1)
            row += 1
        else:
            self._type_var = tk.StringVar(value=self._tile_type)

        # name
        self._lbl(self, "Nombre", row)
        self.ename = self._entry(self)
        self.ename.grid(row=row, column=1, padx=18, pady=5)
        if tile: self.ename.insert(0, tile.name)
        row += 1

        # path
        self._path_lbl_widget = tk.Label(self, text=self._path_label(),
                                          bg=SURFACE, fg=TEXT_DIM, font=FONT_SMALL)
        self._path_lbl_widget.grid(row=row, column=0, sticky="w", padx=18, pady=5)
        pf = tk.Frame(self, bg=SURFACE)
        pf.grid(row=row, column=1, padx=18, pady=5)
        self.epath = self._entry(pf, 22)
        self.epath.pack(side="left")
        # auto-strip surrounding quotes on paste or focus-out
        def _clean_path(e=None):
            v = self.epath.get().strip()
            if len(v) >= 2 and v[0] in ('"',"'") and v[-1] == v[0]:
                self.epath.delete(0, "end")
                self.epath.insert(0, v[1:-1].strip())
        self.epath.bind("<FocusOut>",  _clean_path)
        self.epath.bind("<<Paste>>",   lambda e: self.epath.after(10, _clean_path))
        if tile: self.epath.insert(0, tile.path)
        tk.Button(pf, text="…", bg=BORDER, fg=TEXT, font=FONT_SMALL, bd=0,
                  padx=6, cursor="hand2", command=self._browse)          .pack(side="left", padx=(4,0))
        row += 1

        # size
        self._lbl(self, "Tamaño tile", row)
        sf = tk.Frame(self, bg=SURFACE)
        sf.grid(row=row, column=1, padx=18, pady=5, sticky="w")
        tk.Label(sf,text="Ancho",bg=SURFACE,fg=TEXT_DIM,font=FONT_SMALL).pack(side="left")
        self._wv = tk.IntVar(value=tile.w if tile else Tile.DEF_W)
        tk.Spinbox(sf,from_=80,to=400,textvariable=self._wv,width=5,
                   bg=BORDER,fg=TEXT,insertbackground=TEXT,
                   relief="flat",font=FONT_BODY).pack(side="left",padx=(4,10))
        tk.Label(sf,text="Alto",bg=SURFACE,fg=TEXT_DIM,font=FONT_SMALL).pack(side="left")
        self._hv = tk.IntVar(value=tile.h if tile else Tile.DEF_H)
        tk.Spinbox(sf,from_=60,to=300,textvariable=self._hv,width=5,
                   bg=BORDER,fg=TEXT,insertbackground=TEXT,
                   relief="flat",font=FONT_BODY).pack(side="left",padx=(4,0))
        row += 1

        self._color_row(self, row, self._chosen_color, TILE_COLORS)
        row += 1
        self._btns(self, row, self._save)
        self.grab_set(); self.lift(); self._center()

    def _path_label(self):
        t = self._type_var.get() if hasattr(self, "_type_var") else self._tile_type
        return "Archivo" if t == "file" else "Carpeta"

    def _on_type_change(self):
        self._tile_type = self._type_var.get()
        self._path_lbl_widget.configure(text=self._path_label())

    def _browse(self):
        t = self._type_var.get() if hasattr(self, "_type_var") else self._tile_type
        if t == "file":
            p = filedialog.askopenfilename(title="Seleccionar archivo")
        else:
            p = filedialog.askdirectory(title="Seleccionar carpeta")
        if p:
            self.epath.delete(0, "end")
            self.epath.insert(0, p)

    def _save(self):
        n = self.ename.get().strip()
        # strip surrounding quotes (Windows copies paths with quotes sometimes)
        p = self.epath.get().strip().strip('"').strip("'").strip()
        t = self._type_var.get() if hasattr(self, "_type_var") else self._tile_type
        if not n:
            messagebox.showwarning("Falta nombre","Ingresa un nombre.",parent=self); return
        if not p:
            label = "archivo" if t == "file" else "carpeta"
            messagebox.showwarning("Falta ruta",f"Selecciona un {label}.",parent=self); return
        self.result = {"name":n,"path":p,"color":self._chosen_color,
                       "w":self._wv.get(),"h":self._hv.get(),"tile_type":t}
        self.destroy()



class PanelDialog(BaseDialog):
    def __init__(self,master,panel=None):
        super().__init__(master,"Editar panel" if panel else "Nuevo panel")
        self._chosen_color=panel.color if panel else PANEL_PRESETS[0]
        self._color_row(self,0,self._chosen_color,PANEL_PRESETS)
        self._lbl(self,"Opacidad",1)
        self._av=tk.DoubleVar(value=panel.alpha if panel else 0.5)
        sf=tk.Frame(self,bg=SURFACE); sf.grid(row=1,column=1,padx=18,pady=5,sticky="w")
        for lbl,val in [("25%",0.25),("50%",0.5),("75%",0.75),("100%",1.0)]:
            tk.Radiobutton(sf,text=lbl,variable=self._av,value=val,
                           bg=SURFACE,fg=TEXT,selectcolor=BORDER,
                           activebackground=SURFACE,font=FONT_SMALL)\
              .pack(side="left",padx=6)
        self._btns(self,2,self._save)
        self.grab_set(); self.lift(); self._center()

    def _save(self):
        self.result={"color":self._chosen_color,"alpha":self._av.get()}; self.destroy()


class LabelDialog(BaseDialog):
    def __init__(self,master,lbl=None):
        super().__init__(master,"Editar texto" if lbl else "Nuevo texto")
        TC=["#ffffff","#e8e6f0","#cccccc","#7c6aff","#ff6a9e","#00d4aa",
            "#ff9f43","#ffcc00","#54a0ff","#ff6b6b","#a29bfe","#000000"]
        self._chosen_color=lbl.color if lbl else "#ffffff"
        self._lbl(self,"Texto",0)
        self.etxt=self._entry(self,28); self.etxt.grid(row=0,column=1,padx=18,pady=5)
        if lbl: self.etxt.insert(0,lbl.text)
        self._lbl(self,"Tamaño",1)
        sf=tk.Frame(self,bg=SURFACE); sf.grid(row=1,column=1,padx=18,pady=5,sticky="w")
        self._sv=tk.IntVar(value=lbl.size if lbl else 20)
        tk.Spinbox(sf,from_=8,to=120,textvariable=self._sv,width=5,
                   bg=BORDER,fg=TEXT,insertbackground=TEXT,
                   relief="flat",font=FONT_BODY).pack(side="left")
        tk.Label(sf,text="pt",bg=SURFACE,fg=TEXT_DIM,font=FONT_SMALL).pack(side="left",padx=4)
        self._lbl(self,"Negrita",2)
        self._bv=tk.BooleanVar(value=lbl.bold if lbl else False)
        tk.Checkbutton(self,variable=self._bv,bg=SURFACE,fg=TEXT,
                       selectcolor=BORDER,activebackground=SURFACE)\
          .grid(row=2,column=1,sticky="w",padx=18)
        self._color_row(self,3,self._chosen_color,TC)
        self._btns(self,4,self._save)
        self.grab_set(); self.lift(); self._center()

    def _save(self):
        t=self.etxt.get().strip()
        if not t: messagebox.showwarning("Falta texto","Escribe algo.",parent=self); return
        self.result={"text":t,"color":self._chosen_color,
                     "size":self._sv.get(),"bold":self._bv.get()}; self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  BOARD STATE  — one per tab
# ═══════════════════════════════════════════════════════════════════════════════
class BoardState:
    """All data for one pizarra tab."""
    def __init__(self):
        self.name   = "Pizarra"
        self.tiles:  list = []
        self.panels: list = []
        self.labels: list = []
        self.checks: list = []

    def to_dict(self):
        return {
            "name":   self.name,
            "tiles":  [t.to_dict() for t in self.tiles],
            "panels": [p.to_dict() for p in self.panels],
            "labels": [l.to_dict() for l in self.labels],
            "checks": [c.to_dict() for c in self.checks],
        }

# ═══════════════════════════════════════════════════════════════════════════════
#  CUSTOM TAB BAR
# ═══════════════════════════════════════════════════════════════════════════════
class TabBar(tk.Frame):
    """Custom tab bar with rename-on-double-click and add/close buttons."""
    TAB_H   = 34
    TAB_PAD = 18

    def __init__(self, master, on_switch, on_add, on_close, on_rename):
        super().__init__(master, bg=SURFACE, height=self.TAB_H)
        self.pack_propagate(False)
        self._on_switch = on_switch
        self._on_add    = on_add
        self._on_close  = on_close
        self._on_rename = on_rename
        self._tabs      = []   # list of {"name":str, "frame":Frame, "label":Label, "close":Button}
        self._active    = -1
        self._edit_entry = None

        # "+" add button at the right
        self._add_btn = tk.Button(self, text="＋", bg=SURFACE, fg=TEXT_DIM,
                                   font=("Segoe UI",12), bd=0, padx=10,
                                   cursor="hand2", command=self._on_add,
                                   activebackground=BORDER,
                                   activeforeground=TEXT)
        self._add_btn.pack(side="right", fill="y")

        self._inner = tk.Frame(self, bg=SURFACE)
        self._inner.pack(side="left", fill="both", expand=True)

    def add_tab(self, name, switch=True):
        idx = len(self._tabs)
        frm = tk.Frame(self._inner, bg=SURFACE, cursor="hand2")
        frm.pack(side="left", fill="y", padx=(0,2))

        lbl = tk.Label(frm, text=name, bg=SURFACE, fg=TEXT_DIM,
                        font=FONT_BODY, padx=self.TAB_PAD, pady=6)
        lbl.pack(side="left", fill="y")

        cls = tk.Button(frm, text="×", bg=SURFACE, fg=TEXT_DIM,
                         font=("Segoe UI",9), bd=0, padx=4,
                         cursor="hand2",
                         command=lambda i=idx: self._on_close(i))
        cls.pack(side="left", fill="y", padx=(0,4))

        tab = {"name": name, "frame": frm, "label": lbl, "close": cls}
        self._tabs.append(tab)

        # bindings
        for w in (frm, lbl):
            w.bind("<Button-1>",       lambda e, i=idx: self._switch(i))
            w.bind("<Double-Button-1>", lambda e, i=idx: self._start_rename(i))

        if switch:
            self._switch(idx)
        return idx

    def rename_tab(self, idx, name):
        if 0 <= idx < len(self._tabs):
            self._tabs[idx]["name"]  = name
            self._tabs[idx]["label"].configure(text=name)

    def remove_tab(self, idx):
        if idx < 0 or idx >= len(self._tabs): return
        self._tabs[idx]["frame"].destroy()
        self._tabs.pop(idx)
        # re-bind close buttons with new indices
        for i, tab in enumerate(self._tabs):
            tab["close"].configure(command=lambda j=i: self._on_close(j))
            for w in (tab["frame"], tab["label"]):
                w.bind("<Button-1>",       lambda e, j=i: self._switch(j))
                w.bind("<Double-Button-1>", lambda e, j=i: self._start_rename(j))
        new_active = min(self._active, len(self._tabs)-1)
        self._active = -1
        if new_active >= 0:
            self._switch(new_active)

    def _switch(self, idx):
        if self._active == idx: return
        # deactivate old
        if 0 <= self._active < len(self._tabs):
            t = self._tabs[self._active]
            t["frame"].configure(bg=SURFACE)
            t["label"].configure(bg=SURFACE, fg=TEXT_DIM,
                                  font=FONT_BODY)
            t["close"].configure(bg=SURFACE)
        self._active = idx
        t = self._tabs[idx]
        t["frame"].configure(bg=BG)
        t["label"].configure(bg=BG, fg=TEXT,
                              font=("Segoe UI",9,"bold"))
        t["close"].configure(bg=BG)
        self._on_switch(idx)

    def _start_rename(self, idx):
        """Show inline entry over the tab label."""
        if self._edit_entry:
            self._edit_entry.destroy()
            self._edit_entry = None
        tab = self._tabs[idx]
        lbl = tab["label"]
        var = tk.StringVar(value=tab["name"])
        e = tk.Entry(lbl.master, textvariable=var, width=14,
                     bg=BORDER, fg=TEXT, insertbackground=TEXT,
                     relief="flat", font=FONT_BODY)
        e.place(in_=lbl, x=0, y=0, relwidth=1, relheight=1)
        e.focus_set(); e.select_range(0,"end")
        self._edit_entry = e
        self._rename_committed = False

        def commit(ev=None):
            if self._rename_committed: return
            self._rename_committed = True
            new_name = var.get().strip() or tab["name"]
            self._edit_entry = None
            # unbind global click before destroying
            try: self.winfo_toplevel().unbind("<Button-1>")
            except: pass
            e.destroy()
            self.rename_tab(idx, new_name)
            self._on_rename(idx, new_name)

        def cancel(ev=None):
            if self._rename_committed: return
            self._rename_committed = True
            self._edit_entry = None
            try: self.winfo_toplevel().unbind("<Button-1>")
            except: pass
            e.destroy()

        def on_global_click(ev):
            # commit if click is outside the entry widget
            try:
                ex = e.winfo_rootx(); ey = e.winfo_rooty()
                ew = e.winfo_width();  eh = e.winfo_height()
                if not (ex <= ev.x_root <= ex+ew and ey <= ev.y_root <= ey+eh):
                    commit()
            except tk.TclError:
                pass

        e.bind("<Return>", commit)
        e.bind("<Escape>", lambda ev: cancel())
        # bind global click on root to detect outside clicks
        self.winfo_toplevel().bind("<Button-1>", on_global_click, add="+")

    @property
    def active(self): return self._active


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════════════════════
class FolderBoard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FolderBoard"); self.configure(bg=BG)
        self.geometry("1200x740"); self.minsize(700,480)
        # Remove native title bar — use custom one

        self.edit_mode = False
        self._browser  = None
        self._next_id  = 1
        self._boards: list[BoardState] = []   # one per tab
        self._cur: BoardState | None   = None  # active board
        self._build_ui()
        self.load()
        # Center on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        w,h = 1200,740
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # shortcuts to active board's lists
    @property
    def tiles(self):  return self._cur.tiles  if self._cur else []
    @property
    def panels(self): return self._cur.panels if self._cur else []
    @property
    def labels(self): return self._cur.labels if self._cur else []
    @property
    def checks(self): return self._cur.checks if self._cur else []

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── app bar ──
        bar=tk.Frame(self,bg=SURFACE,height=44)
        bar.pack(fill="x",side="top"); bar.pack_propagate(False)
        tk.Label(bar,text="◈  FolderBoard",bg=SURFACE,fg=TEXT,
                 font=("Segoe UI",13,"bold")).pack(side="left",padx=20)
        self._rc=tk.Frame(bar,bg=SURFACE); self._rc.pack(side="right",padx=16)
        self.edit_btn=tk.Button(self._rc,text="✏  Editar",bg=BORDER,fg=TEXT_DIM,
                                 font=FONT_SMALL,bd=0,padx=12,pady=5,
                                 cursor="hand2",command=self.toggle_edit)
        self.edit_btn.pack(side="left",padx=4)
        self.btn_tile  = self._mkbtn("＋ Tile",  self.add_tile,  ACCENT)
        self.btn_panel = self._mkbtn("▭ Panel",  self.add_panel, "#3d3a5e")
        self.btn_label = self._mkbtn("T Texto",  self.add_label, "#2e3a3e")
        self.btn_check = self._mkbtn("☑ Check",  self.add_check, "#2a3a2a")

        # tab bar
        self._tabbar = TabBar(self,
                               on_switch=self._switch_board,
                               on_add=self._new_board,
                               on_close=self._close_board,
                               on_rename=self._rename_board)
        self._tabbar.pack(fill="x", side="top")

        # status
        self.status=tk.Label(self,bg=BG,fg=TEXT_DIM,font=FONT_SMALL,
                              text="Modo vista  —  click en un tile para explorar",anchor="w")
        self.status.pack(fill="x",padx=20,pady=(4,0))

        # canvas container
        self.cf=tk.Frame(self,bg=BG)
        self.cf.pack(fill="both",expand=True,pady=4)
        self.canvas=tk.Canvas(self.cf,bg=BG,highlightthickness=0)
        self.canvas.place(relx=0,rely=0,relwidth=1,relheight=1)
        self._draw_grid()
        self.canvas.bind("<Configure>",lambda e:self._draw_grid())
        self.canvas.bind("<Button-3>",self._ctx_menu)
        self.canvas.bind("<Button-1>",self._canvas_click)

    def _mkbtn(self,text,cmd,bg):
        return tk.Button(self._rc,text=text,bg=bg,fg=TEXT,
                         font=FONT_SMALL,bd=0,padx=11,pady=5,
                         cursor="hand2",command=cmd)

    def _draw_grid(self):
        self.canvas.delete("grid")
        w=self.canvas.winfo_width() or 1200
        h=self.canvas.winfo_height() or 700
        for x in range(0,w,36): self.canvas.create_line(x,0,x,h,fill="#1a1a22",tags="grid")
        for y in range(0,h,36): self.canvas.create_line(0,y,w,y,fill="#1a1a22",tags="grid")
        for i in self.canvas.find_withtag("grid"): self.canvas.tag_lower(i)

    # ── board / tab management ────────────────────────────────────────────────
    def _new_board(self, name="Pizarra", switch=True):
        bs = BoardState()
        bs.name = name
        self._boards.append(bs)
        self._tabbar.add_tab(name, switch=switch)
        if switch:
            self._cur = bs
        return bs

    def _switch_board(self, idx):
        self.close_browser()
        # hide all canvas items of current board
        if self._cur:
            for t in self._cur.tiles:
                for i in t._items: self.canvas.itemconfigure(i, state="hidden")
            for p in self._cur.panels:
                for i in p._items: self.canvas.itemconfigure(i, state="hidden")
            for l in self._cur.labels:
                for i in l._items: self.canvas.itemconfigure(i, state="hidden")
            for ck in self._cur.checks:
                for i in ck._items: self.canvas.itemconfigure(i, state="hidden")

        self._cur = self._boards[idx]

        # show items of new board
        for t in self._cur.tiles:
            for i in t._items: self.canvas.itemconfigure(i, state="normal")
        for p in self._cur.panels:
            for i in p._items: self.canvas.itemconfigure(i, state="normal")
        for l in self._cur.labels:
            for i in l._items: self.canvas.itemconfigure(i, state="normal")
        for ck in self._cur.checks:
            for i in ck._items: self.canvas.itemconfigure(i, state="normal")

        self.enforce_zorder()

    def _close_board(self, idx):
        if len(self._boards) <= 1:
            messagebox.showinfo("Info","Debe haber al menos una pizarra.",parent=self)
            return
        if not messagebox.askyesno("Eliminar pizarra",
                                    f"¿Eliminar «{self._boards[idx].name}»?",
                                    parent=self):
            return
        bs = self._boards[idx]
        # delete all canvas items
        for t in bs.tiles:
            for i in t._items:
                try: self.canvas.delete(i)
                except: pass
        for p in bs.panels:
            for i in p._items:
                try: self.canvas.delete(i)
                except: pass
        for l in bs.labels:
            for i in l._items:
                try: self.canvas.delete(i)
                except: pass
        for ck in bs.checks:
            for i in ck._items:
                try: self.canvas.delete(i)
                except: pass
        self._boards.pop(idx)
        self._tabbar.remove_tab(idx)   # will call _switch_board on new active
        self.save()

    def _rename_board(self, idx, name):
        self._boards[idx].name = name
        self.save()

    # ── browser ───────────────────────────────────────────────────────────────
    def open_browser(self,tile):
        if not os.path.isdir(tile.path):
            messagebox.showerror("Error",f"Carpeta no encontrada:\n{tile.path}"); return
        self.close_browser()
        cw=self.cf.winfo_width() or 1000
        ch=self.cf.winfo_height() or 660
        bw=max(600,int(cw*0.78)); bh=max(420,int(ch*0.80))
        bx=(cw-bw)//2; by=(ch-bh)//2
        self._browser=FileBrowser(self.cf,tile,close_cb=self.close_browser)
        self._browser.place(x=bx,y=by,width=bw,height=bh)
        self._browser.lift()

    def close_browser(self):
        if self._browser: self._browser.destroy(); self._browser=None

    def _canvas_click(self, e):
        """Close browser when clicking outside it on the canvas."""
        if not self._browser: return
        bx = self._browser.winfo_x(); by = self._browser.winfo_y()
        bw = self._browser.winfo_width(); bh = self._browser.winfo_height()
        if not (bx <= e.x <= bx+bw and by <= e.y <= by+bh):
            self.close_browser()

    def _open_file_for_tile(self, tile):
        """Open a file picker starting at tile's folder path."""
        init = tile.path if os.path.isdir(tile.path) else os.path.expanduser("~")
        path = filedialog.askopenfilename(initialdir=init,
                                          title=f"Abrir archivo — {tile.name}")
        if path:
            open_path(path)

    # ── edit mode ─────────────────────────────────────────────────────────────
    def toggle_edit(self):
        self.close_browser()
        self.edit_mode=not self.edit_mode
        if self.edit_mode:
            self.edit_btn.configure(bg=ACCENT,fg="#fff",text="✔  Listo")
            for b in (self.btn_tile,self.btn_panel,self.btn_label,self.btn_check): b.pack(side="left",padx=3)
            self.status.configure(text="Modo edición  —  arrastra · clic derecho · ⤡ redimensionar")
            self.canvas.configure(cursor="fleur")
        else:
            self.edit_btn.configure(bg=BORDER,fg=TEXT_DIM,text="✏  Editar")
            for b in (self.btn_tile,self.btn_panel,self.btn_label,self.btn_check): b.pack_forget()
            self.status.configure(text="Modo vista  —  click en un tile para explorar")
            self.canvas.configure(cursor="")
        for p in self.panels: p.draw()
        for l in self.labels: l.draw()
        for ck in self.checks: ck.draw()
        self.enforce_zorder()

    def enforce_zorder(self):
        c = self.canvas
        for p in self.panels:
            for item in p._items: c.tag_lower(item)
        for g in c.find_withtag("grid"): c.tag_lower(g)
        for l in self.labels:
            for item in l._items: c.tag_raise(item)
        for ck in self.checks:
            for item in ck._items: c.tag_raise(item)
        for t in self.tiles:
            for item in t._items: c.tag_raise(item)

    # ── create ────────────────────────────────────────────────────────────────
    def _nid(self): i=self._next_id; self._next_id+=1; return i
    def _pos(self,col,ox=40,oy=60,sx=180,sy=130):
        n=len(col); return ox+(n%5)*sx, oy+(n//5)*sy

    def add_tile(self,x=None,y=None,tile_type="browser"):
        if not self._cur: return
        dlg=TileDialog(self,tile_type=tile_type); self.wait_window(dlg)
        if not dlg.result: return
        tx,ty=(x,y) if x is not None else self._pos(self.tiles)
        t=Tile(self,self._nid(),dlg.result["name"],dlg.result["path"],
               dlg.result["color"],tx,ty,dlg.result["w"],dlg.result["h"],
               tile_type=dlg.result.get("tile_type","browser"))
        self._cur.tiles.append(t); self.save(); self.enforce_zorder()

    def add_panel(self,x=None,y=None):
        if not self._cur: return
        dlg=PanelDialog(self); self.wait_window(dlg)
        if not dlg.result: return
        px,py=(x,y) if x is not None else self._pos(self.panels,60,80,220,160)
        p=Panel(self,self._nid(),dlg.result["color"],dlg.result["alpha"],px,py,200,120)
        self._cur.panels.append(p); self.save(); self.enforce_zorder()

    def add_label(self,x=None,y=None):
        if not self._cur: return
        dlg=LabelDialog(self); self.wait_window(dlg)
        if not dlg.result: return
        lx,ly=(x,y) if x is not None else self._pos(self.labels,50,50,180,80)
        l=FreeLabel(self,self._nid(),dlg.result["text"],dlg.result["color"],
                    dlg.result["size"],dlg.result["bold"],lx,ly)
        self._cur.labels.append(l); self.save(); self.enforce_zorder()


    def add_check(self,x=None,y=None):
        if not self._cur: return
        lx,ly=(x,y) if x is not None else self._pos(self.checks,60,200,220,40)
        ck=CheckItem(self,self._nid(),"Nueva tarea",False,ACCENT,lx,ly)
        self._cur.checks.append(ck); self.save(); self.enforce_zorder()

    def del_check(self,ck):
        if not messagebox.askyesno("Eliminar","¿Eliminar este checkbox?",parent=self): return
        for i in ck._items:
            try: self.canvas.delete(i)
            except: pass
        self._cur.checks.remove(ck); self.save()

    def edit_check(self,ck):
        import tkinter.simpledialog as sd
        new_label = sd.askstring("Editar checkbox","Etiqueta:",
                                  initialvalue=ck.label, parent=self)
        if new_label is not None:
            ck.label = new_label.strip() or ck.label
            ck.draw(); self.save()

    # ── edit/delete ───────────────────────────────────────────────────────────
    def edit_tile(self,t):
        dlg=TileDialog(self,"Editar acceso",tile=t); self.wait_window(dlg)
        if not dlg.result: return
        t.name=dlg.result["name"]; t.path=dlg.result["path"]
        t.color=dlg.result["color"]; t.w=dlg.result["w"]; t.h=dlg.result["h"]
        t.tile_type=dlg.result.get("tile_type", getattr(t,"tile_type","browser"))
        t.draw(); self.save(); self.enforce_zorder()

    def del_tile(self,t):
        if not messagebox.askyesno("Eliminar",f"¿Eliminar «{t.name}»?",parent=self): return
        for i in t._items:
            try: self.canvas.delete(i)
            except: pass
        self._cur.tiles.remove(t); self.save()

    def edit_panel(self,p):
        dlg=PanelDialog(self,panel=p); self.wait_window(dlg)
        if not dlg.result: return
        p.color=dlg.result["color"]; p.alpha=dlg.result["alpha"]; p.draw(); self.save()

    def del_panel(self,p):
        if not messagebox.askyesno("Eliminar","¿Eliminar este panel?",parent=self): return
        for i in p._items:
            try: self.canvas.delete(i)
            except: pass
        self._cur.panels.remove(p); self.save()

    def edit_label(self,l):
        dlg=LabelDialog(self,lbl=l); self.wait_window(dlg)
        if not dlg.result: return
        l.text=dlg.result["text"]; l.color=dlg.result["color"]
        l.size=dlg.result["size"]; l.bold=dlg.result["bold"]
        l.draw(); self.save()

    def del_label(self,l):
        if not messagebox.askyesno("Eliminar","¿Eliminar este texto?",parent=self): return
        for i in l._items:
            try: self.canvas.delete(i)
            except: pass
        self._cur.labels.remove(l); self.save()

    # ── context menu ──────────────────────────────────────────────────────────
    def _ctx_menu(self,e):
        if not self.edit_mode: return
        tile=self._hit_tile(e.x,e.y); lbl=self._hit_label(e.x,e.y)
        pan=self._hit_panel(e.x,e.y); ck=self._hit_check(e.x,e.y)
        m=tk.Menu(self,tearoff=0,bg=SURFACE,fg=TEXT,
                  activebackground=ACCENT,activeforeground="#fff",font=FONT_BODY,bd=0,relief="flat")
        if tile:
            m.add_command(label="📂  Abrir carpeta", command=lambda:open_path(tile.path))
            m.add_command(label="📄  Abrir archivo…", command=lambda:self._open_file_for_tile(tile))
            m.add_separator()
            m.add_command(label="✏  Editar tile",   command=lambda:self.edit_tile(tile))
            m.add_command(label="🗑  Eliminar tile", command=lambda:self.del_tile(tile))
        elif ck:
            m.add_command(label="✏  Editar etiqueta", command=lambda:self.edit_check(ck))
            m.add_command(label="🗑  Eliminar check",  command=lambda:self.del_check(ck))
        elif lbl:
            m.add_command(label="✏  Editar texto",   command=lambda:self.edit_label(lbl))
            m.add_command(label="🗑  Eliminar texto", command=lambda:self.del_label(lbl))
        elif pan:
            m.add_command(label="✏  Editar panel",   command=lambda:self.edit_panel(pan))
            m.add_command(label="🗑  Eliminar panel", command=lambda:self.del_panel(pan))
        else:
            m.add_command(label="＋  Nuevo tile aquí",  command=lambda:self.add_tile(e.x,e.y))
            m.add_command(label="▭  Nuevo panel aquí",  command=lambda:self.add_panel(e.x,e.y))
            m.add_command(label="T  Nuevo texto aquí",  command=lambda:self.add_label(e.x,e.y))
            m.add_command(label="☑  Nuevo check aquí",  command=lambda:self.add_check(e.x,e.y))
        try: m.tk_popup(e.x_root,e.y_root)
        finally: m.grab_release()

    def _hit_tile(self,x,y):
        for t in self.tiles:
            if t.x<=x<=t.x+t.w and t.y<=y<=t.y+t.h: return t
        return None
    def _hit_panel(self,x,y):
        for p in self.panels:
            if p.x<=x<=p.x+p.w and p.y<=y<=p.y+p.h: return p
        return None
    def _hit_label(self,x,y):
        for l in self.labels:
            for item in [i for i in l._items if self.canvas.type(i)=="text"]:
                b=self.canvas.bbox(item)
                if b and b[0]<=x<=b[2] and b[1]<=y<=b[3]: return l
        return None
    def _hit_check(self,x,y):
        for ck in self.checks:
            # bounding box spans from (ck.x, ck.y) across box + label
            items = [i for i in ck._items if self.canvas.type(i) in ("rectangle","text","line")]
            for item in items:
                b = self.canvas.bbox(item)
                if b and b[0]-4<=x<=b[2]+4 and b[1]-4<=y<=b[3]+4: return ck
        return None

    # ── persistence ───────────────────────────────────────────────────────────
    def save(self):
        data = {"boards": [b.to_dict() for b in self._boards],
                "active": self._tabbar.active}
        try:
            with open(DATA_FILE,"w",encoding="utf-8") as f:
                json.dump(data,f,indent=2,ensure_ascii=False)
        except Exception as ex: print("Save error:",ex)

    def _load_board_data(self, bs, items):
        for d in items:
            kind=d.get("kind","tile")
            if kind=="tile":
                t=Tile(self,d["tid"],d["name"],d["path"],d["color"],
                       d["x"],d["y"],d.get("w",Tile.DEF_W),d.get("h",Tile.DEF_H),
                       d.get("saved_filters",[]),
                       d.get("tile_type","browser"))
                t._active_chip       = d.get("active_chip", t.saved_filters[0] if t.saved_filters else "")
                t._browser_rev       = d.get("browser_rev", False)
                t._browser_type      = d.get("browser_type", "all")
                t._browser_sort_col  = d.get("browser_sort_col", "Archivo")
                t._browser_sort_rev  = d.get("browser_sort_rev", False)
                t._browser_exclude   = d.get("browser_exclude", [])
                bs.tiles.append(t); self._next_id=max(self._next_id,d["tid"]+1)
            elif kind=="panel":
                p=Panel(self,d["pid"],d["color"],d.get("alpha",0.5),
                        d["x"],d["y"],d["w"],d["h"])
                bs.panels.append(p); self._next_id=max(self._next_id,d["pid"]+1)
            elif kind=="label":
                l=FreeLabel(self,d["lid"],d["text"],d["color"],
                            d.get("size",20),d.get("bold",False),d["x"],d["y"])
                bs.labels.append(l); self._next_id=max(self._next_id,d["lid"]+1)
            elif kind=="check":
                ck=CheckItem(self,d["cid"],d.get("label",""),d.get("checked",False),
                             d.get("color",ACCENT),d["x"],d["y"])
                bs.checks.append(ck); self._next_id=max(self._next_id,d["cid"]+1)

    def load(self):
        if not os.path.exists(DATA_FILE):
            # first run: create one default board
            self._new_board("Pizarra 1")
            return
        try:
            with open(DATA_FILE,encoding="utf-8") as f: raw=json.load(f)
        except Exception as ex:
            print("Load error:",ex)
            self._new_board("Pizarra 1"); return

        # Support old format (flat list) and new format (dict with boards)
        if isinstance(raw, list):
            # migrate old save
            bs = self._new_board("Pizarra 1", switch=False)
            self._load_board_data(bs, raw)
            self._tabbar._switch(0)
            self._cur = self._boards[0]
            self.enforce_zorder()
            return

        boards_data = raw.get("boards", [])
        active_idx  = raw.get("active", 0)

        if not boards_data:
            self._new_board("Pizarra 1"); return

        for bd in boards_data:
            bs = self._new_board(bd.get("name","Pizarra"), switch=False)
            all_items = (bd.get("tiles",[]) + bd.get("panels",[]) + bd.get("labels",[]) + bd.get("checks",[]))
            self._load_board_data(bs, all_items)

        # hide all boards' items first, then show only active
        for bs in self._boards:
            for t in bs.tiles:
                for i in t._items: self.canvas.itemconfigure(i, state="hidden")
            for p in bs.panels:
                for i in p._items: self.canvas.itemconfigure(i, state="hidden")
            for l in bs.labels:
                for i in l._items: self.canvas.itemconfigure(i, state="hidden")
            for ck in bs.checks:
                for i in ck._items: self.canvas.itemconfigure(i, state="hidden")

        active_idx = min(active_idx, len(self._boards)-1)
        self._tabbar._switch(active_idx)
        self._cur = self._boards[active_idx]
        for t in self._cur.tiles:
            for i in t._items: self.canvas.itemconfigure(i, state="normal")
        for p in self._cur.panels:
            for i in p._items: self.canvas.itemconfigure(i, state="normal")
        for l in self._cur.labels:
            for i in l._items: self.canvas.itemconfigure(i, state="normal")
        for ck in self._cur.checks:
            for i in ck._items: self.canvas.itemconfigure(i, state="normal")
        self.enforce_zorder()

if __name__=="__main__":
    FolderBoard().mainloop()
