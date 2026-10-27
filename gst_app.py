#!/usr/bin/env python3
"""GST Status: GSTR-1 / GSTR-3B filing status checker (desktop app).

Chalane ke liye:  python gst_app.py
.exe banane ke liye: build_exe.bat par double-click (Windows par).
Sirf Python standard library use hoti hai.
"""
import os, sys, re, json, csv, threading, datetime as dt
import urllib.request, urllib.parse, urllib.error

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:  # logic ko bina GUI ke test karne ke liye
    tk = None

APP_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CFG_PATH = os.path.join(APP_DIR, "gst_config.json")
DEFAULT_URL = "https://www.knowyourgst.com/gstin-management/returnapi/?gstin={gstin}&fy={fy}"

def set_window_icon(root, name="gst_icon.ico"):
    """Window ke title bar aur taskbar ka icon (Windows .ico). Exe me bhi chalta hai (PyInstaller --add-data)."""
    for base in (getattr(sys, "_MEIPASS", None), APP_DIR, os.path.dirname(os.path.abspath(__file__))):
        p = os.path.join(base, name) if base else ""
        if p and os.path.isfile(p):
            try:
                root.iconbitmap(default=p)
                return True
            except Exception:
                pass
    return False


def set_taskbar_id(app_id):
    """Taskbar par Python ke bajay apna icon dikhane ke liye (sirf Windows)."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
CH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------- logic ----------------
def checksum_ok(g):
    s = 0
    for i in range(14):
        p = CH.index(g[i]) * (2 if i % 2 else 1)
        s += p // 36 + p % 36
    return CH[(36 - s % 36) % 36] == g[14]


def lbl(p):
    return f"{MN[p[1] - 1]} {p[0]}"


def nxt(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)


OVR_PATH = os.path.join(APP_DIR, "gst_due_dates.json")
OVR = []  # sarkari extension: [{"rt","y","m","q": "both"|"M"|"Q","due": date}]


def load_overrides():
    OVR.clear()
    try:
        with open(OVR_PATH, encoding="utf-8") as fh:
            for o in json.load(fh):
                OVR.append({"rt": o["rt"], "y": int(o["y"]), "m": int(o["m"]), "q": o.get("q", "both"),
                            "due": dt.date.fromisoformat(o["due"])})
    except (OSError, ValueError, KeyError, TypeError):
        pass


def save_overrides():
    try:
        with open(OVR_PATH, "w", encoding="utf-8") as fh:
            json.dump([{**o, "due": o["due"].isoformat()} for o in OVR], fh, indent=1)
    except OSError:
        pass


load_overrides()


def due(rt, y, m, q=False):
    for o in reversed(OVR):  # baad me jodi hui date jeetti hai
        if o["rt"] == rt and o["y"] == y and o["m"] == m and o["q"] in ("both", "Q" if q else "M"):
            return o["due"]
    ny, nm = nxt(y, m)
    if rt == "CMP08":  # composition: quarter ke baad ki 18 tareekh
        return dt.date(ny, nm, 18)
    if rt == "GSTR4":  # composition saalana: FY ke baad 30 April
        return dt.date(y if m < 4 else y + 1, 4, 30)
    if rt == "GSTR9":  # saalana return: FY ke baad 31 December
        return dt.date(y if m < 4 else y + 1, 12, 31)
    day = (13 if rt == "GSTR1" else 24) if q else (11 if rt == "GSTR1" else 20)
    return dt.date(ny, nm, day)


def current_fy(t):
    return t.year if t.month >= 4 else t.year - 1


def fy_years(fy, t):
    """Portal se kaun-kaun se FY fetch karne hain (April-May me March ka return pichle FY me hota hai)."""
    return [fy] + ([fy - 1] if fy == current_fy(t) and t.month in (4, 5) else [])


def fy_range(fy, t):
    """(start, end) = pehla aur aakhri (saal, mahina) jo dikhana hai."""
    if fy < current_fy(t):
        return (fy, 4), (fy + 1, 3)
    return ((fy - 1, 4) if t.month in (4, 5) else (fy, 4)), (t.year, t.month)


def parse_period(s):
    s = str(s or "").strip()
    for pat, order in ((r"(\d{1,2})(\d{4})", "my"), (r"(\d{4})[-/](\d{2})", "ym")):
        m = re.fullmatch(pat, s)
        if m:
            a, b = int(m[1]), int(m[2])
            return (b, a) if order == "my" else (a, b)
    for f in ("%B %Y", "%b %Y", "%b-%Y", "%B-%Y"):
        try:
            d = dt.datetime.strptime(s, f)
            return (d.year, d.month)
        except ValueError:
            pass


def parse_date(s):
    s = str(s or "").strip()[:10]
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass


def find_records(o, out):
    if isinstance(o, dict):
        if {k.lower() for k in o} & {"rtntype", "return_type", "returntype", "rtn_type"}:
            out.append(o)
            return out
        for v in o.values():
            find_records(v, out)
    elif isinstance(o, list):
        for v in o:
            find_records(v, out)
    return out


def pick(r, *names):
    low = {k.lower(): v for k, v in r.items()}
    for n in names:
        if low.get(n) not in (None, "") and not isinstance(low[n], (dict, list)):
            return low[n]


def period_of(r):
    """Period nikalta hai. Portal 'taxp': 'September' + 'fy': '2026-2027' deta hai (mahine ka naam, saal nahi)."""
    per = parse_period(pick(r, "ret_prd", "period", "tax_period", "taxperiod", "retperiod", "taxp"))
    if per:
        return per
    name = str(pick(r, "taxp", "ret_prd", "period", "tax_period", "taxperiod") or "").strip()
    fy = str(pick(r, "fy") or "")
    m = re.match(r"(\d{4})", fy)
    if not m:
        return None
    sy = int(m[1])
    mon = None
    found = re.findall(r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", name.lower())
    if found:  # 'September' ya 'July - September' (quarter): aakhri mahina
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(found[-1]) + 1
    else:
        q = re.search(r"q\s*([1-4])", name.lower())
        if q:
            mon = {1: 6, 2: 9, 3: 12, 4: 3}[int(q[1])]
    if mon:
        return (sy if mon >= 4 else sy + 1, mon)


def norm(r):
    rt = re.sub(r"[^A-Z0-9]", "", str(pick(r, "rtntype", "return_type", "returntype", "rtn_type") or "").upper())
    st = str(pick(r, "status") or "")
    dof = parse_date(pick(r, "dof", "date_of_filing", "filing_date", "filed_on"))
    per = period_of(r)
    if per is None and rt in ("GSTR4", "GSTR9"):  # saalana return: FY ka aakhri mahina (March)
        m_ = re.match(r"(\d{4})", str(pick(r, "fy") or ""))
        per = (int(m_[1]) + 1, 3) if m_ else None
    return {"type": rt, "period": per,
            "dof": dof, "arn": pick(r, "arn") or "",
            "filed": st.lower().startswith("filed") or (not st and dof is not None)}


def demo_data(fy):
    t, y0, rec = dt.date.today(), int(fy[:4]), []
    for rt in ("GSTR1", "GSTR3B"):
        ps, (y, m) = [], (y0, 4)
        while (y, m) < (y0 + 1, 4) and (y, m) <= (t.year, t.month):
            if due(rt, y, m) < t:
                ps.append((y, m))
            y, m = nxt(y, m)
        for i, (y, m) in enumerate(ps):
            if rt == "GSTR3B" and len(ps) >= 3 and i == len(ps) - 2:
                continue  # demo: ek 3B pending dikhao
            d = due(rt, y, m) - dt.timedelta(days=1 if i % 4 else -3)
            rec.append({"arn": "AA%02d%02d%07d" % (m, y % 100, i + 1), "ret_prd": "%02d%d" % (m, y),
                        "dof": d.strftime("%d-%m-%Y"), "rtntype": rt, "status": "Filed"})
    return {"EFiledlist": rec}


def fetch_fy(g, fy, cfg):
    if cfg.get("demo"):
        return demo_data(fy)
    if not cfg.get("key"):
        raise RuntimeError("API key daalo ya Demo mode on karo.")
    url = (cfg.get("url") or DEFAULT_URL).replace("{gstin}", g).replace("{fy}", fy) \
        .replace("{key}", urllib.parse.quote(cfg["key"]))
    headers = {"User-Agent": "gst-status/1.0"}
    if cfg.get("hdr"):
        headers[cfg["hdr"]] = cfg["key"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API error {e.code}. Key, URL aur header check karo.")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Internet/server error: {e.reason}")


def summarize(rt, recs, t, start, end=None, freq="auto"):
    end = end or (t.year, t.month)
    filed = {}
    for r in recs:
        if r["type"] == rt and r["filed"] and r["period"]:
            o = filed.get(r["period"])
            if not o or (r["dof"] and (not o["dof"] or r["dof"] > o["dof"])):
                filed[r["period"]] = r
    q = {"monthly": False, "quarterly": True}.get(freq, len(filed) >= 2 and all(p[1] % 3 == 0 for p in filed))
    if rt == "CMP08":
        q = True  # composition ka CMP-08 hamesha quarterly
    elif rt in ("GSTR4", "GSTR9"):
        q = False

    def ok(m):  # kaun se mahine ka return banta hai
        return m == 3 if rt in ("GSTR4", "GSTR9") else (not q or m % 3 == 0)

    exp, (y, m) = [], start
    while (y, m) <= end:
        if ok(m) and due(rt, y, m, q) < t:
            exp.append((y, m))
        y, m = nxt(y, m)
    pending = [p for p in exp if p not in filed]
    latest = None
    if filed:
        lp = max(filed)
        r = filed[lp]
        late = max(0, (r["dof"] - due(rt, lp[0], lp[1], q)).days) if r["dof"] else None
        latest = {"period": lbl(lp), "filed_on": r["dof"].strftime("%d-%m-%Y") if r["dof"] else "",
                  "arn": r["arn"], "days_late": late}
    months, days, (y, m) = [], {}, start
    while (y, m) <= end:
        if ok(m):
            d, r = due(rt, y, m, q), filed.get((y, m))
            if r:
                late = max(0, (r["dof"] - d).days) if r["dof"] else 0
                if late:
                    days[lbl((y, m))] = (late, "late")
                txt = "Filed " + (r["dof"].strftime("%d-%m-%Y") if r["dof"] else "") + (f" ({late} din late)" if late else "")
                months.append((lbl((y, m)), "late" if late else "filed", txt))
            elif d < t:
                days[lbl((y, m))] = ((t - d).days, "notfiled")
                months.append((lbl((y, m)), "notfiled", f"NOT FILED (due {d.strftime('%d-%m-%Y')})"))
            else:
                months.append((lbl((y, m)), "notdue", f"Not yet due ({d.strftime('%d-%m-%Y')})"))
        y, m = nxt(y, m)
    return {"latest": latest, "pending": [lbl(p) for p in pending], "quarterly": q, "months": months, "days": days}


def check(g, cfg):
    if not GSTIN_RE.match(g):
        raise ValueError("GSTIN ka format galat hai")
    if not checksum_ok(g):
        raise ValueError("GSTIN checksum match nahi hua (typo?)")
    t = dt.date.today()
    y0 = t.year if t.month >= 4 else t.year - 1
    fys, start = [f"{y0}-{str(y0 + 1)[2:]}"], (y0, 4)
    if t.month <= 5:  # March ka return pichle FY me aata hai
        fys.append(f"{y0 - 1}-{str(y0)[2:]}")
        start = (y0 - 1, 4)
    recs = []
    for fy in fys:
        recs += [norm(r) for r in find_records(fetch_fy(g, fy, cfg), [])]
    if not recs:
        raise RuntimeError("API se koi return record nahi mila (response format alag ho sakta hai)")
    return {rt: summarize(rt, recs, t, start) for rt in ("GSTR1", "GSTR3B")}


def to_row(g, res=None, err=None):
    row = {"gstin": g, "error": err or ""}
    for rt, k in (("GSTR1", "gstr1"), ("GSTR3B", "gstr3b")):
        r = res[rt] if res else None
        l = r["latest"] if r else None
        row[f"{k}_latest_period"] = l["period"] if l else ""
        row[f"{k}_filed_on"] = l["filed_on"] if l else ""
        row[f"{k}_arn"] = l["arn"] if l else ""
        row[f"{k}_days_late"] = "" if not l or l["days_late"] is None else l["days_late"]
        row[f"{k}_status"] = "" if not r else ("Up to date" if not r["pending"] else "NOT FILED: " + ", ".join(r["pending"]))
    return row


# ---------------- GUI ----------------
class App:
    COLS = [("gstin", "GSTIN", 140), ("g1", "GSTR-1 latest", 170), ("s1", "GSTR-1 status", 150),
            ("g3", "GSTR-3B latest", 170), ("s3", "GSTR-3B status", 150), ("err", "Note", 200)]

    def __init__(self, root):
        self.root, self.rows = root, []
        root.title("GST Return Status: GSTR-1 & GSTR-3B")
        root.geometry("1000x640")
        cfg = self.load_cfg()

        f = ttk.LabelFrame(root, text="API settings")
        f.pack(fill="x", padx=10, pady=(10, 4))
        f.columnconfigure(1, weight=1)
        self.key, self.url, self.hdr = tk.StringVar(value=cfg.get("key", "")), \
            tk.StringVar(value=cfg.get("url", DEFAULT_URL)), tk.StringVar(value=cfg.get("hdr", "passthrough"))
        self.demo, self.save_key = tk.BooleanVar(value=cfg.get("demo", True)), tk.BooleanVar(value=bool(cfg.get("key")))
        for i, (t, v, show) in enumerate((("API key", self.key, "*"), ("API URL ({gstin} {fy} {key})", self.url, ""),
                                          ("Key header name", self.hdr, ""))):
            ttk.Label(f, text=t).grid(row=i, column=0, sticky="w", padx=6, pady=2)
            ttk.Entry(f, textvariable=v, show=show).grid(row=i, column=1, sticky="ew", padx=6, pady=2)
        ttk.Checkbutton(f, text="Demo mode (nakli data, key ki zaroorat nahi)", variable=self.demo).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Checkbutton(f, text="Key is computer par save karo", variable=self.save_key).grid(row=4, column=1, sticky="w", padx=6, pady=(0, 4))

        g = ttk.LabelFrame(root, text="GSTIN list (ek line me ek GSTIN)")
        g.pack(fill="x", padx=10, pady=4)
        self.box = tk.Text(g, height=5)
        self.box.pack(fill="x", padx=6, pady=4)
        self.box.insert("1.0", "06ABCDE1234F1Z4")

        b = ttk.Frame(root)
        b.pack(fill="x", padx=10)
        self.go_btn = ttk.Button(b, text="Check status", command=self.start)
        self.go_btn.pack(side="left")
        ttk.Button(b, text="CSV se GSTIN load karo", command=self.load_csv).pack(side="left", padx=6)
        ttk.Button(b, text="Report CSV save karo", command=self.export).pack(side="left")
        self.msg = ttk.Label(b, text="")
        self.msg.pack(side="left", padx=12)

        self.tree = ttk.Treeview(root, columns=[c[0] for c in self.COLS], show="headings")
        for c, t, w in self.COLS:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("ok", foreground="#15803d")
        self.tree.tag_configure("bad", foreground="#b91c1c")
        self.tree.tag_configure("err", foreground="#888888")
        self.tree.pack(fill="both", expand=True, padx=10, pady=8)

    def load_cfg(self):
        try:
            with open(CFG_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def cfg(self):
        return {"key": self.key.get().strip(), "url": self.url.get().strip(), "hdr": self.hdr.get().strip(),
                "demo": self.demo.get()}

    def save_cfg(self):
        c = self.cfg()
        if not self.save_key.get():
            c["key"] = ""
        try:
            with open(CFG_PATH, "w", encoding="utf-8") as fh:
                json.dump(c, fh)
        except Exception:
            pass

    def load_csv(self):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if not p:
            return
        with open(p, newline="", encoding="utf-8-sig") as fh:
            vals = [r[0].strip().upper() for r in csv.reader(fh) if r and r[0].strip()]
        vals = [v for v in vals if v[:2].isdigit()]  # header row hata do
        self.box.delete("1.0", "end")
        self.box.insert("1.0", "\n".join(vals))

    def start(self):
        gs = [x.strip().upper() for x in self.box.get("1.0", "end").splitlines() if x.strip()]
        if not gs:
            messagebox.showinfo("GST", "Pehle GSTIN daalo.")
            return
        self.save_cfg()
        self.tree.delete(*self.tree.get_children())
        self.rows = []
        self.go_btn.state(["disabled"])
        cfg = self.cfg()
        threading.Thread(target=self.work, args=(gs, cfg), daemon=True).start()

    def work(self, gs, cfg):
        for i, g in enumerate(gs, 1):
            self.root.after(0, lambda i=i, g=g: self.msg.config(text=f"Check ho raha hai {i}/{len(gs)}: {g}"))
            try:
                row = to_row(g, res=check(g, cfg))
            except Exception as e:
                row = to_row(g, err=str(e))
            self.root.after(0, self.add_row, row)
        self.root.after(0, self.done)

    def add_row(self, r):
        self.rows.append(r)

        def cell(k):
            late = r[f"{k}_days_late"]
            tail = "" if late in ("", 0) else f" ({late} din late)"
            return (f"{r[k + '_latest_period']} ({r[k + '_filed_on']}){tail}" if r[k + "_latest_period"] else "-")
        if r["error"]:
            vals, tag = (r["gstin"], "-", "-", "-", "-", r["error"]), "err"
        else:
            bad = r["gstr1_status"].startswith("NOT FILED") or r["gstr3b_status"].startswith("NOT FILED")
            vals, tag = (r["gstin"], cell("gstr1"), r["gstr1_status"], cell("gstr3b"), r["gstr3b_status"], ""), ("bad" if bad else "ok")
        self.tree.insert("", "end", values=vals, tags=(tag,))

    def done(self):
        self.go_btn.state(["!disabled"])
        self.msg.config(text=f"Ho gaya: {len(self.rows)} GSTIN check hue.")

    def export(self):
        if not self.rows:
            messagebox.showinfo("GST", "Pehle status check karo.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="gst_report.csv")
        if not p:
            return
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:  # utf-8-sig: Excel me sahi khulega
            w = csv.DictWriter(fh, fieldnames=list(self.rows[0].keys()))
            w.writeheader()
            w.writerows(self.rows)
        self.msg.config(text=f"Report save hui: {p}")


if __name__ == "__main__":
    if tk is None:
        sys.exit("tkinter nahi mila. Python ko python.org se install karo (tcl/tk ke saath).")
    set_taskbar_id("GSTReturnStatusChecker.Status")
    root = tk.Tk()
    set_window_icon(root)
    App(root)
    root.mainloop()
