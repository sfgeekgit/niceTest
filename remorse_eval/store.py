"""The dataset on disk. The layout and its rules are defined in SPEC.md, section 6."""
import datetime
import hashlib
import json
import secrets
import threading

from . import paths

SCHEMA = 1
PROTOCOL = 1  # version of the conversation procedure: three fixed user turns, thinking carried forward
CONDITIONS = ["super_remorseful", "remorseful", "neutral", "not_remorseful", "super_not_remorseful"]

_lock = threading.Lock()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def stamp(t=None):
    return (t or utcnow()).strftime("%Y%m%dT%H%M%SZ")


def new_id(t=None):
    return f"{stamp(t)}-{secrets.token_hex(2)}"


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def read_json(path):
    return json.loads(path.read_text())


# ---- the fixed user messages

def messages_config():
    return read_json(paths.PROMPTS / "conditions.json")


def messages_sha256(cfg=None):
    cfg = cfg or messages_config()
    core = {k: cfg[k] for k in ("opener", "conditions", "followup", "third_turn")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def user_turns(condition, cfg=None):
    cfg = cfg or messages_config()
    ending = cfg["conditions"][condition]
    opener = f"{cfg['opener']}, {ending}" if ending else cfg["opener"]
    return [opener, cfg["followup"], cfg["third_turn"]]


# ---- setups

def setup_id(setup, label, register=True):
    """Return a setup's id: a readable label plus the start of its fingerprint. Registers it unless told not to."""
    canonical = json.dumps(setup, sort_keys=True, ensure_ascii=False)
    sid = f"{label}-{hashlib.sha256(canonical.encode()).hexdigest()[:8]}"
    path = paths.DATA / "setups" / f"{sid}.json"
    with _lock:
        if register and not path.exists():
            write_json(path, dict(setup, setup_id=sid))
    return sid


def load_setup(sid):
    return read_json(paths.DATA / "setups" / f"{sid}.json")


# ---- conversations

def cell_dir(model, sid, condition, failed=False):
    return paths.DATA / ("failed" if failed else "conversations") / model / sid / condition


def count_complete(model, sid, condition):
    d = cell_dir(model, sid, condition)
    return len(list(d.glob("*.json"))) if d.exists() else 0


def save_conversation(record, failed=False):
    path = cell_dir(record["model"], record["setup_id"], record["condition"], failed) / f"{record['conv_id']}.json"
    write_json(path, record)
    return path


def iter_conversations():
    """Every complete conversation in the dataset, as (path, record)."""
    base = paths.DATA / "conversations"
    if not base.exists():
        return
    for path in sorted(base.glob("*/*/*/*.json")):
        yield path, read_json(path)


# ---- grades

def grade_path(rubric, judge, conv_id, human=False):
    return paths.DATA / ("human_grades" if human else "grades") / rubric / judge / f"{conv_id}.json"


# ---- ledger and invocations

def ledger(entry):
    """Append one paid call to the ledger."""
    entry = dict(time=utcnow().isoformat(timespec="seconds"), **entry)
    path = paths.DATA / "ledger.jsonl"
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_ledger():
    path = paths.DATA / "ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save_invocation(record):
    write_json(paths.DATA / "invocations" / f"{record['invocation_id']}.json", record)


# ---- reading a reply

def _strings(value):
    """Every piece of text inside a tool call's arguments, unpacking JSON carried as a string."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in "[{":
            try:
                return _strings(json.loads(stripped))
            except ValueError:
                pass
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def rendered_reply(turn):
    """A reply as a reader would see it: its text, plus any document it produced through a tool call."""
    parts = [turn["assistant"].strip()]
    for call in turn.get("tool_calls") or []:
        fn = call.get("function") or {}
        texts = [s for s in _strings(fn.get("arguments") or "") if len(s) >= 80]
        if texts:
            parts.append(f"[The assistant produced this as a separate document, using a tool called {fn.get('name')}:]\n\n" + max(texts, key=len))
    return "\n\n".join(p for p in parts if p)
