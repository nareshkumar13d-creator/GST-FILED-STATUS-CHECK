"""Report banana: mahine-wise CSV aur rang wali Excel (.xlsx). Sirf Python standard library use hoti hai."""
import csv, re, zipfile, datetime as dt

import gst_app as core

RT = (("GSTR1", "GSTR-1", "gstr1"), ("GSTR3B", "GSTR-3B", "gstr3b"))
CRT = (("CMP08", "CMP-08", "cmp08"), ("GSTR4", "GSTR-4", "gstr4"))  # composition ke return
LABEL = {"GSTR1": "GSTR-1", "GSTR3B": "GSTR-3B", "CMP08": "CMP-08", "GSTR4": "GSTR-4"}
NA_RES = {"latest": None, "pending": [], "quarterly": True, "months": []}
FREQ_NAME = {"monthly": "Monthly", "quarterly": "Quarterly (QRMP)"}


# ---------------- hisaab ----------------
def compute(entry, today, global_freq="auto", selected=None):
    """Ek GSTIN ka poora hisaab. entry: {gstin, error, legal, trade, recs, fy, freq, note}."""
    g = entry["gstin"]
    c = {"gstin": g, "legal": entry.get("legal", ""), "trade": entry.get("trade", ""),
         "error": entry.get("error", ""), "note": entry.get("note", ""), "res": None,
         "freq_text": "-", "start": None, "end": None, "sel": None, "pending": {}, "is_pending": False,
         "comp": False, "cres": None, "dty": entry.get("dty", ""), "sts": entry.get("sts", ""), "cxdt": entry.get("cxdt", ""),
         "rgdt": entry.get("rgdt", ""), "ctb": entry.get("ctb", ""), "adr": entry.get("adr", ""),
         "stj": entry.get("stj", ""), "ctj": entry.get("ctj", ""),
         "name": (entry.get("name") or "").strip(), "mobile": (entry.get("mobile") or "").strip(),
         }
    party = c["legal"] or c["trade"]
    if c["legal"] and c["trade"] and c["trade"].lower() != c["legal"].lower():
        party += " (" + c["trade"] + ")"
    c["party"] = c["name"] or party  # aapka diya naam pehle, nahi to portal ka naam
    if c["sts"] and c["sts"].lower() != "active":  # Cancelled / Suspended chetavni
        c["note"] = (c["note"] + " " if c["note"] else "") + f"GST {c['sts']}" + (f" ({c['cxdt']})" if c["cxdt"] else "")
    if c["error"]:
        c["row"] = core.to_row(g, err=c["error"])
        return c
    freq = entry.get("freq") or global_freq
    start, end = core.fy_range(entry["fy"], today)
    types = {r["type"] for r in entry["recs"] if r["filed"]}
    if "composition" in c["dty"].lower() or (types & {"CMP08", "GSTR4"} and not types & {"GSTR1", "GSTR3B"}):
        cres = {rt: core.summarize(rt, entry["recs"], today, start, end) for rt, _, _ in CRT}
        res = {"GSTR1": NA_RES, "GSTR3B": NA_RES}
        c.update(res=res, cres=cres, comp=True, start=start, end=end, freq_text="Composition")
        c["row"] = core.to_row(g, res=res)
        c["row"]["gstr1_status"] = c["row"]["gstr3b_status"] = "N/A (Composition)"
        if selected:
            t_, st_ = month_cell(c, "CMP08", selected)
            c["sel"] = {"GSTR1": ("CMP-08: " + t_, st_), "GSTR3B": ("N/A (Composition)", "na")}
            c["pending"] = {"CMP08": [selected]} if st_ == "notfiled" else {}
        else:
            c["pending"] = {rt: list(cres[rt]["pending"]) for rt, _, _ in CRT if cres[rt]["pending"]}
        c["is_pending"] = bool(c["pending"])
        return c
    res = {rt: core.summarize(rt, entry["recs"], today, start, end, freq) for rt, _, _ in RT}
    c.update(res=res, start=start, end=end)
    q = res["GSTR1"]["quarterly"]
    c["freq_text"] = ("Quarterly (QRMP)" if q else "Monthly") + (" (auto)" if freq == "auto" else "")
    c["row"] = core.to_row(g, res=res)
    if selected:
        c["sel"] = {rt: month_cell(c, rt, selected) for rt, _, _ in RT}
        c["pending"] = {rt: [selected] for rt, _, _ in RT if c["sel"][rt][1] == "notfiled"}
    else:
        c["pending"] = {rt: list(res[rt]["pending"]) for rt, _, _ in RT if res[rt]["pending"]}
    c["is_pending"] = bool(c["pending"])
    return c


MSG = {
    "hl": ("Namaste {n} ji,", "GST portal ke record ke hisaab se aapke ye return abhi tak file nahi hue hain:",
           "Kripya jald file karwa dijiye, taaki late fee aur notice se bachav rahe.", "Sir/Madam"),
    "en": ("Dear {n},", "As per the GST portal records, the following returns are still not filed:",
           "Please file them at the earliest to avoid late fee and notices.", "Sir/Madam"),
    "hi": ("नमस्ते {n} जी,", "जीएसटी पोर्टल के रिकॉर्ड के अनुसार आपके ये रिटर्न अभी तक फाइल नहीं हुए हैं:",
           "कृपया जल्द फाइल करवाएँ, ताकि लेट फीस और नोटिस से बचा जा सके।", "महोदय/महोदया"),
}


def pending_message(c, firm="", lang="hl"):
    """WhatsApp ke liye taiyar message (None agar kuch pending nahi). lang: hl / en / hi"""
    if not c.get("pending"):
        return None
    hello, intro, ask, anon = MSG.get(lang, MSG["hl"])
    name = c["name"] or c["legal"] or c["trade"] or anon
    lines = [hello.format(n=name), intro]
    for rt in ("GSTR1", "GSTR3B", "CMP08", "GSTR4"):
        if c["pending"].get(rt):
            lines.append(f"- {LABEL[rt]}: " + L(", ".join(c["pending"][rt]), lang))
    lines += [ask, f"GSTIN: {c['gstin']}"]
    if firm.strip():
        lines += ["", firm.strip()]
    return "\n".join(lines)


def wa_link(mobile, text):
    """wa.me link (10 digit number par 91 lagata hai). Number sahi na ho to None."""
    import urllib.parse
    d = re.sub(r"\D", "", mobile or "")
    if len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "91" + d
    if len(d) < 11:
        return None
    return "https://wa.me/" + d + "?text=" + urllib.parse.quote(text)


def month_cell(c, rt, label):
    """(text, state) ek mahine ke liye. state: filed / late / notfiled / notdue / na / none"""
    res = c["cres"] if rt in ("CMP08", "GSTR4") else c["res"]
    if not res:
        return "-", "none"
    if c["comp"] and rt in ("GSTR1", "GSTR3B"):
        return "Composition party", "na"
    for per, state, txt in res[rt]["months"]:
        if per == label:
            return ("NOT FILED" if state == "notfiled" else txt), state
    per = core.parse_period(label)
    if per and (per < c["start"] or per > c["end"]):
        return "-", "none"
    return "N/A (quarterly)", "na"


def report_months(computed):
    """Report me kin mahino ke column aayenge (pehle valid GSTIN ki range se)."""
    for c in computed:
        if c["res"]:
            out, (y, m) = [], c["start"]
            while (y, m) <= c["end"]:
                out.append(core.lbl((y, m)))
                y, m = core.nxt(y, m)
            return out
    return []


def is_inactive(c):
    return bool(c.get("sts")) and c["sts"].lower() != "active"


def status_cell(c):
    """(text, style): 'Regular | Active' ya 'Regular | Cancelled (date)'."""
    if not c.get("dty") and not c.get("sts"):
        return "-", S_BORDER
    txt = f"{c['dty'] or '-'} | {c['sts'] or '-'}" + (f" ({c['cxdt']})" if c["cxdt"] and is_inactive(c) else "")
    return txt, (S_RED if is_inactive(c) else S_BORDER)


def cmp_summary(c):
    """Composition party ka CMP-08 / GSTR-4 ka ek line me haal ('-' agar regular party)."""
    if not c.get("comp"):
        return "-"
    cr = c["cres"]
    l = cr["CMP08"]["latest"]
    if l:
        late = l["days_late"]
        head = f"CMP-08 {l['period']} ({l['filed_on']})" + (f" ({late} din late)" if late else "")
    else:
        head = "CMP-08: koi filing nahi"
    pend = cr["CMP08"]["pending"]
    out = head + " | " + ("Up to date" if not pend else "NOT FILED: " + ", ".join(pend))
    if cr["GSTR4"]["pending"]:
        out += " | GSTR-4 pending: " + ", ".join(cr["GSTR4"]["pending"])
    return out


def _latest_text(row, k):
    if not row[f"{k}_latest_period"]:
        return "-"
    late = row[f"{k}_days_late"]
    tail = "" if late in ("", 0) else f" ({late} din late)"
    return f"{row[f'{k}_latest_period']} ({row[f'{k}_filed_on']}){tail}"


# ---------------- bhasha (Hinglish / English / Hindi): gst_lang.py me ----------------
from gst_lang import (L, EXACT, PHRASES, CSV_HDR, FREE_CSV, FREE_X, MONTHS_HI, MONTH_RE)  # noqa: F401


def _csv_head(h, lang):
    if lang == "hl":
        return h
    return CSV_HDR[lang].get(h) or L(h, lang)


# ---------------- CSV ----------------
def write_csv(path, computed, selected=None, lang="hl"):
    months = report_months(computed)
    head = ["gstin", "apna_naam", "mobile", "legal_name", "trade_name", "frequency"]
    for _, _, k in RT:
        head += [f"{k}_latest_period", f"{k}_filed_on", f"{k}_days_late", f"{k}_status"]
    head += ["taxpayer_type", "gst_status", "registration_date", "constitution", "address",
             "state_jurisdiction", "centre_jurisdiction", "cmp08_status", "gstr4_status"]
    head += ["error", "note"]
    if selected:
        head += ["chuna_mahina", "chuna_gstr1", "chuna_gstr3b"]
    for lb in months:
        head += [f"{lb} GSTR-1", f"{lb} GSTR-3B"]
    qmonths = [lb for lb in months if core.parse_period(lb)[1] % 3 == 0]
    head += [f"{lb} CMP-08" for lb in qmonths]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow([_csv_head(h, lang) for h in head])
        for c in computed:
            r = c["row"]
            line = [c["gstin"], c["name"], c["mobile"], c["legal"], c["trade"], c["freq_text"]]
            for _, _, k in RT:
                line += [r[f"{k}_latest_period"] and f"{r[f'{k}_latest_period']}", r[f"{k}_filed_on"],
                         r[f"{k}_days_late"], r[f"{k}_status"]]
            cr = c["cres"]
            line += [c["dty"], (c["sts"] + (f" ({c['cxdt']})" if c["cxdt"] else "")).strip(),
                     c["rgdt"], c["ctb"], c["adr"], c["stj"], c["ctj"],
                     ("Up to date" if not cr["CMP08"]["pending"] else "NOT FILED: " + ", ".join(cr["CMP08"]["pending"])) if cr else "",
                     ("Up to date" if not cr["GSTR4"]["pending"] else "NOT FILED: " + ", ".join(cr["GSTR4"]["pending"])) if cr else ""]
            line += [c["error"], c["note"]]
            if selected:
                sel = c.get("sel") or {}
                line += [selected, sel.get("GSTR1", ("",))[0], sel.get("GSTR3B", ("",))[0]]
            for lb in months:
                for rt, _, _ in RT:
                    line.append(month_cell(c, rt, lb)[0] if c["res"] else "")
            for lb in qmonths:
                line.append(month_cell(c, "CMP08", lb)[0] if c["comp"] else "")
            w.writerow([v if (i < len(head) and head[i] in FREE_CSV) else L(v, lang) for i, v in enumerate(line)])


COUNTS = {"hl": "Kul {t} · Baaki {p} · Theek {o} · Error {e}", "en": "Total {t} · Pending {p} · OK {o} · Errors {e}",
          "hi": "कुल {t} · बाकी {p} · ठीक {o} · त्रुटि {e}"}
PREP = {"hl": "Report banane wala", "en": "Prepared by", "hi": "रिपोर्ट बनाने वाला"}
PAGE = {"hl": "Page", "en": "Page", "hi": "पृष्ठ"}


# ---------------- XLSX (bina openpyxl ke) ----------------
S_NORMAL, S_HEAD, S_BORDER, S_RED, S_YEL, S_GRN, S_GREY, S_TITLE, S_SUB = 0, 1, 2, 3, 4, 5, 6, 7, 8
STATE_STYLE = {"filed": S_GRN, "late": S_YEL, "notfiled": S_RED, "notdue": S_GREY, "na": S_GREY, "none": S_GREY}

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _esc(v):
    return _CTRL.sub("", str(v)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _col(i):
    s = ""
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _sheet_xml(rows, widths, freeze=None, footer=("", "", "")):
    x = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
         '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>']
    if freeze:
        col, row = freeze
        cell = f"{_col(col + 1)}{row + 1}"
        x.append('<sheetViews><sheetView workbookViewId="0"><pane '
                 + (f'xSplit="{col}" ' if col else "") + (f'ySplit="{row}" ' if row else "")
                 + f'topLeftCell="{cell}" activePane="{"bottomRight" if col and row else ("bottomLeft" if row else "topRight")}" state="frozen"/>'
                 '</sheetView></sheetViews>')
    x.append("<cols>" + "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1)) + "</cols>")
    x.append("<sheetData>")
    for ri, row in enumerate(rows, 1):
        x.append(f'<row r="{ri}">')
        for ci, (val, st) in enumerate(row, 1):
            ref = f"{_col(ci)}{ri}"
            if val == "" or val is None:
                x.append(f'<c r="{ref}" s="{st}"/>')
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                x.append(f'<c r="{ref}" s="{st}"><v>{val}</v></c>')
            else:
                x.append(f'<c r="{ref}" s="{st}" t="inlineStr"><is><t xml:space="preserve">{_esc(val)}</t></is></c>')
        x.append("</row>")
    x.append("</sheetData>")
    fl, fc, fr = ((_esc(t.replace("&", "&&"))) for t in footer)  # header/footer me '&' ko '&&' likhte hain
    x.append('<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.6" header="0.3" footer="0.3"/>'
             '<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
             f'<headerFooter><oddFooter>&amp;L&amp;8{fl}&amp;C&amp;8{fc}&amp;R&amp;8{fr} &amp;P / &amp;N</oddFooter></headerFooter></worksheet>')
    return "".join(x)


_STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="8">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><sz val="11"/><color rgb="FF9C0006"/><name val="Calibri"/></font>
<font><sz val="11"/><color rgb="FF9C5700"/><name val="Calibri"/></font>
<font><sz val="11"/><color rgb="FF006100"/><name val="Calibri"/></font>
<font><sz val="11"/><color rgb="FF595959"/><name val="Calibri"/></font>
<font><b/><sz val="14"/><color rgb="FF1F4E78"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FF595959"/><name val="Calibri"/></font>
</fonts>
<fills count="7">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEDEDED"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFBFBFBF"/></left><right style="thin"><color rgb="FFBFBFBF"/></right><top style="thin"><color rgb="FFBFBFBF"/></top><bottom style="thin"><color rgb="FFBFBFBF"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="9">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="5" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="6" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="7" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def write_xlsx(path, computed, info=None, selected=None, lang="hl", firm=None):
    """info: [(naam, value), ...] jo 'Info' sheet me jayega."""
    months = report_months(computed)

    # --- Sheet 1: Summary
    h1 = ["S.No", "GSTIN", "Party name", "Mobile", "Frequency", "GST type / status", "GSTR-1 latest",
          "GSTR-1 status", "GSTR-3B latest", "GSTR-3B status", "Composition: CMP-08 / GSTR-4"]
    if selected:
        h1 += [f"{selected}: GSTR-1", f"{selected}: GSTR-3B"]
    h1 += ["Note"]
    rows1 = [[(h, S_HEAD) for h in h1]]
    for n, c in enumerate(computed, 1):
        r = c["row"]
        line = [(n, S_BORDER), (c["gstin"], S_BORDER), (c["party"] or "-", S_BORDER), (c["mobile"] or "-", S_BORDER),
                (c["freq_text"], S_BORDER), status_cell(c)]
        for _, _, k in RT:
            late = r[f"{k}_days_late"]
            line.append((_latest_text(r, k), S_YEL if late not in ("", 0, None) else S_BORDER))
            st = r[f"{k}_status"]
            line.append((st or "-", S_RED if st.startswith("NOT FILED") else (S_GRN if st == "Up to date" else S_GREY)))
        cs = cmp_summary(c)
        line.append((cs, S_RED if "NOT FILED" in cs or "pending" in cs else (S_GRN if c["comp"] else S_BORDER)))
        if selected:
            sel = c.get("sel") or {}
            for rt, _, _ in RT:
                txt, state = sel.get(rt, ("-", "none"))
                line.append((txt, STATE_STYLE.get(state, S_BORDER)))
        line.append((c["error"] or c["note"], S_RED if c["error"] else S_BORDER))
        rows1.append(line)
    w1 = [6, 18, 38, 16, 24, 24, 32, 34, 32, 34, 52] + ([24, 24] if selected else []) + [40]

    # --- Sheet 2: Mahine-wise
    h2 = ["S.No", "GSTIN", "Party name", "Frequency"]
    for lb in months:
        h2 += [f"{lb}\nGSTR-1", f"{lb}\nGSTR-3B"]
    qmonths = [lb for lb in months if core.parse_period(lb)[1] % 3 == 0]
    h2 += [f"{lb}\nCMP-08" for lb in qmonths]
    rows2 = [[(h, S_HEAD) for h in h2]]
    for n, c in enumerate(computed, 1):
        line = [(n, S_BORDER), (c["gstin"], S_BORDER), (c["party"] or "-", S_BORDER), (c["freq_text"], S_BORDER)]
        for lb in months:
            for rt, _, _ in RT:
                if c["res"]:
                    txt, state = month_cell(c, rt, lb)
                    line.append((txt, STATE_STYLE.get(state, S_BORDER)))
                else:
                    line.append(("", S_BORDER))
        for lb in qmonths:
            if c["comp"]:
                txt, state = month_cell(c, "CMP08", lb)
                line.append((txt, STATE_STYLE.get(state, S_BORDER)))
            else:
                line.append(("", S_BORDER))
        rows2.append(line)
    w2 = [6, 18, 38, 24] + [22] * (2 * len(months) + len(qmonths))

    # --- Sheet 3: Info
    rows3 = [[("GST return status report", S_TITLE)], []]
    rows3.append([("Report ki date", S_BORDER), (dt.date.today().strftime("%d-%m-%Y"), S_BORDER)])
    for k, v in (info or []):
        rows3.append([(k, S_BORDER), (v, S_BORDER)])
    rows3 += [[], [("Rang", S_HEAD), ("Matlab", S_HEAD)],
              [("Hara", S_GRN), ("Filed (time par)", S_BORDER)],
              [("Peela", S_YEL), ("Filed, par late", S_BORDER)],
              [("Laal", S_RED), ("NOT FILED", S_BORDER)],
              [("Bhoora", S_GREY), ("Abhi due nahi / is mahine ka return nahi banta (quarterly)", S_BORDER)],
]
    w3 = [30, 70]

    # --- Sheet: Party details (patra / notice bhejne ke liye)
    h4 = ["S.No", "GSTIN", "Party name", "Legal name", "Trade name", "Taxpayer type", "GST status", "Cancel date",
          "Registration date", "Constitution", "Address", "State jurisdiction", "Centre jurisdiction", "Mobile"]
    rows4 = [[(h, S_HEAD) for h in h4]]
    for n, c in enumerate(computed, 1):
        bad = S_RED if is_inactive(c) else S_BORDER
        rows4.append([(n, S_BORDER), (c["gstin"], S_BORDER), (c["party"] or "-", S_BORDER), (c["legal"] or "-", S_BORDER),
                      (c["trade"] or "-", S_BORDER), (c["dty"] or "-", S_BORDER), (c["sts"] or "-", bad),
                      (c["cxdt"] or "-", bad), (c["rgdt"] or "-", S_BORDER), (c["ctb"] or "-", S_BORDER),
                      (c["adr"] or "-", S_BORDER), (c["stj"] or "-", S_BORDER), (c["ctj"] or "-", S_BORDER),
                      (c["mobile"] or "-", S_BORDER)])
    w4 = [6, 18, 30, 30, 30, 14, 12, 12, 16, 16, 60, 60, 60, 14]

    def loc(rows, free=True):
        """Bhasha badlo: header row sab, baaki cells me sirf 'free text' columns (naam, pata...) chhod kar."""
        if lang == "hl":
            return rows
        head = [str(v) for v, _ in rows[0]] if (free and rows and rows[0]) else []
        out = []
        for ri, row in enumerate(rows):
            out.append([((L(v, lang) if (ri == 0 or not free or i >= len(head) or head[i] not in FREE_X) else v), st)
                        for i, (v, st) in enumerate(row)])
        return out

    # --- title block (firm ka naam, report ka naam, tareekh, ginti, kisne banayi)
    firm = firm or {}
    fname = (firm.get("firm") or "").strip()
    fy = next((v for k, v in (info or []) if k == "Saal (FY)"), "")
    n_tot, n_err = len(computed), sum(1 for c in computed if c["error"])
    n_pen = sum(1 for c in computed if c["is_pending"])
    counts = COUNTS[lang if lang in COUNTS else "hl"].format(t=n_tot, p=n_pen, o=n_tot - n_err - n_pen, e=n_err)
    title = L("GST return status report", lang) if lang != "hl" else "GST return status report"
    r2 = " | ".join(x for x in [title if fname else "", f"FY {fy}" if fy else "",
                                f"{L('Report ki date', lang)}: {dt.date.today().strftime('%d-%m-%Y')}", counts] if x)
    prep = (firm.get("prepared_by") or "").strip()
    r3 = " | ".join(x for x in [(firm.get("contact") or "").strip(),
                                f"{PREP[lang if lang in PREP else 'hl']}: {prep}" if prep else ""] if x)
    block = [[(fname or title, S_TITLE)], [(r2, S_SUB)], [(r3, S_SUB)]]
    HDR = len(block) + 1  # header row number (1-based)
    foot = (fname, title, PAGE[lang if lang in PAGE else "hl"])

    sheets = [(L("Summary", lang), block + loc(rows1), w1, (4, HDR)), (L("Mahine-wise", lang), block + loc(rows2), w2, (4, HDR)),
              (L("Party details", lang), block + loc(rows4), w4, (3, HDR)), (L("Info", lang), loc(rows3, free=False), w3, None)]
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(1, len(sheets) + 1)) + "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + "".join(f'<sheet name="{_esc(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, *_r) in enumerate(sheets, 1))
          + "</sheets><definedNames>"
          + "".join(f'<definedName name="_xlnm.Print_Titles" localSheetId="{i}">\'{_esc(sheets[i][0]).replace(chr(39), chr(39) * 2)}\'!${HDR}:${HDR}</definedName>'
                    for i in range(3))
          + "</definedNames></workbook>")
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                        for i in range(1, len(sheets) + 1))
              + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
              "</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/styles.xml", _STYLES)
        for i, (_n, rows, widths, freeze) in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows, widths, freeze, foot))


# ---------------- HTML / PDF report (browser se Print -> Save as PDF) ----------------
HT = {
    "hl": {"title": "GST Return Status Report", "fy": "Saal (FY)", "date": "Report ki date", "by": "Report banane wala",
           "total": "Kul parties", "pending": "Baaki (pending)", "ok": "Theek", "err": "Error", "party": "Party", "type": "Type",
           "r1": "GSTR-1", "r3": "GSTR-3B", "comp": "Composition (CMP-08)", "note": "Note", "months": "Mahine-wise status",
           "legend": "Nishaan", "l_ok": "Time par file", "l_late": "Late file", "l_bad": "File nahi hua", "l_na": "Abhi due nahi / lagu nahi",
           "disc": "Ye report GST portal ke public data par aadharit hai. Due date sarkari extension se badal sakti hai. "
                   "Kisi bhi karyavahi se pehle portal par ek baar jaanch len.", "page": "Page", "latest": "Aakhri"},
    "en": {"title": "GST Return Status Report", "fy": "Year (FY)", "date": "Report date", "by": "Prepared by",
           "total": "Total parties", "pending": "Pending", "ok": "OK", "err": "Errors", "party": "Party", "type": "Type",
           "r1": "GSTR-1", "r3": "GSTR-3B", "comp": "Composition (CMP-08)", "note": "Note", "months": "Month-wise status",
           "legend": "Legend", "l_ok": "Filed on time", "l_late": "Filed late", "l_bad": "Not filed", "l_na": "Not yet due / not applicable",
           "disc": "This report is based on public data from the GST portal. Due dates may change through government extensions. "
                   "Please verify on the portal before taking any action.", "page": "Page", "latest": "Latest"},
    "hi": {"title": "जीएसटी रिटर्न स्थिति रिपोर्ट", "fy": "वर्ष (FY)", "date": "रिपोर्ट की तारीख", "by": "रिपोर्ट बनाने वाला",
           "total": "कुल पार्टियाँ", "pending": "बाकी (पेंडिंग)", "ok": "ठीक", "err": "त्रुटि", "party": "पार्टी", "type": "प्रकार",
           "r1": "GSTR-1", "r3": "GSTR-3B", "comp": "कम्पोज़िशन (CMP-08)", "note": "टिप्पणी", "months": "महीनेवार स्थिति",
           "legend": "संकेत", "l_ok": "समय पर फाइल", "l_late": "देरी से फाइल", "l_bad": "फाइल नहीं हुआ", "l_na": "अभी देय नहीं / लागू नहीं",
           "disc": "यह रिपोर्ट जीएसटी पोर्टल के सार्वजनिक डेटा पर आधारित है। सरकारी विस्तार से देय तारीखें बदल सकती हैं। "
                   "कोई भी कार्रवाई करने से पहले पोर्टल पर एक बार जाँच कर लें।", "page": "पृष्ठ", "latest": "ताज़ा"},
}
_CSS = """
@page { size: A4 landscape; margin: 10mm; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: 'Segoe UI','Nirmala UI',Arial,sans-serif; color:#1f2937; margin:0; font-size:11px; }
.wrap { padding: 4px 6px; }
.head { border-bottom:3px solid #1F4E78; padding-bottom:8px; margin-bottom:8px; }
.head img { max-height:58px; max-width:150px; vertical-align:middle; margin-right:14px; }
.head .hb { display:inline-block; vertical-align:middle; }
.firm { font-size:20px; font-weight:700; color:#1F4E78; }
.sub { color:#4b5563; font-size:11px; margin-top:2px; }
.title { font-size:15px; font-weight:600; margin:2px 0 6px; }
.meta { color:#374151; margin-bottom:8px; }
.cards { margin:8px 0 10px; font-size:0; }
.card { display:inline-block; width:22.5%; margin-right:1.5%; border:1px solid #d1d5db; border-radius:6px; padding:6px 10px; font-size:11px; vertical-align:top; }
.card b { display:block; font-size:18px; }
.card.pend b { color:#b91c1c; } .card.okc b { color:#15803d; } .card.errc b { color:#6b7280; }
table { width:100%; border-collapse:collapse; margin-top:4px; }
thead { display:table-header-group; }
th { background:#1F4E78; color:#fff; padding:5px 6px; text-align:left; font-weight:600; font-size:10.5px; }
td { border:1px solid #e5e7eb; padding:4px 6px; vertical-align:top; }
tr { page-break-inside:avoid; }
tbody tr:nth-child(even) td { background:#f9fafb; }
.gstin { color:#6b7280; font-size:10px; }
.chip { display:inline-block; padding:1px 7px; border-radius:10px; font-size:10px; font-weight:600; margin-top:2px; }
.c-ok { background:#dcfce7; color:#166534; } .c-late { background:#fef3c7; color:#92400e; }
.c-bad { background:#fee2e2; color:#991b1b; } .c-na { background:#e5e7eb; color:#4b5563; }
.mt td, .mt th { text-align:center; padding:3px 3px; font-size:9.5px; }
.mt td.l, .mt th.l { text-align:left; }
.m { display:block; line-height:1.35; } .m small { color:#6b7280; margin-right:2px; }
.m.ok { color:#15803d; } .m.late { color:#b45309; font-weight:600; } .m.bad { color:#b91c1c; font-weight:700; } .m.na { color:#9ca3af; }
.legend { margin-top:8px; }
.disc { margin-top:10px; color:#6b7280; font-size:9.5px; border-top:1px solid #e5e7eb; padding-top:6px; }
.pb { page-break-before: always; }
"""


def _chip(text, kind):
    import html as _h
    return f'<span class="chip c-{kind}">{_h.escape(text)}</span>'


def _status_chip(txt, lang):
    t = txt or "-"
    if t.startswith("NOT FILED"):
        return _chip(L(t, lang), "bad")
    if t == "Up to date":
        return _chip(L("Filed", lang) + " ✓", "ok")
    if t.startswith("N/A") or t == "-":
        return _chip(L(t, lang), "na")
    return _chip(L(t, lang), "na")


def write_html(path, computed, firm=None, info=None, selected=None, lang="hl", auto_print=False):
    """Client ko dene layak report. Browser me kholo -> Print -> 'Save as PDF'. Hindi / logo sab chalta hai."""
    import html as _h, base64, os
    firm = firm or {}
    X = HT[lang if lang in HT else "hl"]
    e = _h.escape
    months = report_months(computed)
    n_tot, n_err = len(computed), sum(1 for c in computed if c["error"])
    n_pen = sum(1 for c in computed if c["is_pending"])
    fy = next((v for k, v in (info or []) if k == "Saal (FY)"), "")
    logo = ""
    lp = firm.get("logo") or ""
    if lp and os.path.isfile(lp):
        try:
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}.get(lp.rsplit(".", 1)[-1].lower(), "image/png")
            with open(lp, "rb") as fh:
                logo = f'<img src="data:{mime};base64,{base64.b64encode(fh.read()).decode()}" alt="">'
        except OSError:
            logo = ""
    fname = (firm.get("firm") or "").strip()
    contact = (firm.get("contact") or "").strip()
    prep = (firm.get("prepared_by") or "").strip()
    meta = [f"{X['date']}: {dt.date.today().strftime('%d-%m-%Y')}"]
    if fy:
        meta.insert(0, f"{X['fy']}: {fy}")
    if prep:
        meta.append(f"{X['by']}: {e(prep)}")
    out = [f'<!DOCTYPE html><html lang="{ {"hl": "en", "en": "en", "hi": "hi"}[lang if lang in HT else "hl"] }"><head><meta charset="utf-8">'
           f"<title>{e(fname + ' - ' if fname else '')}{e(X['title'])}</title><style>{_CSS}</style></head><body><div class=\"wrap\">",
           f'<div class="head">{logo}<div class="hb"><div class="firm">{e(fname) or e(X["title"])}</div>'
           + (f'<div class="sub">{e(contact)}</div>' if contact else "") + "</div></div>",
           f'<div class="title">{e(X["title"])}</div><div class="meta">{" &nbsp;|&nbsp; ".join(meta)}</div>',
           f'<div class="cards"><div class="card"><b>{n_tot}</b>{e(X["total"])}</div>'
           f'<div class="card pend"><b>{n_pen}</b>{e(X["pending"])}</div>'
           f'<div class="card okc"><b>{n_tot - n_pen - n_err}</b>{e(X["ok"])}</div>'
           f'<div class="card errc"><b>{n_err}</b>{e(X["err"])}</div></div>']
    # --- summary table
    out.append(f'<table><thead><tr><th>#</th><th>{e(X["party"])}</th><th>{e(X["type"])}</th><th>{e(X["r1"])}</th>'
               f'<th>{e(X["r3"])}</th><th>{e(X["comp"])}</th><th>{e(X["note"])}</th></tr></thead><tbody>')
    for n, c in enumerate(computed, 1):
        r = c["row"]
        nm = e(c["party"] or c["gstin"])
        who = f'<b>{nm}</b><div class="gstin">{e(c["gstin"])}' + (f' &middot; {e(c["mobile"])}' if c["mobile"] else "") + "</div>"
        if c["error"]:
            out.append(f'<tr><td>{n}</td><td>{who}</td><td>-</td><td colspan="3">-</td><td>{e(L(c["error"], lang))}</td></tr>')
            continue

        def cell(k, st):
            return (f'{e(L(_latest_text(r, k), lang))}<br>' if r[f"{k}_latest_period"] else "") + _status_chip(st, lang)
        out.append(f"<tr><td>{n}</td><td>{who}</td><td>{e(L(c['freq_text'], lang))}</td><td>{cell('gstr1', r['gstr1_status'])}</td>"
                   f"<td>{cell('gstr3b', r['gstr3b_status'])}</td><td>{e(L(cmp_summary(c), lang))}</td>"
                   f"<td>{e(L(c['note'], lang))}</td></tr>")
    out.append("</tbody></table>")
    # --- mahine-wise
    if months:
        sym = {"filed": ("✓", "ok"), "late": ("✓", "late"), "notfiled": ("✗", "bad"), "notdue": ("·", "na"), "na": ("–", "na"), "none": ("", "na")}
        out.append(f'<div class="pb"></div><div class="title">{e(X["months"])}</div><table class="mt"><thead><tr><th class="l">{e(X["party"])}</th>')
        out += [f"<th>{e(L(lb, lang))}</th>" for lb in months]
        out.append("</tr></thead><tbody>")
        for c in computed:
            out.append(f'<tr><td class="l"><b>{e(c["party"] or c["gstin"])}</b><div class="gstin">{e(c["gstin"])}</div></td>')
            for lb in months:
                if not c["res"]:
                    out.append("<td></td>")
                    continue
                rts = (("CMP08", "CMP"),) if c["comp"] and core.parse_period(lb)[1] % 3 == 0 else (
                    () if c["comp"] else (("GSTR1", "R1"), ("GSTR3B", "3B")))
                if not rts:
                    out.append('<td><span class="m na">–</span></td>')
                    continue
                parts = []
                for rt, tag in rts:
                    txt, state = month_cell(c, rt, lb)
                    s_, k_ = sym.get(state, ("", "na"))
                    late = re.search(r"\((\d+) din late\)", txt)
                    if state == "late" and late:
                        s_ += f" {late[1]}d"
                    parts.append(f'<span class="m {k_}"><small>{tag}</small>{e(s_)}</span>')
                out.append("<td>" + "".join(parts) + "</td>")
            out.append("</tr>")
        out.append("</tbody></table>")
    out.append(f'<div class="legend"><b>{e(X["legend"])}:</b> {_chip("✓", "ok")} {e(X["l_ok"])} &nbsp; {_chip("✓ 5d", "late")} {e(X["l_late"])} '
               f'&nbsp; {_chip("✗", "bad")} {e(X["l_bad"])} &nbsp; {_chip("· –", "na")} {e(X["l_na"])}</div>')
    out.append(f'<div class="disc">{e(X["disc"])}</div></div>')
    if auto_print:
        out.append("<script>window.addEventListener('load',function(){setTimeout(function(){window.print();},500);});</script>")
    out.append("</body></html>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(out))
