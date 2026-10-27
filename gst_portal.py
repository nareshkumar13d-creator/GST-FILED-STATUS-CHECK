"""GST portal (Search Taxpayer) client: captcha aap khud type karte ho, API key ki zaroorat nahi.

Ye portal ke public (undocumented) endpoints use karta hai, jo kabhi bhi badal sakte hain.
Captcha ko bypass nahi karta: har GSTIN ke liye captcha insaan hi daalta hai.
"""
import json, random, re, time, datetime as dt
import urllib.request, urllib.error, http.cookiejar

import gst_app as core

BASE = "https://services.gst.gov.in"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")


def _is_image(b):
    return b[:8] == b"\x89PNG\r\n\x1a\n" or b[:3] == b"\xff\xd8\xff" or b[:4] == b"GIF8"


def _as_image(raw):
    """Portal ka jawab image ho to wahi; JSON/base64 me chhupa ho to nikalta hai; warna None."""
    import base64, re
    if _is_image(raw):
        return raw
    txt = raw.decode("utf-8", "ignore").strip()
    cands = [txt]
    try:
        o = json.loads(txt)
        stack = [o]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, str) and len(x) > 100:
                cands.append(x)
    except ValueError:
        pass
    for c in cands:
        c = re.sub(r"^data:image/[^;]+;base64,", "", c.strip())
        try:
            b = base64.b64decode(c, validate=False)
        except Exception:
            continue
        if _is_image(b):
            return b
    return None


class CaptchaWrong(Exception):
    pass


class Portal:
    """Ek GSTIN = ek session (captcha cookies se bandha hota hai)."""

    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.raw = []  # debugging ke liye aakhri responses
        self.legal, self.trade = "", ""  # party ka naam (verify ke baad bharta hai)
        self.meta = {}  # taxpayer type (dty), status (sts), cancel date (cxdt)

    def req(self, path, data=None, accept="application/json, text/plain, */*"):
        h = {"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9",
             "Referer": BASE + "/services/searchtp", "Origin": BASE,
             "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty",
             "Connection": "keep-alive"}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            h["Content-Type"] = "application/json;charset=UTF-8"
        try:
            with self.op.open(urllib.request.Request(BASE + path, data=body, headers=h), timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Portal ne request rok di (HTTP {e.code}). Thodi der baad try karo.")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Internet/portal error: {e.reason}")

    def captcha_image(self):
        self.req("/services/searchtp", accept="text/html,*/*")  # session start
        raw = self.req("/services/captcha?rnd=" + str(random.random()), accept="image/png,image/*,*/*")
        img = _as_image(raw)
        if img is None:
            snip = " ".join(raw[:150].decode("utf-8", "replace").split()) or "(khali jawab)"
            raise RuntimeError(f"Captcha image nahi mila, portal ne bheja: {snip}")
        return img

    def _json(self, path, data):
        """Portal kabhi-kabhi 'Request Rejected' deta hai (rate limit): thoda ruk ke 3 baar tak dobara koshish (1.5s, 3.5s ruk ke)."""
        waits = (0, 1.5, 3.5)
        for i, w in enumerate(waits):
            if w:
                time.sleep(w)
            txt = self.req(path, data).decode("utf-8", "replace")
            self.raw.append(f"POST {path} {json.dumps(data)}\n{txt[:3000]}")
            if "request rejected" not in txt.lower():
                break
            if i == len(waits) - 1:
                m = re.search(r"support id is:\s*<?(\d+)", txt, re.I)
                raise RuntimeError("Portal ke security filter ne request reject ki" + (f" (ID {m.group(1)})" if m else "") +
                                   ". Thodi der (15-20 min) ruko ya mobile hotspot/dusra internet lo, phir 'Error / Skip wale dobara check karo' dabao.")
        try:
            return json.loads(txt)
        except ValueError:
            snip = " ".join(txt.split())[:120] or "(khali jawab)"
            raise RuntimeError(f"Portal ka jawab samajh nahi aaya (JSON nahi mila). Portal ne bheja: {snip}")

    def verify(self, gstin, captcha):
        r = self._json("/services/api/search/taxpayerDetails", {"gstin": gstin, "captcha": captcha})
        if isinstance(r, dict) and "gstin" in {k.lower() for k in r}:
            return r
        code = str(r.get("errorCode", "")) if isinstance(r, dict) else ""
        msg = str(r.get("message", "")) if isinstance(r, dict) else ""
        if code == "SWEB_9000" or "captcha" in msg.lower():
            raise CaptchaWrong(msg or "Captcha galat ya expire ho gaya.")
        raise RuntimeError(msg or f"Portal ne GSTIN accept nahi kiya ({code or 'unknown'}).")

    def filing_table(self, gstin, fy_start):
        """Ek FY ki return filing list. FY ke do format try karta hai."""
        none_found = False
        for fy in (f"{fy_start}-{fy_start + 1}", f"{fy_start}-{str(fy_start + 1)[2:]}"):
            data = self._json("/services/api/search/taxpayerReturnDetails", {"gstin": gstin, "fy": fy})
            found = core.find_records(data, [])
            if not found and isinstance(data, dict) and "no records" in str(data.get("status", "")).lower():
                none_found = True  # portal: is FY me koi return nahi
                continue
            empty_ok = isinstance(data, dict) and any(k.lower() == "efiledlist" and isinstance(v, list) for k, v in data.items())
            if found or empty_ok:
                return found
        if none_found:
            return []
        raise RuntimeError("Return table nahi mila (portal ka format badla ho sakta hai). 'Raw response' dekho.")


def party_names(info):
    """Portal ke GSTIN details se (legal name, trade name) nikalta hai. Nahi mile to khali string."""
    low = {str(k).lower(): v for k, v in info.items()} if isinstance(info, dict) else {}
    legal = str(low.get("lgnm") or low.get("legalname") or "").strip()
    trade = str(low.get("tradenam") or low.get("tradename") or "").strip()
    return legal, trade


def party_meta(info):
    """Taxpayer type (Regular / Composition ...), GST status (Active / Cancelled) aur cancel date."""
    low = {str(k).lower(): v for k, v in info.items()} if isinstance(info, dict) else {}
    cx, rg = core.parse_date(low.get("cxdt")), core.parse_date(low.get("rgdt"))
    pr = low.get("pradr")
    adr = pr.get("adr") if isinstance(pr, dict) else ""
    return {"dty": str(low.get("dty") or "").strip(), "sts": str(low.get("sts") or "").strip(),
            "cxdt": cx.strftime("%d-%m-%Y") if cx else "", "rgdt": rg.strftime("%d-%m-%Y") if rg else "",
            "ctb": str(low.get("ctb") or "").strip(), "adr": str(adr or "").strip(),
            "stj": str(low.get("stj") or "").strip(), "ctj": str(low.get("ctj") or "").strip()}


def fetch(portal, gstin, captcha, fy=None, today=None):
    """Captcha verify karke us FY ke saare return records (normalized) deta hai."""
    info = portal.verify(gstin, captcha)
    time.sleep(0.3)  # portal ke filter ko tez requests na lagen
    portal.legal, portal.trade = party_names(info)
    portal.meta = party_meta(info)
    t = today or dt.date.today()
    fy = core.current_fy(t) if fy is None else fy
    raw_recs, recs = [], []
    for y in core.fy_years(fy, t):
        for r in portal.filing_table(gstin, y):
            raw_recs.append(r)
            recs.append(core.norm(r))
    good = [r for r in recs if r["type"] in ("GSTR1", "GSTR3B", "CMP08", "GSTR4") and r["filed"] and r["period"]]
    if not good:
        if not raw_recs:
            return []  # portal: "No records Found" (is FY me kuch file nahi hua)
        sample = json.dumps(raw_recs[0])[:300] if raw_recs else "(list khali)"
        raise RuntimeError(f"Portal se {len(raw_recs)} record mile par padh nahi paaye. Pehla record: {sample}")
    return recs


def lookup(portal, gstin, captcha, today=None, fy=None):
    """Purane tareeke ka wrapper: seedha summary deta hai. Return: {rt: summary}."""
    t = today or dt.date.today()
    fy = core.current_fy(t) if fy is None else fy
    recs = fetch(portal, gstin, captcha, fy, t)
    start, end = core.fy_range(fy, t)
    return {rt: core.summarize(rt, recs, t, start, end) for rt in ("GSTR1", "GSTR3B")}
