#!/usr/bin/env python3
"""GST Portal Checker: GSTR-1 / GSTR-3B status, bina API key ke.

Aap sirf captcha type karte ho; baaki sab (session, captcha, return table, NOT FILED nikalna) automatic.
Bhasha: upar kone me Hinglish / English / हिंदी chuno (poori app, report aur message badal jate hain).
Chalane ke liye: python gst_portal_app.py     |  .exe ke liye: build_exe.bat
"""
import os, re, io, csv, pathlib, base64, time, threading, tempfile, webbrowser, datetime as dt
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import gst_app as core
import gst_portal as gp
import gst_report as rep
import gst_session as ses
import gst_lang as lang
import gst_settings
from gst_lang import T

BLUE, BG, LINE = "#1F4E78", "#f3f6fa", "#cbd5e1"
FREQ_TOKENS = {"M": "monthly", "MONTHLY": "monthly", "Q": "quarterly", "QRMP": "quarterly", "QUARTERLY": "quarterly"}
SESSION_PATH = os.path.join(core.APP_DIR, "gst_session.json")


def D(s):
    """Dynamic text (status / error / mahine) ko chuni hui bhasha me."""
    return lang.L(s)


def fy_label(fy):
    return f"{fy}-{str(fy + 1)[2:]}"


def fy_choices(today=None):
    cur = core.current_fy(today or dt.date.today())
    return [fy_label(cur - i) for i in range(3)]


def period_choices(fy, today=None):
    t = today or dt.date.today()
    (y, m), end = core.fy_range(fy, t)
    out = []
    while (y, m) <= end:
        out.append(core.lbl((y, m)))
        y, m = core.nxt(y, m)
    return out


def parse_line(line):
    """Ek line ko {gstin, freq, name, mobile} me todta hai.
    Jaise: '06ABC...'  |  '06ABC...,Q'  |  '06ABC...,Ram Traders,9876543210,Q' (extra cheezein koi bhi kram me)."""
    line = line.replace("\t", ",").replace(";", ",")
    if "," in line:
        try:
            toks = next(csv.reader([line]))
        except (csv.Error, StopIteration):
            toks = line.split(",")
    else:
        toks = line.split()
    toks = [t.strip() for t in toks if t.strip()]
    if not toks:
        return None
    out = {"gstin": toks[0].upper(), "freq": None, "name": "", "mobile": ""}
    for t in toks[1:]:
        if t.upper() in FREQ_TOKENS:
            out["freq"] = FREQ_TOKENS[t.upper()]
        elif re.fullmatch(r"\+?[\d\s\-]{10,15}", t):
            out["mobile"] = t
        elif not out["name"]:
            out["name"] = t
    return out


class PortalApp:
    # (id, heading key, width)
    COLS = [("gstin", "GSTIN", 130), ("party", "Party name", 200), ("freq", "Type", 120),
            ("g1", "GSTR-1 latest", 190), ("s1", "GSTR-1 status", 190),
            ("g3", "GSTR-3B latest", 190), ("s3", "GSTR-3B status", 190),
            ("cmp", "Composition: CMP-08", 250),
            ("p1", "Chuna mahina: GSTR-1", 170), ("p3", "Chuna mahina: GSTR-3B", 170), ("err", "Note", 240)]
    COMPACT = ("gstin", "party", "freq", "s1", "s3", "cmp", "p1", "p3", "err")  # 'Chhota view' me ye columns

    def __init__(self, root):
        self.root = root
        lang.load_choice()
        self.fit_window()
        self.queue, self.idx = [], 0
        self.entries, self.computed = [], []
        self.portal, self.cur, self.busy, self.img, self.lastraw = None, None, False, None, ""
        self.pre, self.pre_busy, self.waiting = None, False, False  # agla captcha pehle se la lene ke liye
        self.inflight, self.tries, self.run_id = {}, {}, 0  # peeche chal rahe lookup (GSTIN -> True), galat captcha ginti, run ka number
        self.run_fy, self.base_img, self.line_info = None, None, {}
        self.info_msg, self.cap_done, self.period_rev = ("Start check dabao. Har GSTIN ka captcha yahan aayega.", {}), False, {}
        self.build_ui()
        root.after(300, self.offer_restore)

    def fit_window(self):
        """Window screen se badi na ho: Windows par poori screen (maximize), warna screen ke andar."""
        r = self.root
        try:
            r.state("zoomed")
        except tk.TclError:
            w, h = r.winfo_screenwidth(), r.winfo_screenheight()
            r.geometry(f"{min(1380, w - 20)}x{min(780, h - 80)}+0+0")
        r.minsize(900, 560)

    # ---------- UI banana (bhasha badalne par dobara chalta hai) ----------
    def build_ui(self, st=None):
        st = st or {}
        root = self.root
        root.title(T("GST Portal Checker: GSTR-1 & GSTR-3B (captcha manual)"))
        self.apply_style()

        top = ttk.Frame(root, style="Header.TFrame", padding=(14, 10))
        top.pack(fill="x")
        left = ttk.Frame(top, style="Header.TFrame")
        left.pack(side="left")
        ttk.Label(left, text=T("GST Return Status Checker"), style="HeaderTitle.TLabel").pack(anchor="w")
        firm = gst_settings.firm()
        self.sub_lbl = ttk.Label(left, text=firm["firm"] or T("Bina API key; captcha aap type karte ho"), style="HeaderSub.TLabel")
        self.sub_lbl.pack(anchor="w")
        self.lang_var = tk.StringVar(value=lang.lang_name())
        lc = ttk.Combobox(top, textvariable=self.lang_var, values=list(lang.LANGS), width=10, state="readonly")
        lc.pack(side="right")
        lc.bind("<<ComboboxSelected>>", self.change_lang)
        ttk.Label(top, text=T("Bhasha / Language:"), style="Header.TLabel").pack(side="right", padx=(0, 6))
        ttk.Button(top, text=T("Firm ki jaankari"), command=self.firm_dialog).pack(side="right", padx=(0, 18))

        # neeche ki status patti (pehle pack hoti hai taaki table ke neeche hamesha dikhe)
        sb = ttk.Frame(root, style="Status.TFrame")
        sb.pack(side="bottom", fill="x")
        self.status = ttk.Label(sb, anchor="w", style="Status.TLabel", padding=(12, 5))
        self.status.pack(side="left")
        ttk.Label(sb, text=T("Row par double-click: mahine-wise status.  Right-click: is party ko Monthly / Quarterly (QRMP) / Auto maano."),
                  style="StatusHint.TLabel", padding=(12, 5)).pack(side="right")

        box = ttk.LabelFrame(root, text=T("GSTIN list (ek line me ek GSTIN; chaho to 'GSTIN,Q' = quarterly ya 'GSTIN,M' = monthly likho)"))
        box.pack(fill="x", padx=12, pady=(10, 4))
        self.box = tk.Text(box, height=3)
        self.box.pack(fill="x", padx=6, pady=4)
        if st.get("box"):
            self.box.insert("1.0", st["box"])

        b = ttk.Frame(root)
        b.pack(fill="x", padx=10)
        self.start_btn = ttk.Button(b, text=T("Start check"), command=self.start, style="Accent.TButton")
        self.start_btn.pack(side="left")
        ttk.Button(b, text=T("CSV se GSTIN load karo"), command=self.load_csv).pack(side="left", padx=6)
        ttk.Button(b, text=T("Report CSV"), command=self.export_csv).pack(side="left")
        ttk.Button(b, text=T("Report Excel"), command=self.export_xlsx).pack(side="left", padx=6)
        ttk.Button(b, text=T("Report PDF"), command=self.export_pdf).pack(side="left")
        ttk.Button(b, text=T("Raw response"), command=self.show_raw).pack(side="right")
        ttk.Button(b, text=T("Error / Skip wale dobara check karo"), command=self.retry_errors).pack(side="right", padx=6)
        ttk.Button(b, text=T("Pending ko message"), command=self.msg_dialog).pack(side="right")

        o = ttk.Frame(root)
        o.pack(fill="x", padx=10, pady=(6, 0))
        ttk.Label(o, text=T("Saal (FY):")).pack(side="left")
        self.fy_var = tk.StringVar(value=st.get("fy", fy_choices()[0]))
        fy_cb = ttk.Combobox(o, textvariable=self.fy_var, values=fy_choices(), width=9, state="readonly")
        fy_cb.pack(side="left", padx=(4, 12))
        fy_cb.bind("<<ComboboxSelected>>", self.fy_changed)
        ttk.Label(o, text=T("Return type:")).pack(side="left")
        self.freq_labels = {T("Auto (andaza)"): "auto", T("Sab Monthly"): "monthly", T("Sab Quarterly (QRMP)"): "quarterly"}
        rev = {v: k for k, v in self.freq_labels.items()}
        self.freq_var = tk.StringVar(value=rev[st.get("freq", "auto")])
        fq = ttk.Combobox(o, textvariable=self.freq_var, values=list(self.freq_labels), width=22, state="readonly")
        fq.pack(side="left", padx=(4, 12))
        fq.bind("<<ComboboxSelected>>", lambda e: self.rebuild())
        ttk.Label(o, text=T("Mahina:")).pack(side="left")
        values = self.period_values()
        sel0 = st.get("sel")
        self.sel = tk.StringVar(value=D(sel0) if sel0 else T("Sab mahine"))
        self.sel_cb = ttk.Combobox(o, textvariable=self.sel, values=values, width=16, state="readonly")
        self.sel_cb.pack(side="left", padx=(4, 12))
        self.sel_cb.bind("<<ComboboxSelected>>", lambda e: self.rebuild())
        ttk.Button(o, text=T("Due date badlo"), command=self.due_dialog).pack(side="left")

        self.pending_var = tk.BooleanVar(value=st.get("pending", False))
        ttk.Checkbutton(o, text=T("Sirf pending dikhao"), variable=self.pending_var, command=self.rebuild).pack(side="left", padx=(18, 0))
        self.compact_var = tk.BooleanVar(value=st.get("compact", True))
        ttk.Checkbutton(o, text=T("Chhota view (kam columns)"), variable=self.compact_var, command=self.apply_columns).pack(side="left", padx=12)

        cap = ttk.LabelFrame(root, text=T("Captcha"))
        cap.pack(fill="x", padx=10, pady=6)
        self.info = ttk.Label(cap, text="")
        self.info.pack(anchor="w", padx=6, pady=(4, 0))
        row = ttk.Frame(cap)
        row.pack(fill="x", padx=6, pady=6)
        self.zoom_var = tk.StringVar(value=st.get("zoom", "2x"))
        self.cap_lbl = ttk.Label(row, text=T("(captcha yahan dikhega)"), relief="sunken", width=24, anchor="center")
        self.cap_lbl.pack(side="left", ipady=14)
        self.entry = ttk.Entry(row, width=14, font=("Segoe UI", 14))
        self.entry.pack(side="left", padx=10)
        if st.get("cap_text"):
            self.entry.insert(0, st["cap_text"])
        self.entry.bind("<Return>", lambda e: self.submit())
        self.entry.bind("<KeyRelease>", lambda e: self.auto_submit())
        self.entry.bind("<<Paste>>", lambda e: self.root.after(50, self.auto_submit))
        self.ok_btn = ttk.Button(row, text=T("Submit (Enter)"), command=self.submit)
        self.ok_btn.pack(side="left")
        ttk.Button(row, text=T("Naya captcha"), command=self.refresh).pack(side="left", padx=6)
        ttk.Button(row, text=T("Skip"), command=self.skip).pack(side="left")
        self.auto_var = tk.BooleanVar(value=st.get("auto_submit", True))
        ttk.Checkbutton(row, text=T("Auto-submit (6 akshar)"), variable=self.auto_var).pack(side="left", padx=(14, 0))
        ttk.Label(row, text=T("Captcha size:")).pack(side="left", padx=(14, 4))
        zc = ttk.Combobox(row, textvariable=self.zoom_var, values=["1x", "2x", "3x"], width=4, state="readonly")
        zc.pack(side="left")
        zc.bind("<<ComboboxSelected>>", lambda e: self.rezoom())

        tf = ttk.Frame(root)
        tf.pack(fill="both", expand=True, padx=10, pady=6)
        self.tree = ttk.Treeview(tf, columns=[c[0] for c in self.COLS], show="headings")
        vs = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        tf.grid_rowconfigure(0, weight=1)
        tf.grid_columnconfigure(0, weight=1)
        for c, t, w in self.COLS:
            self.tree.heading(c, text=T(t))
            self.tree.column(c, width=w, minwidth=60, anchor="w", stretch=False)  # fixed width: left-right scroll hoga
        self.tree.bind("<Shift-MouseWheel>", lambda e: self.tree.xview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.tree.tag_configure("ok", foreground="#15803d")
        self.tree.tag_configure("bad", foreground="#b91c1c", background="#fdf0f0")
        self.tree.tag_configure("err", foreground="#6b7280", background="#f3f4f6")
        self.tree.tag_configure("warn", foreground="#c2410c", background="#fff4e8")  # GST cancelled / suspended
        self.tree.bind("<Double-1>", self.detail)
        self.menu = tk.Menu(root, tearoff=0)
        for text, val in (("Is party ko Monthly maano", "monthly"), ("Is party ko Quarterly (QRMP) maano", "quarterly"),
                          ("Auto (andaza)", None)):
            self.menu.add_command(label=T(text), command=lambda v=val: self.set_party_freq(v))
        self.tree.bind("<Button-3>", self.popup)
        self.apply_columns()
        # pichli state wapas
        if self.base_img is not None and self.cur:
            self.rezoom()
        elif self.cap_done:
            self.cap_lbl.config(text=T("(ho gaya)"))
        self.say(*self.info_msg[:1], **self.info_msg[1])

    def apply_style(self):
        """Saaf, ek jaisa look: neela header, bade rows, rang wale headings."""
        self.root.configure(background=BG)
        sty = ttk.Style(self.root)
        try:
            sty.theme_use("clam")
        except tk.TclError:
            pass
        f = ("Segoe UI", 10)
        sty.configure(".", font=f, background=BG)
        sty.configure("TFrame", background=BG)
        sty.configure("TLabel", background=BG)
        sty.configure("TCheckbutton", background=BG)
        sty.configure("TLabelframe", background=BG, bordercolor=LINE)
        sty.configure("TLabelframe.Label", background=BG, foreground=BLUE, font=("Segoe UI", 10, "bold"))
        sty.configure("TButton", padding=(10, 5))
        sty.configure("Accent.TButton", background=BLUE, foreground="white", font=("Segoe UI", 10, "bold"), padding=(16, 6))
        sty.map("Accent.TButton", background=[("active", "#2c6aa3"), ("disabled", "#9aa5b1")])
        sty.configure("Header.TFrame", background=BLUE)
        sty.configure("Header.TLabel", background=BLUE, foreground="white")
        sty.configure("HeaderTitle.TLabel", background=BLUE, foreground="white", font=("Segoe UI", 16, "bold"))
        sty.configure("HeaderSub.TLabel", background=BLUE, foreground="#cfe0f1", font=("Segoe UI", 10))
        sty.configure("Status.TFrame", background="#e5ebf3")
        sty.configure("Status.TLabel", background="#e5ebf3", foreground="#1f2937", font=("Segoe UI", 10))
        sty.configure("StatusHint.TLabel", background="#e5ebf3", foreground="#4b5563", font=("Segoe UI", 9))
        sty.configure("Treeview", rowheight=28, font=f, background="white", fieldbackground="white", bordercolor=LINE)
        sty.configure("Treeview.Heading", background=BLUE, foreground="white", font=("Segoe UI", 10, "bold"), padding=(6, 7))
        sty.map("Treeview.Heading", background=[("active", "#2c6aa3")])
        sty.map("Treeview", background=[("selected", "#bfdbfe")], foreground=[("selected", "#111827")])

    def update_status(self):
        t = len(self.computed)
        p = sum(1 for c in self.computed if c["is_pending"])
        e = sum(1 for c in self.computed if c["error"])
        txt = T("Kul: {t}  |  Baaki (pending): {p}  |  Theek: {o}  |  Error: {e}", t=t, p=p, o=t - p - e, e=e)
        if self.inflight:
            txt += T("  |  Check ho rahe: {n}", n=len(self.inflight))
        self.status.config(text=txt)

    def say(self, key, **kw):
        """Captcha ke upar ka message: bhasha badalne par dobara usi message ko naye text me dikhata hai."""
        self.info_msg = (key, kw)
        kw2 = {k: (D(v) if k in ("msg", "e") and isinstance(v, str) else v) for k, v in kw.items()}
        self.info.config(text=T(key, **kw2))
        self.update_status()

    def change_lang(self, _e=None):
        new = lang.LANGS.get(self.lang_var.get(), "hl")
        if new == lang.CODE:
            return
        st = {"box": self.box.get("1.0", "end").rstrip("\n"), "fy": self.fy_var.get(), "freq": self.global_freq(),
              "sel": self.selected(), "pending": self.pending_var.get(), "compact": self.compact_var.get(),
              "zoom": self.zoom_var.get(), "cap_text": self.entry.get(), "auto_submit": self.auto_var.get()}
        lang.set_lang(new)
        lang.save_choice()
        for w in self.root.winfo_children():
            w.destroy()
        self.build_ui(st)
        self.rebuild()
        if not self.cur:
            self.say("Bhasha badal di gayi hai.")

    # ---------- settings ----------
    def cur_fy(self):
        return int(self.fy_var.get()[:4])

    def period_values(self):
        months = period_choices(self.cur_fy())
        self.period_rev = {D(m): m for m in months}
        return [T("Sab mahine")] + [D(m) for m in months]

    def global_freq(self):
        return self.freq_labels.get(self.freq_var.get(), "auto")

    def selected(self):
        return self.period_rev.get(self.sel.get())

    def fy_changed(self, _e=None):
        self.sel_cb.config(values=self.period_values())
        self.sel.set(T("Sab mahine"))
        if self.entries:
            self.say("Naye saal ka data laane ke liye Start check dobara dabao.")

    # ---------- list / queue ----------
    def load_csv(self):
        """CSV se GSTIN. Header ho (gstin, name, mobile, type) to columns naam se pehchane jate hain;
        header na ho to pehla column GSTIN aur baaki columns jaise-the-waise."""
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if not p:
            return
        with open(p, newline="", encoding="utf-8-sig") as fh:
            rows = [r for r in csv.reader(fh) if r and any(x.strip() for x in r)]
        idx = {}
        if rows and not rows[0][0].strip()[:2].isdigit():  # pehli row header hai
            for i, h in enumerate(rows[0]):
                h = h.strip().lower()
                for key, names in (("gstin", ("gstin", "gst no", "gst number", "gstin no")),
                                   ("name", ("name", "party", "party name", "naam", "apna naam", "client name")),
                                   ("mobile", ("mobile", "phone", "mob", "mobile no", "whatsapp")),
                                   ("freq", ("type", "freq", "frequency", "return type"))):
                    if h in names and key not in idx:
                        idx[key] = i
        lines = []
        for r in rows:
            cell = lambda k: r[idx[k]].strip() if k in idx and idx[k] < len(r) else ""
            first = cell("gstin") if idx else r[0].strip()
            if not first[:2].isdigit():
                continue
            toks = [first, cell("name"), cell("mobile"), cell("freq")] if idx else [x.strip() for x in r]
            buf = io.StringIO()
            csv.writer(buf).writerow([x for x in toks if x])
            lines.append(buf.getvalue().strip())
        self.box.delete("1.0", "end")
        self.box.insert("1.0", "\n".join(lines))

    def start(self):
        items = [parse_line(x) for x in self.box.get("1.0", "end").splitlines()]
        items = [i for i in items if i]
        if not items:
            return messagebox.showinfo("GST", T("Pehle GSTIN daalo."))
        self.tree.delete(*self.tree.get_children())
        self.entries, self.computed, self.queue, self.idx, self.line_info = [], [], [], 0, {}
        self.run_fy, self.cap_done, self.waiting = self.cur_fy(), False, False
        self.run_id, self.inflight, self.tries = self.run_id + 1, {}, {}  # purane run ke der se aaye result ignore honge
        dups = 0
        for it in items:
            g = it["gstin"]
            if g in self.line_info:
                dups += 1  # duplicate GSTIN ek hi baar
                continue
            self.line_info[g] = {"freq": it["freq"], "name": it["name"], "mobile": it["mobile"]}
            if not core.GSTIN_RE.match(g) or not core.checksum_ok(g):
                self.add_entry({"gstin": g, "error": "GSTIN galat hai (format/checksum)", "fy": self.run_fy})
            else:
                self.queue.append(g)
        if dups:
            messagebox.showinfo("GST", T("{n} duplicate GSTIN hata diye.", n=dups))
        self.next_captcha()

    def next_captcha(self):
        self.save_session()
        if self.idx >= len(self.queue):
            self.cur = None
            self.finish_msg()
            return
        self.cur = self.queue[self.idx]
        self.load_captcha()

    def finish_msg(self):
        """Saari captcha ho chuke: abhi peeche chal rahe lookup ho gaye ya nahi, uske hisaab se message."""
        if self.inflight:
            self.cap_done = False
            self.cap_lbl.config(image="", text="…")
            self.say("Aakhri {n} GSTIN ka check chal raha hai…", n=len(self.inflight))
        else:
            self.cap_done = True
            self.cap_lbl.config(image="", text=T("(ho gaya)"))
            self.say("Ho gaya: {n} GSTIN. Report CSV / Excel save kar sakte ho.", n=len(self.entries))

    def after_lookup(self):
        self.save_session()
        if self.cur is None and self.idx >= len(self.queue):
            self.finish_msg()

    PRE_MAX_AGE = 240  # itne second se purana pehle-se-laya captcha nahi vaparte (expire ho sakta hai)

    def take_pre(self):
        pre, self.pre = self.pre, None
        return (pre["p"], pre["raw"]) if pre and time.time() - pre["t"] < self.PRE_MAX_AGE else None

    def load_captcha(self):
        if self.busy or not self.cur:
            return
        pre = self.take_pre()
        if pre:  # pehle se taiyar: turant dikhao
            return self.show_captcha(*pre)
        self.busy = True
        self.say("{g} ({i}/{n}): captcha la raha hoon…", g=self.cur, i=self.idx + 1, n=len(self.queue))
        if self.pre_busy:  # peeche se aa raha hai: uska intezaar, dobara request nahi
            self.waiting = True
            return
        threading.Thread(target=self._captcha_job, args=(False,), daemon=True).start()

    def prefetch_next(self):
        """Aap abhi wala captcha type kar rahe ho, tab tak peeche se agla la lo."""
        if self.pre or self.pre_busy or self.idx + 1 >= len(self.queue):
            return
        self.pre_busy = True
        threading.Thread(target=self._captcha_job, args=(True,), daemon=True).start()

    def _captcha_job(self, prefetch=False):
        try:
            p = gp.Portal()
            raw = p.captcha_image()
            self.root.after(0, self.captcha_ready, p, raw, prefetch)
        except Exception as e:
            self.root.after(0, self.captcha_failed, str(e), prefetch)

    def captcha_ready(self, portal, raw, prefetch):
        if not prefetch:
            return self.show_captcha(portal, raw)
        self.pre_busy = False
        if self.waiting:  # current party isi ka intezaar kar rahi thi
            self.waiting = False
            self.show_captcha(portal, raw)
        else:
            self.pre = {"p": portal, "raw": raw, "t": time.time()}

    def show_captcha(self, portal, raw):
        self.busy, self.portal = False, portal
        try:
            try:
                self.base_img = tk.PhotoImage(data=base64.b64encode(raw).decode())
            except tk.TclError:  # JPEG etc.: Pillow se PNG bana ke window me hi dikhao
                from PIL import Image
                buf = io.BytesIO()
                Image.open(io.BytesIO(raw)).convert("RGB").save(buf, "PNG")
                self.base_img = tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode())
            self.rezoom()
        except Exception as ex:  # phir bhi na ho to default viewer me kholo
            self.cap_err = f"{type(ex).__name__}: {ex} | bytes: {raw[:12]!r} | len={len(raw)}"
            print("CAPTCHA IMAGE ERROR:", self.cap_err)
            path = os.path.join(tempfile.gettempdir(), "gst_captcha.jpg")
            with open(path, "wb") as fh:
                fh.write(raw)
            webbrowser.open(path)
            self.cap_lbl.config(image="", text=T("Captcha alag window me khula hai"))
        self.entry.delete(0, "end")
        self.entry.focus_set()
        self.say("{g} ({i}/{n}): captcha type karke Enter dabao.", g=self.cur, i=self.idx + 1, n=len(self.queue))
        if getattr(self, "cap_err", ""):
            self.info.config(text=self.info.cget("text") + "  [image error: " + self.cap_err + "]")
            self.cap_err = ""
        self.prefetch_next()

    def rezoom(self):
        """Captcha ka size (1x / 2x / 3x) badalta hai."""
        if self.base_img is None:
            return
        n = int(self.zoom_var.get()[0])
        self.img = self.base_img.zoom(n) if n > 1 else self.base_img
        self.cap_lbl.config(image=self.img, text="")

    def captcha_failed(self, msg, prefetch=False):
        if prefetch:
            self.pre_busy = False
            if not self.waiting:
                return  # peeche ki koshish fail: chup raho, zarurat padne par seedha la lenge
            self.waiting = False
        self.busy = False
        self.say("Captcha nahi aaya: {msg}  ('Naya captcha' dabao)", msg=msg)

    # ---------- actions ----------
    CAP_LEN = 6  # GST portal captcha hamesha 6 akshar ka hota hai

    def auto_submit(self):
        """6 akshar type hote hi Enter ki zaroorat nahi: apne aap submit."""
        if self.auto_var.get() and len(self.entry.get().strip()) == self.CAP_LEN:
            self.submit()

    def submit(self):
        cap = self.entry.get().strip()
        if self.busy or not self.cur or not self.portal or not cap:
            return
        g, portal = self.cur, self.portal
        self.portal = None
        self.inflight[g] = True
        threading.Thread(target=self._lookup_job, args=(g, portal, cap, self.run_fy, self.run_id), daemon=True).start()
        self.idx += 1  # lookup peeche chalta rahega; aap seedha agla captcha bharo
        self.next_captcha()

    def _lookup_job(self, g, portal, cap, fy, rid):
        t0 = time.time()
        try:
            recs = gp.fetch(portal, g, cap, fy)
            portal.raw.append(f"lookup time: {time.time() - t0:.1f}s")
            self.root.after(0, self.got_result, g, recs, portal, fy, rid)
        except gp.CaptchaWrong:
            self.root.after(0, self.wrong_captcha, g, portal, rid)
        except Exception as e:
            portal.raw.append(f"lookup time (error): {time.time() - t0:.1f}s")
            self.root.after(0, self.got_error, g, str(e), portal, rid)

    def got_result(self, g, recs, portal, fy, rid=None):
        if rid is not None and rid != self.run_id:
            return
        self.inflight.pop(g, None)
        self.lastraw = "\n\n".join(portal.raw)
        e = {"gstin": g, "error": "", "legal": portal.legal, "trade": portal.trade, "recs": recs, "fy": fy,
             "freq": self.line_info.get(g, {}).get("freq"), **portal.meta}
        if not recs:
            e["note"] = "Is saal me portal ne koi return record nahi diya"
        self.add_entry(e)
        self.after_lookup()

    def wrong_captcha(self, g, portal, rid=None):
        """Is GSTIN ka captcha galat gaya: ise baad me dobara poochenge (abhi aap agla bhar rahe ho)."""
        if rid is not None and rid != self.run_id:
            return
        self.inflight.pop(g, None)
        self.tries[g] = self.tries.get(g, 0) + 1
        if self.tries[g] >= 4:
            self.add_entry({"gstin": g, "error": "Captcha baar-baar galat gaya", "fy": self.run_fy})
            return self.after_lookup()
        self.say("{g}: captcha galat tha, ise baad me dobara poochenge.", g=g)
        if self.cur is None:  # sab ho chuka tha: abhi poocho
            self.queue.append(g)
            self.next_captcha()
        else:
            self.queue.insert(self.idx + 1, g)  # abhi wale ke baad
            self.save_session()

    def got_error(self, g, msg, portal, rid=None):
        if rid is not None and rid != self.run_id:
            return
        self.inflight.pop(g, None)
        self.lastraw = "\n\n".join(portal.raw)
        self.add_entry({"gstin": g, "error": msg, "fy": self.run_fy, "raw": self.lastraw[:6000]})
        self.after_lookup()

    def refresh(self):
        self.load_captcha()

    def skip(self):
        if self.cur and not self.busy:
            self.add_entry({"gstin": self.cur, "error": "Skip kiya", "fy": self.run_fy})
            self.idx += 1
            self.next_captcha()

    # ---------- table ----------
    def compute(self, entry):
        return rep.compute(entry, dt.date.today(), self.global_freq(), self.selected())

    def add_entry(self, entry):
        for k, v in self.line_info.get(entry["gstin"], {}).items():
            entry.setdefault(k, v)  # aapka naam / mobile
        self.entries.append(entry)
        c = self.compute(entry)
        self.computed.append(c)
        if self.shown(c):
            self.insert_row(len(self.computed) - 1, c)
        self.update_status()

    def apply_columns(self):
        """Chhota view: latest columns chhupao; mahina chuna ho tabhi 'Chuna mahina' columns dikhao."""
        if self.compact_var.get():
            cols = [c for c in self.COMPACT if self.selected() or c not in ("p1", "p3")]
        else:
            cols = [c[0] for c in self.COLS]
        self.tree.configure(displaycolumns=cols)

    def rebuild(self):
        """Setting badli (type / mahina / due date / bhasha): bina captcha ke sab dobara hisaab."""
        self.apply_columns()
        self.computed = [self.compute(e) for e in self.entries]
        self.tree.delete(*self.tree.get_children())
        for i, c in enumerate(self.computed):
            if self.shown(c):
                self.insert_row(i, c)
        self.update_status()

    def shown(self, c):
        """'Sirf pending' tick ho to sirf pending parties (error wali bhi dikhti hain, taaki koi chhoote nahi)."""
        return not self.pending_var.get() or c["is_pending"] or bool(c["error"])

    def insert_row(self, i, c):
        r = c["row"]
        d = dict.fromkeys([k for k, _, _ in self.COLS], "-")
        d.update(gstin=c["gstin"], party=c["party"] or "-")
        if c["error"]:
            d["err"], tag = D(c["error"]), "err"
        else:
            def cell(k):
                late = r[f"{k}_days_late"]
                tail = "" if late in ("", 0) else f" ({late} din late)"
                return D(f"{r[k + '_latest_period']} ({r[k + '_filed_on']}){tail}") if r[k + "_latest_period"] else "-"
            nf = r["gstr1_status"].startswith("NOT FILED") or r["gstr3b_status"].startswith("NOT FILED")
            if c.get("sel"):
                d["p1"], d["p3"] = D(c["sel"]["GSTR1"][0]), D(c["sel"]["GSTR3B"][0])
                nf = c["sel"]["GSTR1"][1] == "notfiled" or c["sel"]["GSTR3B"][1] == "notfiled"
            if c["comp"]:
                nf = bool(c["is_pending"])
            ok = D("Filed") + " ✓"
            d.update(freq=D(c["freq_text"]), g1=cell("gstr1"), g3=cell("gstr3b"), cmp=D(rep.cmp_summary(c)),
                     s1=D(r["gstr1_status"]) if r["gstr1_status"] != "Up to date" else ok,
                     s3=D(r["gstr3b_status"]) if r["gstr3b_status"] != "Up to date" else ok,
                     err=D(c["note"]))
            tag = "warn" if rep.is_inactive(c) else ("bad" if nf else "ok")
        self.tree.insert("", "end", iid=str(i), values=tuple(d[k] for k, _, _ in self.COLS), tags=(tag,))

    def popup(self, e):
        iid = self.tree.identify_row(e.y)
        if iid:
            self.tree.selection_set(iid)
            self.menu.tk_popup(e.x_root, e.y_root)

    def set_party_freq(self, val):
        sel = self.tree.selection()
        if sel and int(sel[0]) < len(self.entries) and not self.entries[int(sel[0])]["error"]:
            self.entries[int(sel[0])]["freq"] = val
            self.rebuild()
            self.save_session()

    def detail(self, _e):
        sel = self.tree.selection()
        if not sel:
            return
        c = self.computed[int(sel[0])]
        if not c["res"]:
            if c["error"]:  # error row: poora note + portal ka response dikhao
                self.show_raw()
            return
        w = tk.Toplevel(self.root)
        w.title(T("{g}: month-wise status ({t})", g=c["gstin"], t=D(c["freq_text"])))
        w.geometry("560x520")
        t = ttk.Treeview(w, columns=("rt", "p", "s"), show="headings")
        for col, h, wd in (("rt", "Return", 90), ("p", "Period", 120), ("s", "Status", 330)):
            t.heading(col, text=T(h))
            t.column(col, width=wd, anchor="w")
        t.tag_configure("notfiled", foreground="#b91c1c")
        t.tag_configure("late", foreground="#b45309")
        t.tag_configure("filed", foreground="#15803d")
        t.tag_configure("notdue", foreground="#888888")
        src, kinds = (c["cres"], rep.CRT) if c["comp"] else (c["res"], rep.RT)
        for rt, name, _k in kinds:
            for per, state, txt in src[rt]["months"]:
                t.insert("", "end", values=(name, D(per), D(txt)), tags=(state,))
        t.pack(fill="both", expand=True, padx=8, pady=8)

    def show_raw(self):
        w = tk.Toplevel(self.root)
        w.title(T("Raw portal response (debugging)"))
        w.geometry("700x420")
        txt = tk.Text(w, wrap="word")
        txt.pack(fill="both", expand=True)
        sel = self.tree.selection()
        raw = ""
        if sel and int(sel[0]) < len(self.entries):  # chuni hui row ka response, nahi to aakhri
            e = self.entries[int(sel[0])]
            raw = (D(e.get("error", "")) + "\n\n" + e.get("raw", "")).strip() if e.get("error") else ""
        txt.insert("1.0", raw or self.lastraw or T("Abhi koi response nahi hai."))

    # ---------- due date badlo ----------
    def due_dialog(self):
        w = tk.Toplevel(self.root)
        w.title(T("Due date badlo"))
        w.geometry("580x430")
        ttk.Label(w, text=T("Sarkar ne kisi mahine ki due date badhayi ho to yahan daalo.\nHisaab (late / NOT FILED) apne aap naye sire se hoga."),
                  justify="left").grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=8)
        types = {T("Dono (Monthly + QRMP)"): "both", T("Sirf Monthly"): "M", T("Sirf Quarterly (QRMP)"): "Q"}
        v_rt, v_per, v_ty, v_dt = tk.StringVar(value="GSTR-1"), tk.StringVar(), tk.StringVar(value=T("Dono (Monthly + QRMP)")), tk.StringVar()
        months = period_choices(self.cur_fy())
        per_rev = {D(m): m for m in months}
        v_per.set(D(months[-1]) if months else "")
        for i, (lab, var, vals) in enumerate((("Return", v_rt, ["GSTR-1", "GSTR-3B"]), ("Mahina", v_per, list(per_rev)),
                                              ("Kis par", v_ty, list(types)))):
            ttk.Label(w, text=T(lab)).grid(row=1, column=i * 2, sticky="e", padx=(10, 2))
            ttk.Combobox(w, textvariable=var, values=vals, width=14 if i < 2 else 22, state="readonly").grid(row=1, column=i * 2 + 1, sticky="w")
        ttk.Label(w, text=T("Nayi due date (dd-mm-yyyy):")).grid(row=2, column=0, columnspan=2, sticky="e", padx=10, pady=8)
        ttk.Entry(w, textvariable=v_dt, width=14).grid(row=2, column=2, sticky="w")
        lst = tk.Listbox(w, height=9)
        lst.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=10, pady=6)
        w.grid_rowconfigure(4, weight=1)
        w.grid_columnconfigure(3, weight=1)

        def show():
            lst.delete(0, "end")
            tyname = {v: k for k, v in types.items()}
            for o in core.OVR:
                lst.insert("end", f"{'GSTR-1' if o['rt'] == 'GSTR1' else 'GSTR-3B'} | {D(core.lbl((o['y'], o['m'])))} | "
                                  f"{tyname.get(o['q'], o['q'])} | {o['due'].strftime('%d-%m-%Y')}")

        def add():
            d, per = core.parse_date(v_dt.get()), core.parse_period(per_rev.get(v_per.get(), ""))
            if not d or not per:
                return messagebox.showinfo("GST", T("Date dd-mm-yyyy me daalo (jaise 25-10-2026) aur mahina chuno."), parent=w)
            rt, q = ("GSTR1" if v_rt.get() == "GSTR-1" else "GSTR3B"), types[v_ty.get()]
            core.OVR[:] = [o for o in core.OVR if not (o["rt"] == rt and (o["y"], o["m"]) == per and o["q"] == q)]
            core.OVR.append({"rt": rt, "y": per[0], "m": per[1], "q": q, "due": d})
            core.save_overrides()
            show()
            self.rebuild()

        def remove():
            s = lst.curselection()
            if s:
                del core.OVR[s[0]]
                core.save_overrides()
                show()
                self.rebuild()

        ttk.Button(w, text=T("Add / Badlo"), command=add).grid(row=3, column=0, columnspan=2, pady=4)
        ttk.Button(w, text=T("Chuni hui hatao"), command=remove).grid(row=3, column=2, columnspan=2, pady=4)
        show()

    # ---------- session (kaam beech mein na khoye) ----------
    def save_session(self):
        todo = list(self.inflight) + self.queue[self.idx:]  # jo chal raha tha wo bhi baaki maano (band hone par kuch na chhute)
        try:
            ses.save(SESSION_PATH, {"run_fy": self.run_fy, "queue": todo, "idx": 0,
                                    "line_info": self.line_info, "box": self.box.get("1.0", "end"),
                                    "entries": self.entries})
        except (OSError, TypeError, ValueError):
            pass

    def offer_restore(self):
        st = ses.load(SESSION_PATH)
        if not st or not st["entries"] and st["idx"] >= len(st["queue"]):
            return
        left = max(0, len(st["queue"]) - st["idx"])
        done = len(st["entries"])
        if not messagebox.askyesno("GST", T("Pichla kaam mila: {done} GSTIN ho chuke hain, {left} baaki hain.\nWahin se aage badhein? (Nahi dabaoge to naya kaam shuru karne par ye hat jayega.)",
                                            done=done, left=left)):
            return
        self.run_fy, self.queue, self.idx = st.get("run_fy"), st["queue"], st["idx"]
        self.run_id, self.inflight, self.tries = self.run_id + 1, {}, {}
        self.line_info, self.entries = st["line_info"], st["entries"]
        self.box.delete("1.0", "end")
        self.box.insert("1.0", st.get("box", "").strip())
        if self.run_fy:
            self.fy_var.set(fy_label(self.run_fy))
            self.fy_changed()
        self.rebuild()
        if left:
            self.next_captcha()
        else:
            self.say("Pichla result wapas aa gaya: {done} GSTIN. Report save kar sakte ho.", done=done)

    def retry_errors(self):
        """Jin GSTIN me error aaya ya Skip kiya, unhe dobara captcha se check karo."""
        if self.busy or self.inflight:
            if self.inflight:
                messagebox.showinfo("GST", T("Pehle chal rahe check poore hone do, phir dobara check karo."))
            return
        redo = [e for e in self.entries if e["error"] and not e["error"].startswith("GSTIN galat")]
        if not redo:
            return messagebox.showinfo("GST", T("Dobara check karne layak koi error / skip wali party nahi hai."))
        self.run_fy = redo[0].get("fy") or self.run_fy
        self.entries = [e for e in self.entries if e not in redo]
        self.queue, self.idx, self.cap_done = [e["gstin"] for e in redo], 0, False
        self.run_id, self.tries = self.run_id + 1, {}
        self.rebuild()
        self.next_captcha()

    # ---------- pending message ----------
    def msg_dialog(self):
        pend = [c for c in self.computed if c["is_pending"]]
        if not pend:
            return messagebox.showinfo("GST", T("Abhi koi pending party nahi hai."))
        w = tk.Toplevel(self.root)
        w.title(T("Pending parties ko message (WhatsApp)"))
        w.geometry("760x520")
        top = ttk.Frame(w)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text=T("Aapki firm ka naam (message ke neeche aayega):")).pack(side="left")
        firm = tk.StringVar(value=gst_settings.firm()["firm"])
        ttk.Entry(top, textvariable=firm, width=30).pack(side="left", padx=6)
        mid = ttk.Frame(w)
        mid.pack(fill="both", expand=True, padx=8)
        lst = tk.Listbox(mid, width=38)
        lst.pack(side="left", fill="y")
        txt = tk.Text(mid, wrap="word")
        txt.pack(side="left", fill="both", expand=True, padx=(8, 0))
        for c in pend:
            lst.insert("end", f"{c['party'] or c['gstin']}  {T('(mobile hai)') if c['mobile'] else T('(mobile nahi)')}"
                            + ("  [GST " + D(c["sts"]) + "]" if rep.is_inactive(c) else ""))

        def show(_e=None):
            s = lst.curselection()
            if s:
                txt.delete("1.0", "end")
                txt.insert("1.0", rep.pending_message(pend[s[0]], firm.get(), lang.CODE))

        def cur():
            s = lst.curselection()
            return (pend[s[0]], txt.get("1.0", "end").strip()) if s else (None, "")

        def clip(text):
            w.clipboard_clear()
            w.clipboard_append(text)
            self.say("Message copy ho gaya. WhatsApp me paste karo.")

        def copy_one():
            c, t = cur()
            if c:
                clip(t)

        def copy_all():
            clip("\n\n-----\n\n".join(rep.pending_message(c, firm.get(), lang.CODE) for c in pend))

        def wa():
            c, t = cur()
            if not c:
                return
            link = rep.wa_link(c["mobile"], t)
            if link:
                webbrowser.open(link)
            else:
                messagebox.showinfo("GST", T("Is party ka mobile number nahi hai. Message copy karke khud bhejo."), parent=w)

        lst.bind("<<ListboxSelect>>", show)
        bt = ttk.Frame(w)
        bt.pack(fill="x", padx=8, pady=8)
        ttk.Button(bt, text=T("Ye message copy karo"), command=copy_one).pack(side="left")
        ttk.Button(bt, text=T("WhatsApp me kholo"), command=wa).pack(side="left", padx=6)
        ttk.Button(bt, text=T("Sab messages copy karo"), command=copy_all).pack(side="left")

    # ---------- firm ki jaankari ----------
    def firm_dialog(self):
        cur = gst_settings.firm()
        w = tk.Toplevel(self.root)
        w.title(T("Firm ki jaankari (report me aayegi)"))
        w.geometry("560x230")
        v = {k: tk.StringVar(value=cur[k]) for k in gst_settings.FIRM_KEYS}
        for i, (key, lab) in enumerate((("firm", "Firm ka naam:"), ("contact", "Pata / phone:"),
                                        ("prepared_by", "Report banane wala (naam):"), ("logo", "Logo (PNG / JPG):"))):
            ttk.Label(w, text=T(lab)).grid(row=i, column=0, sticky="e", padx=(12, 6), pady=7)
            ttk.Entry(w, textvariable=v[key], width=44).grid(row=i, column=1, sticky="we", pady=7)

        def pick():
            f = filedialog.askopenfilename(filetypes=[("Image", "*.png *.jpg *.jpeg *.gif"), ("All", "*.*")])
            if f:
                v["logo"].set(f)

        ttk.Button(w, text=T("Chuno…"), command=pick).grid(row=3, column=2, padx=6)
        ttk.Button(w, text=T("Logo hatao"), command=lambda: v["logo"].set("")).grid(row=3, column=3)

        def save():
            gst_settings.update(**{k: v[k].get().strip() for k in gst_settings.FIRM_KEYS})
            self.sub_lbl.config(text=v["firm"].get().strip() or T("Bina API key; captcha aap type karte ho"))
            w.destroy()
            self.say("Firm ki jaankari save ho gayi.")

        ttk.Button(w, text=T("Save karo"), command=save, style="Accent.TButton").grid(row=4, column=1, sticky="w", pady=12)
        w.grid_columnconfigure(1, weight=1)

    # ---------- export ----------
    def _export_ready(self):
        if not self.computed:
            messagebox.showinfo("GST", T("Pehle check chalao."))
            return False
        return True

    def visible(self):
        return [c for c in self.computed if self.shown(c)]

    def _info(self):
        fy = self.run_fy or self.cur_fy()
        return [("Saal (FY)", fy_label(fy)), ("Return type", self.freq_var.get()),
                ("Due date badli hui", ", ".join(f"{'GSTR-1' if o['rt'] == 'GSTR1' else 'GSTR-3B'} {core.lbl((o['y'], o['m']))} -> "
                                                f"{o['due'].strftime('%d-%m-%Y')}" for o in core.OVR) or "Koi nahi")]

    def export_csv(self):
        if not self._export_ready():
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="gst_report.csv")
        if p:
            rep.write_csv(p, self.visible(), self.selected(), lang.CODE)
            self.say("CSV report save hui: {p}", p=p)

    def export_pdf(self):
        """Client ko dene layak report: browser me khulti hai, Print -> 'Save as PDF'."""
        if not self._export_ready():
            return
        p = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML", "*.html")], initialfile="gst_report.html")
        if not p:
            return
        try:
            rep.write_html(p, self.visible(), gst_settings.firm(), self._info(), self.selected(), lang.CODE, auto_print=True)
        except OSError as e:
            return messagebox.showerror("GST", T("Report save nahi hui: {e}", e=e))
        webbrowser.open(pathlib.Path(p).resolve().as_uri())
        self.say("PDF report: browser me Print dialog khulega. 'Save as PDF' chuno. File: {p}", p=p)

    def export_xlsx(self):
        if not self._export_ready():
            return
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialfile="gst_report.xlsx")
        if p:
            try:
                rep.write_xlsx(p, self.visible(), self._info(), self.selected(), lang.CODE, gst_settings.firm())
            except OSError as e:
                return messagebox.showerror("GST", T("Save nahi hui (file kahin khuli hai?): {e}", e=e))
            self.say("Excel report save hui: {p}", p=p)


if __name__ == "__main__":
    core.set_taskbar_id("GSTReturnStatusChecker.Portal")
    root = tk.Tk()
    core.set_window_icon(root)
    PortalApp(root)
    root.mainloop()
