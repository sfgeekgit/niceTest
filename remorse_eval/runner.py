"""Run conversations: plan what is missing, show the cost, then fill the cells."""
import concurrent.futures
import datetime
import json
import random
import re
import sys
import threading

from . import api, paths, prompts, store

DEFAULT_REPEATS = 5
MAX_TOOL_ROUNDS = 3
TOOL_ACK = "OK"
ARTIFACT_MARKUP = re.compile(r"<antArtifact|<artifact\b|<function_calls>|<invoke\b|```artifact|\bcreate_file\b", re.I)

CLAUDE_QUESTION = """
This run includes Claude models. Which system prompt should they get?

  1. weblike   the long claude.ai prompt as extracted from the web app, including its tool
               sections. Closest known match to the website. Unofficial. Roughly {ratio}x the
               input tokens of the official prompt.
  2. official  the shorter prompt Anthropic publishes. Verifiable and cheaper, but the pilots
               suggest it is further from how the website behaves.

Choice [1]: """


def load_models():
    cfg = store.read_json(paths.CONFIG / "models.json")
    return cfg["models"], cfg["defaults"]


def select_models(models, names=None, vendor=None):
    if names in (None, "") and not vendor:
        raise SystemExit("Choose models with --models a,b,c, --models all, or --vendor NAME.")
    keys = list(models)
    if names and names != "all":
        keys = [k.strip() for k in names.split(",") if k.strip()]
        unknown = [k for k in keys if k not in models]
        if unknown:
            raise SystemExit(f"Unknown model(s): {', '.join(unknown)}. See: python3 -m remorse_eval models")
    if vendor:
        keys = [k for k in keys if models[k]["vendor"] == vendor]
    if not keys:
        raise SystemExit("No models selected.")
    return keys


def effective_label(source_id):
    if source_id == "dateonly":
        return "dateonly"
    return "official" if "/official/" in source_id else "weblike"


def build_setup(model_key, mcfg, defaults, mode, location, register=True):
    """The setup a model would run under in a given prompt mode, and its id."""
    source_id = prompts.source_for(mcfg, mode)
    described = prompts.describe(source_id)
    setup = {
        "source": "api",
        "model": {"key": model_key, "openrouter_id": mcfg["openrouter_id"]},
        "system_prompt": {"id": described["id"], "sha256": described["sha256"]},
        "location": location if described["kind"] == "extracted" else None,
        "reasoning": mcfg.get("reasoning"),
        "max_tokens": mcfg.get("max_tokens", defaults["max_tokens"]),
        "tools": mcfg.get("tools", defaults["tools"]),
        "provider": mcfg.get("provider"),
        "cache_system_prompt": bool(mcfg.get("cache_system_prompt")),
        "messages_sha256": store.messages_sha256(),
        "protocol": store.PROTOCOL,
    }
    return setup, store.setup_id(setup, effective_label(source_id), register)


def ask_claude_prompt(models, keys, given):
    """Decide the prompt mode for Claude models, asking if nobody said."""
    claude = [k for k in keys if models[k]["vendor"] == "anthropic"]
    if not claude or given:
        return given or "weblike"
    if not sys.stdin.isatty():
        raise SystemExit("This run includes Claude models. Pass --claude-prompt weblike or --claude-prompt official.")
    ratios = []
    for k in claude:
        p = models[k]["prompts"]
        if p.get("weblike") and p["weblike"] != p.get("official"):
            try:
                long_text, _ = prompts.build(p["weblike"])
                short_text, _ = prompts.build(p["official"])
                ratios.append(len(long_text) / len(short_text))
            except FileNotFoundError:
                pass
    ratio = f"{sum(ratios) / len(ratios):.0f}" if ratios else "several"
    answer = input(CLAUDE_QUESTION.format(ratio=ratio)).strip().lower()
    return "official" if answer in ("2", "official") else "weblike"


def estimate_cost(model_key, mcfg, setup, sid, prices, ledger_rows):
    """Rough dollars per conversation: measured mean if this setup has run before, else from prices."""
    measured = {}
    for row in ledger_rows:
        if row.get("purpose") == "conversation" and row.get("model") == model_key and row.get("setup_id") == sid:
            measured[row["conv_id"]] = measured.get(row["conv_id"], 0) + (row.get("cost_usd") or 0)
    if measured:
        return sum(measured.values()) / len(measured), "measured"
    snapshot = mcfg["price_per_mtok"]
    p_in, p_out = prices.get(mcfg["openrouter_id"], (snapshot["input"], snapshot["output"]))
    text, _ = prompts.build(setup["system_prompt"]["id"])
    system_tokens = len(text) / 3.6
    # three turns each resend the system prompt; caching makes the repeats cheap
    system_equiv = system_tokens * (1.25 + 0.2 if setup["cache_system_prompt"] else 3)
    return ((system_equiv + 3000) * p_in + 3000 * p_out) / 1e6, "estimated"


def request_body(setup, messages):
    body = {
        "model": setup["model"]["openrouter_id"],
        "messages": messages,
        "max_tokens": setup["max_tokens"],
        "usage": {"include": True},
    }
    for field in ("reasoning", "tools", "provider"):
        if setup.get(field):
            body[field] = setup[field]
    return body


def run_conversation(task, key, invocation_id, today):
    """One three-turn conversation. Returns (record, failed)."""
    setup, started = task["setup"], store.utcnow()
    text, meta = prompts.build(setup["system_prompt"]["id"], today, setup["location"])
    system = {"role": "system", "content": text}
    if setup["cache_system_prompt"]:
        system["content"] = [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
    messages, turns, error = [system], [], None
    conv_id = store.new_id(started)

    for n, user_text in enumerate(store.user_turns(task["condition"]), 1):
        messages.append({"role": "user", "content": user_text})
        texts, calls, rounds, reasoning, cost = [], [], [], [], 0.0
        while True:
            try:
                response, seconds = api.chat(request_body(setup, messages), key)
            except api.ApiError as e:
                if rounds:  # the acknowledgement was not accepted; keep what the model produced
                    rounds[-1]["acknowledgement_rejected"] = str(e)[:300]
                else:
                    error = f"turn {n}: {e}"
                break
            choice = response["choices"][0]
            reply = choice["message"]
            usage = response.get("usage") or {}
            content = reply.get("content") or ""
            cost += usage.get("cost") or 0
            texts.append(content)
            calls += reply.get("tool_calls") or []
            if reply.get("reasoning"):
                reasoning.append(reply["reasoning"])
            rounds.append({"finish_reason": choice.get("finish_reason"), "usage": usage, "cost_usd": usage.get("cost"),
                           "provider": response.get("provider"), "response_id": response.get("id"),
                           "annotations": reply.get("annotations"), "latency_s": round(seconds, 2)})
            store.ledger({
                "purpose": "conversation", "invocation_id": invocation_id, "conv_id": conv_id,
                "model": task["model"], "setup_id": task["setup_id"], "condition": task["condition"], "turn": n,
                "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                "cost_usd": usage.get("cost"),
            })
            carried = {"role": "assistant", "content": content}
            if reply.get("reasoning_details"):
                # thinking is carried forward, as a real session does
                carried["reasoning_details"] = reply["reasoning_details"]
            wants_tool = choice.get("finish_reason") == "tool_calls" and reply.get("tool_calls")
            if wants_tool and len(rounds) <= MAX_TOOL_ROUNDS:
                # A long web-style prompt describes tools (documents, drafts) that are not really
                # there. The call is acknowledged so the model can finish its turn; what it put in
                # the call, usually the letter, is kept in tool_calls.
                carried["tool_calls"] = reply["tool_calls"]
                messages.append(carried)
                messages += [{"role": "tool", "tool_call_id": c.get("id"), "content": TOOL_ACK} for c in reply["tool_calls"]]
                continue
            messages.append(carried)
            break
        if error:
            break
        turns.append({
            "user": user_text,
            "assistant": "\n\n".join(t for t in texts if t.strip()),
            "reasoning": "\n\n".join(reasoning) or None,
            "tool_calls": calls or None,
            "finish_reason": rounds[-1]["finish_reason"],
            "rounds": rounds,
            "cost_usd": round(cost, 6),
            "provider": rounds[-1]["provider"],
        })
        if not turns[-1]["assistant"].strip() and not calls:
            error = f"turn {n}: empty reply (finish_reason={rounds[-1]['finish_reason']})"
            break

    record = {
        "schema": store.SCHEMA,
        "conv_id": conv_id,
        "model": task["model"],
        "setup_id": task["setup_id"],
        "condition": task["condition"],
        "source": "api",
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": store.utcnow().isoformat(timespec="seconds"),
        "invocation_id": invocation_id,
        "system_prompt": {k: meta.get(k) for k in ("id", "sha256", "date_filled", "location_filled", "date_appended", "warnings")},
        "turns": turns,
        "cost_usd": round(sum(t["cost_usd"] or 0 for t in turns), 6),
        "flags": {"artifact_markup": any(ARTIFACT_MARKUP.search(t["assistant"]) for t in turns),
                  "tool_calls": sorted({(c.get("function") or {}).get("name") or "?" for t in turns for c in t["tool_calls"] or []})},
    }
    if error:
        record["error"] = error
    return record, bool(error)


def run(args):
    models, defaults = load_models()
    keys = select_models(models, args.models, args.vendor)
    conditions = args.conditions.split(",") if args.conditions else store.CONDITIONS
    bad = [c for c in conditions if c not in store.CONDITIONS]
    if bad:
        raise SystemExit(f"Unknown condition(s): {', '.join(bad)}")
    location = prompts.load_config()["default_location"]
    claude_mode = ask_claude_prompt(models, keys, args.claude_prompt)

    prices, ledger_rows = api.live_prices(), store.read_ledger()
    tasks, plan = [], []
    for k in keys:
        mode = claude_mode if models[k]["vendor"] == "anthropic" else args.prompt_mode
        try:
            setup, sid = build_setup(k, models[k], defaults, mode, location, register=not args.dry_run)
        except FileNotFoundError as e:
            raise SystemExit(str(e))
        have = {c: store.count_complete(k, sid, c) for c in conditions}
        need = {c: max(0, args.repeats - have[c]) for c in conditions}
        each, basis = estimate_cost(k, models[k], setup, sid, prices, ledger_rows)
        plan.append({"model": k, "setup_id": sid, "have": sum(have.values()), "to_run": sum(need.values()),
                     "per_conversation_usd": round(each, 4), "basis": basis, "estimate_usd": round(each * sum(need.values()), 2)})
        for c in conditions:
            tasks += [{"model": k, "setup": setup, "setup_id": sid, "condition": c, "estimate": each}] * need[c]

    total = sum(p["estimate_usd"] for p in plan)
    print(f"\nPlan: {args.repeats} per condition, {len(conditions)} condition(s), {len(keys)} model(s)\n")
    print(f"{'model':28s} {'setup':28s} {'have':>5s} {'to run':>7s} {'each':>9s} {'estimate':>9s}")
    for p in plan:
        print(f"{p['model']:28s} {p['setup_id']:28s} {p['have']:5d} {p['to_run']:7d} "
              f"{'$%.4f' % p['per_conversation_usd']:>9s} {'$%.2f' % p['estimate_usd']:>9s}  ({p['basis']})")
    print(f"\n{len(tasks)} conversation(s) to run, estimated ${total:.2f}. Spending stops at ${args.max_spend:.2f} (--max-spend).")
    if not tasks:
        print("Nothing to do: every cell already has the requested number.")
        return
    if args.dry_run:
        return
    if not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit("Not running without confirmation. Pass --yes to run unattended.")
        if input("Run it? [y/N]: ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return

    key = api.api_key()
    invocation_id = store.new_id()
    today = datetime.date.today()
    random.Random(args.seed if args.seed is not None else invocation_id).shuffle(tasks)
    lock = threading.Lock()
    state = {"spent": 0.0, "committed": 0.0, "done": 0, "failed": 0, "skipped": 0}

    def work(task):
        with lock:
            # count conversations still in flight at their estimate so the ceiling is not overshot
            if state["spent"] + state["committed"] + task["estimate"] > args.max_spend:
                state["skipped"] += 1
                return
            state["committed"] += task["estimate"]
        record, failed = run_conversation(task, key, invocation_id, today)
        store.save_conversation(record, failed)
        with lock:
            state["committed"] -= task["estimate"]
            state["spent"] += record["cost_usd"]
            state["failed" if failed else "done"] += 1
            mark = "FAILED " + record.get("error", "") if failed else "ok"
            print(f"  [{state['done'] + state['failed']}/{len(tasks)}] {task['model']} {task['condition']} "
                  f"${record['cost_usd']:.4f} (total ${state['spent']:.2f}) {mark[:120]}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, tasks))

    store.save_invocation({
        "invocation_id": invocation_id, "command": "run", "started_on": today.isoformat(),
        "arguments": {k: v for k, v in vars(args).items() if k != "func"},
        "claude_prompt": claude_mode, "plan": plan,
        "completed": state["done"], "failed": state["failed"], "not_run_spend_ceiling": state["skipped"],
        "spent_usd": round(state["spent"], 6),
    })
    print(f"\nDone: {state['done']} complete, {state['failed']} failed, {state['skipped']} not run (spend ceiling). "
          f"Spent ${state['spent']:.4f}.")
    if state["skipped"]:
        print("Run the same command again with a higher --max-spend to fill the remaining cells.")


def list_models(args):
    models, _ = load_models()
    print(f"{'model':28s} {'vendor':12s} {'in/out per 1M':>16s}  weblike prompt")
    for k, m in models.items():
        p = m["price_per_mtok"]
        prompt = m["prompts"].get("weblike") or "(date line only)"
        print(f"{k:28s} {m['vendor']:12s} {'$%g / $%g' % (p['input'], p['output']):>16s}  {prompt}")
    print(f"\n{len(models)} models. Prices as of {next(iter(models.values()))['price_per_mtok']['as_of']}.")


def status(args):
    """What the dataset holds: conversations per cell and spend."""
    cells = {}
    for _, rec in store.iter_conversations():
        cells.setdefault((rec["model"], rec["setup_id"]), {}).setdefault(rec["condition"], 0)
        cells[(rec["model"], rec["setup_id"])][rec["condition"]] += 1
    if not cells:
        print("No conversations yet.")
    else:
        short = ["s_rem", "rem", "neut", "not", "s_not"]
        print(f"{'model':28s} {'setup':30s} " + " ".join(f"{s:>5s}" for s in short))
        for (model, sid), counts in sorted(cells.items()):
            print(f"{model:28s} {sid:30s} " + " ".join(f"{counts.get(c, 0):5d}" for c in store.CONDITIONS))
    spend = {}
    for row in store.read_ledger():
        spend[row.get("purpose", "?")] = spend.get(row.get("purpose", "?"), 0) + (row.get("cost_usd") or 0)
    if spend:
        print("\nSpend: " + ", ".join(f"{k} ${v:.4f}" for k, v in sorted(spend.items())) + f"; total ${sum(spend.values()):.4f}")
