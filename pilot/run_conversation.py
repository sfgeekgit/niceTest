#!/usr/bin/env python3
"""Run one conversation (opener, then the fixed follow-up and fixed third turn) and log it.

Usage: python3 pilot/run_conversation.py --model haiku-4.5 --condition neutral --batch haiku_pilot
"""
import argparse
import datetime
import json

from run_once import HERE, KEY_FILE, RESULTS, ROOT, first_message, post, system_prompt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--condition", required=True)
    ap.add_argument("--batch", required=True, help="subdirectory of results/ for this set of runs")
    ap.add_argument("--turns", type=int, default=3, choices=[2, 3], help="user turns to send")
    args = ap.parse_args()

    cfg = json.loads((HERE / "models.json").read_text())[args.model]
    conditions = json.loads((ROOT / "prompts" / "conditions.json").read_text())
    key = KEY_FILE.read_text().strip()
    now = datetime.datetime.now()

    base = {
        "model": cfg["openrouter_id"],
        # Anthropic's own endpoint only, as claude.ai uses
        "provider": {"order": ["anthropic"], "allow_fallbacks": False},
        "reasoning": cfg["reasoning"],
        "max_tokens": cfg["max_tokens"],
        # web search is available in a claude.ai session; the model decides whether to use it
        "tools": [{"type": "openrouter:web_search"}],
        "usage": {"include": True},
    }
    messages = [
        {"role": "system", "content": system_prompt(cfg, now)},
        {"role": "user", "content": first_message(conditions, args.condition)},
    ]
    turns = []
    user_turns = [None, conditions["followup"], conditions["third_turn"]][: args.turns]
    for user_text in user_turns:
        if user_text is not None:
            messages.append({"role": "user", "content": user_text})
        request = dict(base, messages=list(messages))
        response = post("/chat/completions", request, key)
        reply = response["choices"][0]["message"]
        # carry the reply and its thinking blocks into the next turn, as a real session does
        carried = {"role": "assistant", "content": reply.get("content") or ""}
        if reply.get("reasoning_details"):
            carried["reasoning_details"] = reply["reasoning_details"]
        messages.append(carried)
        turns.append({"request": request, "response": response})

    key_info = post("/key", None, key).get("data", {})
    costs = [(t["response"].get("usage") or {}).get("cost") or 0 for t in turns]
    record = {
        "timestamp": now.isoformat(timespec="seconds"),
        "batch": args.batch,
        "model": args.model,
        "condition": args.condition,
        "cost_usd": round(sum(costs), 6),
        "key_usage_total_usd": key_info.get("usage"),
        "turns": turns,
    }
    out_dir = RESULTS / args.batch
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.model}_{args.condition}.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")

    with (RESULTS / "runs.jsonl").open("a") as f:
        for n, t in enumerate(turns, 1):
            usage = t["response"].get("usage") or {}
            f.write(json.dumps({
                "timestamp": record["timestamp"],
                "batch": args.batch,
                "model": args.model,
                "openrouter_id": t["response"].get("model"),
                "provider": t["response"].get("provider"),
                "condition": args.condition,
                "turn": n,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "cost_usd": usage.get("cost"),
                "finish_reason": t["response"]["choices"][0].get("finish_reason"),
                "file": f"{args.batch}/{out.name}",
            }) + "\n")

    print(f"{args.condition}: ${record['cost_usd']:.6f} -> {out}")


if __name__ == "__main__":
    main()
