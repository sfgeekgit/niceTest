"""System prompts: where they come from, how they are cleaned, and how they are fingerprinted.

The text of a prompt is only ever held in memory. What gets stored with a conversation is a
reference: the source id, a SHA-256 of the source text, and what was filled in.
"""
import datetime
import hashlib
import json
import re

from .paths import CONFIG, PROMPTS

DATE_LINE = "The current date is {date}."

# Capture dates appear in extracted prompts in these forms. Order matters: longer forms are
# replaced first so that a shorter form never eats part of a longer one.
DATE_FORMATS = [
    "%A, %B %d, %Y",   # Saturday, October 03, 2026
    "%A, %B {d}, %Y",  # Saturday, October 3, 2026
    "%B %d, %Y",       # October 03, 2026
    "%B {d}, %Y",      # October 3, 2026
    "%b %d, %Y",
    "%b {d}, %Y",
    "%Y-%m-%d",
]

CAPTURE_DATE_PATTERNS = [
    r"Current date: (\d{4}-\d{2}-\d{2})",
    r"The current date is (?:[A-Z][a-z]+, )?([A-Z][a-z]+ \d{1,2}, \d{4})",
    r"Current time is (?:[A-Z][a-z]+, )?([A-Z][a-z]+ \d{1,2}, \d{4})",
    r"Current time: (?:[A-Z][a-z]+, )?([A-Z][a-z]+ \d{1,2}, \d{4})",
]

# Lines that are annotations by whoever captured the prompt, or per-user content.
DROP_LINE_PATTERNS = [
    r"^\[Message role: .*\]\s*$",
    r"\[REDACTED",
    r"PLACEHOLDER USERPREFRENCES",
    r"PLACEHOLDER USERSTYLE",
    r"^\[user's message text appears here\]\s*$",
    r"^`?\[saved_info_placeholder\]`?\s*$",
    r"^`?\[user_saved_info\]`?\s*$",
    r"asgeirtj",
]

# Checked after cleaning; any hit means a capture detail survived and is reported.
LEFTOVER_PATTERNS = [r"Reykjav", r"Hafnarf", r"asgeirtj"]


def _fmt(date, fmt):
    return date.strftime(fmt.replace("{d}", str(date.day)))


def _location_replacements(loc):
    return [
        ("Hafnarfjörður, Hafnarfjarðarkaupstaður, Iceland", f"{loc['city']}, {loc['region']}, {loc['country']}"),
        ("Hafnarfjörður, Iceland", f"{loc['city']}, {loc['country']}"),
        ("Reykjavík, Capital Region, IS", f"{loc['city']}, {loc['region']}, {loc['country_code']}"),
        ("Atlantic/Reykjavík", loc["timezone"]),
        ("Atlantic/Reykjavik", loc["timezone"]),
        ("Reykjavik/Iceland", loc["timezone"]),
    ]


def _capture_date(text):
    for pattern in CAPTURE_DATE_PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue
        raw = m.group(1)
        for fmt in ("%Y-%m-%d", "%B %d, %Y"):
            try:
                return datetime.datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
    return None


def _clean_extracted(text, source, today, location):
    warnings = []
    if source.get("strip_prefix") and text.lstrip().startswith(source["strip_prefix"]):
        text = text.lstrip()[len(source["strip_prefix"]):].lstrip()
    if source.get("unwrap_backtick_tags"):
        # the collection wraps XML-style tags in backticks so they display on GitHub
        text = re.sub(r"`(</?[A-Za-z_][^`\n]*>)`", r"\1", text)

    drop = [re.compile(p) for p in DROP_LINE_PATTERNS]
    text = "\n".join(line for line in text.split("\n") if not any(p.search(line) for p in drop))

    for old, new in _location_replacements(location):
        text = text.replace(old, new)

    captured = _capture_date(text)
    if captured is None:
        # the prompt expects the date to be supplied; give it the same line the date-only mode uses
        text += "\n\n" + DATE_LINE.format(date=today.strftime("%A, %B %d, %Y"))
        warnings.append("no capture date found; a date line was appended")
    else:
        for offset in (0, -1):  # the day itself, and "yesterday" examples derived from it
            old_day = captured + datetime.timedelta(days=offset)
            new_day = today + datetime.timedelta(days=offset)
            for fmt in DATE_FORMATS:
                text = text.replace(_fmt(old_day, fmt), _fmt(new_day, fmt))

    for pattern in LEFTOVER_PATTERNS:
        if re.search(pattern, text):
            warnings.append(f"capture detail still present after cleaning: {pattern}")
    return text, {"capture_date": captured.isoformat() if captured else None, "warnings": warnings}


def load_config():
    return json.loads((CONFIG / "prompts.json").read_text())


def describe(source_id):
    """Identity of a prompt source without building it: id, kind and hash of the source text."""
    cfg = load_config()
    if source_id == "dateonly":
        return {"id": "dateonly", "kind": "dateonly", "sha256": hashlib.sha256(DATE_LINE.encode()).hexdigest()}
    source = cfg["sources"][source_id]
    path = PROMPTS / source["file"]
    if not path.exists():
        hint = " Run: python3 prompts/fetch_unofficial.py" if source["kind"] == "extracted" else ""
        raise FileNotFoundError(f"system prompt file missing for {source_id}: {path}.{hint}")
    digest = hashlib.sha256(path.read_bytes())
    digest.update(f"|cleaning:{cfg['cleaning_version']}".encode())
    return {"id": source_id, "kind": source["kind"], "sha256": digest.hexdigest()}


def build(source_id, today=None, location=None):
    """Return (text, meta). `text` is what is sent as the system prompt; `meta` is what is stored."""
    cfg = load_config()
    today = today or datetime.date.today()
    location = location or cfg["default_location"]
    date_text = today.strftime("%A, %B %d, %Y")
    meta = dict(describe(source_id), date_filled=date_text, location_filled=None, warnings=[])

    if source_id == "dateonly":
        return DATE_LINE.format(date=date_text), meta

    source = cfg["sources"][source_id]
    text = (PROMPTS / source["file"]).read_text().rstrip("\n")
    if source["kind"] == "official":
        if "{{currentDateTime}}" in text:
            text = text.replace("{{currentDateTime}}", date_text)
        else:
            # some published prompts carry no date; the product supplies it separately
            text += "\n\n" + DATE_LINE.format(date=date_text)
            meta["date_appended"] = True
        return text, meta

    text, info = _clean_extracted(text, source, today, location)
    meta.update(info)
    meta["location_filled"] = f"{location['city']}, {location['country']}"
    return text, meta


def source_for(model_cfg, mode):
    """Which prompt source a model uses in a given mode. Falls back to a date line."""
    if mode == "dateonly":
        return "dateonly"
    return model_cfg.get("prompts", {}).get(mode) or "dateonly"
