#!/usr/bin/env python3
"""Send one condition's first turn to one model, once, and log everything.

Usage: python3 run_once.py --model haiku-4.5 --condition super_not_remorseful
"""
import argparse
import datetime
import json
import os
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
RESULTS = ROOT / "results"
KEY_FILE = pathlib.Path(os.environ.get("OPENROUTER_KEY_FILE", "~/.config/openrouter/remorse-eval.key")).expanduser()
API = "https://openrouter.ai/api/v1"


def first_message(conditions, name):
    ending = conditions["conditions"][name]
    opener = conditions["opener"]
    return f"{opener}, {ending}" if ending else opener


def system_prompt(model_cfg, now):
    text = (ROOT / model_cfg["system_prompt"]).read_text().rstrip("\n")
    # claude.ai fills this placeholder with the date of the session
    return text.replace("{{currentDateTime}}", now.strftime("%A, %B %d, %Y"))


def post(path, body, key):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode()[:2000]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--condition", required=True)
    args = ap.parse_args()

    models = json.loads((ROOT / "models.json").read_text())
    conditions = json.loads((ROOT / "prompts" / "conditions.json").read_text())
    cfg = models[args.model]
    key = KEY_FILE.read_text().strip()
    now = datetime.datetime.now()

    request = {
        "model": cfg["openrouter_id"],
        # Anthropic's own endpoint only, as claude.ai uses
        "provider": {"order": ["anthropic"], "allow_fallbacks": False},
        "messages": [
            {"role": "system", "content": system_prompt(cfg, now)},
            {"role": "user", "content": first_message(conditions, args.condition)},
        ],
        "reasoning": cfg["reasoning"],
        "max_tokens": cfg["max_tokens"],
        # web search is available in a claude.ai session; the model decides whether to use it
        "tools": [{"type": "openrouter:web_search"}],
        "usage": {"include": True},
    }
    response = post("/chat/completions", request, key)
    key_info = post("/key", None, key).get("data", {})

    usage = response.get("usage", {})
    message = response["choices"][0]["message"]
    stamp = now.strftime("%Y%m%dT%H%M%S")
    record = {
        "timestamp": now.isoformat(timespec="seconds"),
        "model": args.model,
        "condition": args.condition,
        "turn": 1,
        "cost_usd": usage.get("cost"),
        "key_usage_total_usd": key_info.get("usage"),
        "key_limit_remaining_usd": key_info.get("limit_remaining"),
        "request": request,
        "response": response,
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{stamp}_{args.model}_{args.condition}_turn1.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")

    summary = {
        "timestamp": record["timestamp"],
        "model": args.model,
        "openrouter_id": response.get("model"),
        "provider": response.get("provider"),
        "condition": args.condition,
        "turn": 1,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "cost_usd": usage.get("cost"),
        "key_usage_total_usd": key_info.get("usage"),
        "finish_reason": response["choices"][0].get("finish_reason"),
        "file": out.name,
    }
    with (RESULTS / "runs.jsonl").open("a") as f:
        f.write(json.dumps(summary) + "\n")

    print(json.dumps(summary, indent=2))
    print("\n--- USER ---\n" + request["messages"][1]["content"])
    if message.get("reasoning"):
        print("\n--- THINKING ---\n" + message["reasoning"])
    print("\n--- ASSISTANT ---\n" + (message.get("content") or ""))


if __name__ == "__main__":
    main()
