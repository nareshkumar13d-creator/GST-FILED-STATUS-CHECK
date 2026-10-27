"""Kaam beech mein na khoye: session (ho chuke GSTIN + baaki queue) file me save / wapas load."""
import json, os, datetime as dt


def _enc(r):
    d = dict(r)
    d["period"] = list(r["period"]) if r.get("period") else None
    d["dof"] = r["dof"].isoformat() if r.get("dof") else None
    return d


def _dec(d):
    d = dict(d)
    d["period"] = tuple(d["period"]) if d.get("period") else None
    d["dof"] = dt.date.fromisoformat(d["dof"]) if d.get("dof") else None
    return d


def save(path, state):
    """state: {run_fy, queue, idx, line_info, box, entries}. Pehle temp file, phir replace (beech me band ho to purani file bachi rahe)."""
    out = dict(state)
    out["v"] = 1
    out["saved"] = dt.datetime.now().isoformat(timespec="seconds")
    out["entries"] = [{**e, "recs": [_enc(r) for r in e["recs"]]} if e.get("recs") is not None else dict(e)
                      for e in state["entries"]]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    os.replace(tmp, path)


def load(path):
    """Session wapas deta hai, ya None (file nahi / kharab)."""
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
        st["entries"] = [{**e, "recs": [_dec(r) for r in e["recs"]]} if e.get("recs") is not None else e
                         for e in st["entries"]]
        st.setdefault("queue", [])
        st.setdefault("idx", 0)
        st.setdefault("line_info", {})
        return st
    except (OSError, ValueError, KeyError, TypeError):
        return None
