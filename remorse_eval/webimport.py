"""File a hand-run web chat as a conversation in the dataset.

The person sends the three fixed messages on the vendor's website, copies the whole chat,
and pastes it into a file. Because the user messages are fixed strings, the paste can be
split into turns without any markup.
"""
import datetime
import hashlib
import re
import sys

from . import store

NOISE_LINES = {"Claude finished the response", "No history, memory, or Claude training."}


def add_arguments(p):
    p.add_argument("--model", required=True, help="model key, e.g. claude-opus-4.6")
    p.add_argument("--condition", required=True, choices=store.CONDITIONS)
    p.add_argument("--file", required=True, help="file holding the pasted chat, or - for standard input")
    p.add_argument("--product", default="claude.ai", help="the website used (default claude.ai)")
    p.add_argument("--effort", default="medium", help="effort setting shown in the web app (default medium)")
    p.add_argument("--thinking", default="on", choices=["on", "off"], help="extended thinking (default on)")
    p.add_argument("--not-incognito", action="store_true", help="the chat was not an incognito chat")
    p.add_argument("--collected-on", help="date the chat was run, YYYY-MM-DD (default today)")
    p.add_argument("--collector", default="hand", help="who or what collected it (default hand)")
    p.add_argument("--letter-format", choices=["inline", "artifact", "none"], help="how the letter appeared, if one was written")
    p.add_argument("--network", help="where the browser was connecting from, if known")
    p.add_argument("--pilot-md", action="store_true", help="the file is a pilot transcript in results/*_web_manual/ format")


def _strip_thinking_title(block):
    """The web app shows a one-line thinking title, which a copy captures twice."""
    lines = block.split("\n")
    solid = [i for i, line in enumerate(lines) if line.strip()]
    if len(solid) >= 2 and lines[solid[0]].strip() == lines[solid[1]].strip():
        title = lines[solid[0]].strip()
        return "\n".join(lines[solid[1] + 1:]).strip(), title
    return block.strip(), None


def parse_paste(text, users):
    """Split a pasted chat on the three known user messages. Returns a list of turns."""
    text = "\n".join(line for line in text.replace("\r\n", "\n").split("\n") if line.strip() not in NOISE_LINES)
    positions, start = [], 0
    for user in users:
        at = text.find(user, start)
        if at < 0:
            raise SystemExit(f"Could not find this user message in the paste, in order:\n  {user}")
        positions.append(at)
        start = at + len(user)
    turns = []
    for n, user in enumerate(users):
        end = positions[n + 1] if n + 1 < len(users) else len(text)
        block = text[positions[n] + len(user):end]
        reply, title = _strip_thinking_title(block)
        if not reply:
            raise SystemExit(f"No reply found after user message {n + 1}.")
        turns.append({"user": user, "assistant": reply, "reasoning": None, "reasoning_title": title})
    return turns


def parse_pilot_md(text, users):
    """Read a transcript written during the pilots (## User N / ## Thinking N / ## Assistant N)."""
    sections = dict((m.group(1).strip(), m.group(2).strip())
                    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M))
    turns = []
    for n, user in enumerate(users, 1):
        if sections.get(f"User {n}") != user:
            raise SystemExit(f"User message {n} in the file does not match the fixed message.")
        title = next((v for k, v in sections.items() if k.startswith(f"Thinking {n}")), None)
        turns.append({"user": user, "assistant": sections[f"Assistant {n}"], "reasoning": None, "reasoning_title": title})
    return turns


def run(args):
    raw = sys.stdin.read() if args.file == "-" else open(args.file).read()
    users = store.user_turns(args.condition)
    turns = parse_pilot_md(raw, users) if args.pilot_md else parse_paste(raw, users)
    collected = datetime.date.fromisoformat(args.collected_on) if args.collected_on else datetime.date.today()

    setup = {
        "source": "web",
        "model": {"key": args.model, "product": args.product},
        "system_prompt": {"id": "none", "sha256": None},
        "web_settings": {"effort": args.effort, "thinking": args.thinking, "incognito": not args.not_incognito},
        "messages_sha256": store.messages_sha256(),
        "protocol": store.PROTOCOL,
    }
    sid = store.setup_id(setup, f"web-{args.product}")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    for _, rec in store.iter_conversations():
        if rec.get("web", {}).get("paste_sha256") == digest:
            raise SystemExit(f"This paste is already in the dataset as {rec['conv_id']}.")

    now = store.utcnow()
    record = {
        "schema": store.SCHEMA,
        "conv_id": store.new_id(now),
        "model": args.model,
        "setup_id": sid,
        "condition": args.condition,
        "source": "web",
        "started_at": collected.isoformat(),
        "finished_at": collected.isoformat(),
        "invocation_id": None,
        "system_prompt": {"id": "none"},
        "turns": turns,
        "cost_usd": None,
        "flags": {"artifact_markup": False},
        "web": {
            "collected_by": args.collector, "collected_on": collected.isoformat(), "imported_at": now.isoformat(timespec="seconds"),
            "letter_format": args.letter_format, "network": args.network,
            "paste_sha256": digest, "raw_paste": raw,
        },
    }
    path = store.save_conversation(record)
    print(f"Saved {record['conv_id']} ({args.model}, {args.condition}) to {path}")
    for n, t in enumerate(turns, 1):
        print(f"  reply {n}: {len(t['assistant'])} characters" + (f", thinking title: {t['reasoning_title']}" if t["reasoning_title"] else ""))
