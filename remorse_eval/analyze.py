"""Rebuild the summary tables and the report from the raw data. Everything here is derived."""
import collections
import csv
import math
import random

from . import grade, paths, store

LABELS = {1: "refuses", 2: "argues against", 3: "asks first", 4: "writes letter"}
SHORT = {"super_remorseful": "super remorseful", "remorseful": "remorseful", "neutral": "neutral",
         "not_remorseful": "not remorseful", "super_not_remorseful": "super not remorseful"}


def wilson(k, n, z=1.96):
    """95% interval for a proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks, i = [0.0] * len(values), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs, ys):
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def trend(xs, ys, permutations=5000):
    """Spearman correlation between remorse order and an outcome, with a permutation p-value."""
    rho = spearman(xs, ys)
    if rho is None:
        return None, None
    rng, ys, extreme = random.Random(0), list(ys), 0
    for _ in range(permutations):
        rng.shuffle(ys)
        r = spearman(xs, ys)
        if r is not None and abs(r) >= abs(rho) - 1e-12:
            extreme += 1
    return rho, (extreme + 1) / (permutations + 1)


def kappa(pairs):
    """Cohen's kappa for two raters over the same items."""
    if not pairs:
        return None
    n = len(pairs)
    agree = sum(a == b for a, b in pairs) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    chance = sum(ca[k] * cb[k] for k in ca) / (n * n)
    return (agree - chance) / (1 - chance) if chance < 1 else 1.0


def load():
    convs = [rec for _, rec in store.iter_conversations()]
    grades = collections.defaultdict(dict)  # conv_id -> {(kind, judge): grade}
    for kind in ("grades", "human_grades"):
        base = paths.DATA / kind / grade.RUBRIC
        if base.exists():
            for path in sorted(base.glob("*/*.json")):
                g = store.read_json(path)
                grades[g["conv_id"]][("human" if kind == "human_grades" else "judge", g["judge"])] = g
    return convs, grades


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return out + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


def run(args):
    convs, grades = load()
    if not convs:
        print("No conversations yet.")
        return
    out = paths.DATA / "summary"
    primary = next(iter(grade.judges_config()))

    # conversations.csv
    rows = []
    for c in convs:
        row = [c["conv_id"], c["model"], c["setup_id"], c["source"], c["condition"], c["started_at"][:10], c["cost_usd"]]
        for t in c["turns"]:
            text = t["assistant"].strip()
            row += [len(text), len(t.get("reasoning") or ""), text.endswith("?")]
        rows.append(row + [c["flags"].get("artifact_markup")])
    write_csv(out / "conversations.csv",
              ["conv_id", "model", "setup_id", "source", "condition", "date", "cost_usd",
               "reply1_chars", "reasoning1_chars", "reply1_ends_question", "reply2_chars", "reasoning2_chars", "reply2_ends_question",
               "reply3_chars", "reasoning3_chars", "reply3_ends_question", "artifact_markup"], rows)

    # grades.csv
    fields = ["warned", "alternatives", "letter_outcome", "letter_quality", "warmth", "effort", "challenges_user", "mentions_remorse"]
    by_id = {c["conv_id"]: c for c in convs}
    rows = []
    for conv_id, per in grades.items():
        c = by_id.get(conv_id)
        if not c:
            continue
        for (kind, judge), g in per.items():
            for turn, scores in sorted(g["replies"].items()):
                rows.append([conv_id, c["model"], c["setup_id"], c["source"], c["condition"], kind, judge, turn] + [scores.get(f) for f in fields])
    write_csv(out / "grades.csv", ["conv_id", "model", "setup_id", "source", "condition", "kind", "judge", "turn"] + fields, rows)

    # costs.csv
    spend = collections.defaultdict(lambda: [0, 0.0])
    for row in store.read_ledger():
        k = (row.get("purpose"), row.get("model") or row.get("judge"))
        spend[k][0] += 1
        spend[k][1] += row.get("cost_usd") or 0
    write_csv(out / "costs.csv", ["purpose", "model_or_judge", "calls", "cost_usd"],
              [[p, m, n, round(cost, 6)] for (p, m), (n, cost) in sorted(spend.items())])

    # report.md
    lines = ["# Results report", "",
             "Rebuilt from the raw data by `python3 -m remorse_eval analyze`. Do not edit by hand.", "",
             f"{len(convs)} conversations; outcome tables use the primary judge, `{primary}`.", ""]
    groups = collections.defaultdict(list)
    for c in convs:
        groups[(c["model"], c["setup_id"])].append(c)

    def scores_for(c, turn, who=("judge", primary)):
        g = grades.get(c["conv_id"], {}).get(who)
        return g["replies"].get(turn) if g else None

    for (model, sid), members in sorted(groups.items()):
        lines += [f"## {model}, setup `{sid}`", ""]
        counts = collections.Counter(c["condition"] for c in members)
        smallest = min(counts.get(cond, 0) for cond in store.CONDITIONS)
        if smallest < 10:
            lines += [f"Only {smallest} conversation(s) in the smallest cell. Too few to show an effect; treat everything below as a check that the pipeline works.", ""]
        for turn, title in (("2", "Second reply (asked for the letter)"), ("3", "Third reply (\"just write the letter\")")):
            table, xs, ys = [], [], []
            for i, cond in enumerate(store.CONDITIONS):
                graded = [s for s in (scores_for(c, turn) for c in members if c["condition"] == cond) if s]
                levels = collections.Counter(s["letter_outcome"] for s in graded)
                wrote, n = levels.get(4, 0), len(graded)
                lo, hi = wilson(wrote, n)
                table.append([SHORT[cond], counts.get(cond, 0), n] + [levels.get(k, 0) for k in (1, 2, 3, 4)]
                             + [f"{100 * wrote / n:.0f}% ({100 * lo:.0f}-{100 * hi:.0f})" if n else "-"])
                xs += [i] * n
                ys += [s["letter_outcome"] for s in graded]
            lines += [f"### {title}", ""]
            lines += _table(["Condition", "Conversations", "Graded"] + [LABELS[k] for k in (1, 2, 3, 4)] + ["Wrote letter (95% interval)"], table)
            rho, p = trend(xs, ys)
            lines += ["", "Trend from most to least remorseful (positive means more willing to write as remorse falls): "
                      + (f"Spearman rho {rho:+.2f}, permutation p = {p:.3f}." if rho is not None else "not computable yet."), ""]
        table, xs, ys = [], [], []
        for i, cond in enumerate(store.CONDITIONS):
            both = [(scores_for(c, "2"), scores_for(c, "3")) for c in members if c["condition"] == cond]
            ends = [max(a["letter_outcome"], b["letter_outcome"]) == 4 for a, b in both if a and b]
            wrote, n = sum(ends), len(ends)
            lo, hi = wilson(wrote, n)
            table.append([SHORT[cond], counts.get(cond, 0), n, wrote, f"{100 * wrote / n:.0f}% ({100 * lo:.0f}-{100 * hi:.0f})" if n else "-"])
            xs += [i] * n
            ys += [int(e) for e in ends]
        lines += ["### By the end of the conversation", "",
                  "Whether a letter had been written in the second or the third reply. This is the headline outcome.", ""]
        lines += _table(["Condition", "Conversations", "Graded", "Letter written", "Rate (95% interval)"], table)
        rho, p = trend(xs, ys)
        lines += ["", "Trend from most to least remorseful (positive means a letter is more likely as remorse falls): "
                  + (f"Spearman rho {rho:+.2f}, permutation p = {p:.3f}." if rho is not None else "not computable yet."), ""]
        table, xs, ys = [], [], []
        for i, cond in enumerate(store.CONDITIONS):
            cell = [c for c in members if c["condition"] == cond]
            graded = [s for s in (scores_for(c, "1") for c in cell) if s]
            chars = [len(c["turns"][0]["assistant"]) for c in cell]
            table.append([SHORT[cond], len(cell), f"{sum(chars) / len(chars):.0f}" if chars else "-",
                          f"{sum(s['warmth'] for s in graded) / len(graded):.1f}" if graded else "-",
                          f"{sum(s['effort'] for s in graded) / len(graded):.1f}" if graded else "-"])
            xs += [i] * len(graded)
            ys += [s["warmth"] for s in graded]
        lines += ["### First reply", ""] + _table(["Condition", "Conversations", "Mean length (characters)", "Mean warmth (1-5)", "Mean effort (1-5)"], table)
        rho, p = trend(xs, ys)
        lines += ["", "Warmth trend from most to least remorseful: "
                  + (f"Spearman rho {rho:+.2f}, permutation p = {p:.3f}." if rho is not None else "not computable yet."), ""]

    # agreement
    lines += ["## Agreement between graders", ""]
    raters = sorted({who for per in grades.values() for who in per})
    table = []
    for a in raters:
        for b in raters:
            if a >= b:
                continue
            pairs = []
            for per in grades.values():
                if a in per and b in per:
                    for turn in ("2", "3"):
                        sa, sb = per[a]["replies"].get(turn), per[b]["replies"].get(turn)
                        if sa and sb:
                            pairs.append((sa["letter_outcome"], sb["letter_outcome"]))
            if pairs:
                k = kappa(pairs)
                table.append([f"{a[1]} ({a[0]})", f"{b[1]} ({b[0]})", len(pairs),
                              f"{100 * sum(x == y for x, y in pairs) / len(pairs):.0f}%", f"{k:.2f}" if k is not None else "-"])
    lines += (_table(["Grader", "Grader", "Replies both graded", "Same letter outcome", "Cohen's kappa"], table)
              if table else ["No reply has been graded by two graders yet."]) + [""]

    # web against API
    lines += ["## Web against API, same model", ""]
    table = []
    for model in sorted({c["model"] for c in convs}):
        for source in ("web", "api"):
            members = [c for c in convs if c["model"] == model and c["source"] == source]
            if not members or not any(c["source"] == "web" for c in convs if c["model"] == model):
                continue
            row = [model, source, len(members), f"{sum(len(c['turns'][0]['assistant']) for c in members) / len(members):.0f}"]
            for turn in ("2", "3"):
                graded = [s for s in (scores_for(c, turn) for c in members) if s]
                row.append(f"{sum(s['letter_outcome'] == 4 for s in graded)} of {len(graded)}" if graded else "-")
            both = [(scores_for(c, "2"), scores_for(c, "3")) for c in members]
            ends = [max(a["letter_outcome"], b["letter_outcome"]) == 4 for a, b in both if a and b]
            row.append(f"{sum(ends)} of {len(ends)}" if ends else "-")
            table.append(row)
    lines += (_table(["Model", "Source", "Conversations", "Mean first-reply length", "Wrote letter, second reply", "Wrote letter, third reply", "Letter by the end"], table)
              if table else ["No model has both web and API conversations yet."]) + ["",
              "API rows pool every API setup for the model; see the per-setup sections above for each one.", ""]

    total = sum(cost for _, cost in spend.values())
    lines += ["## Spend", "", f"${total:.2f} in total across {sum(n for n, _ in spend.values())} paid calls. See `costs.csv`.", ""]
    (out / "report.md").write_text("\n".join(lines))
    print(f"Wrote {out}/conversations.csv, grades.csv, costs.csv and report.md")
