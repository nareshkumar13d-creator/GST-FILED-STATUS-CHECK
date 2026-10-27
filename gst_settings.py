"""Chhoti settings file (bhasha + firm ki jaankari). Ek key badalne par baaki keys bachi rehti hain."""
import json, os, sys

APP_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
PATH = os.path.join(APP_DIR, "gst_settings.json")
FIRM_KEYS = ("firm", "contact", "prepared_by", "logo")


def load():
    try:
        with open(PATH, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def update(**kw):
    d = load()
    d.update(kw)
    try:
        with open(PATH, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return d


def firm():
    d = load()
    return {k: str(d.get(k, "") or "").strip() for k in FIRM_KEYS}
