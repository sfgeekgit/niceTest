"""Command line: python3 -m remorse_eval <command> --help"""
import argparse

from . import analyze, grade, runner, webimport


def main():
    ap = argparse.ArgumentParser(prog="python3 -m remorse_eval", description="Run and grade the remorse experiment.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="run conversations until each cell has --repeats")
    p.add_argument("--models", help="comma-separated model keys, or 'all'")
    p.add_argument("--vendor", help="only models from this vendor (anthropic, openai, google, xai, ...)")
    p.add_argument("--conditions", help="comma-separated remorse levels (default: all five)")
    p.add_argument("--repeats", type=int, default=runner.DEFAULT_REPEATS,
                   help=f"conversations wanted per condition per model (default {runner.DEFAULT_REPEATS}); existing ones count")
    p.add_argument("--claude-prompt", choices=["weblike", "official"],
                   help="system prompt for Claude models; asked interactively if omitted")
    p.add_argument("--prompt-mode", choices=["weblike", "dateonly"], default="weblike",
                   help="system prompt for non-Claude models (default weblike)")
    p.add_argument("--max-spend", type=float, default=1.00, help="stop starting conversations at this many dollars (default 1.00)")
    p.add_argument("--workers", type=int, default=4, help="conversations in parallel (default 4)")
    p.add_argument("--seed", type=int, help="seed for the random order of conversations")
    p.add_argument("--dry-run", action="store_true", help="show the plan and estimate, then stop")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=runner.run)

    p = sub.add_parser("models", help="list the candidate models")
    p.set_defaults(func=runner.list_models)

    p = sub.add_parser("status", help="show what the dataset holds")
    p.set_defaults(func=runner.status)

    p = sub.add_parser("import-web", help="file a hand-run web chat as a conversation")
    webimport.add_arguments(p)
    p.set_defaults(func=webimport.run)

    p = sub.add_parser("grade", help="grade ungraded conversations with the judge models")
    grade.add_arguments(p)
    p.set_defaults(func=grade.run)

    p = sub.add_parser("human-grade", help="grade a blind sample by hand")
    grade.add_human_arguments(p)
    p.set_defaults(func=grade.run_human)

    p = sub.add_parser("analyze", help="rebuild the summary tables and report")
    p.set_defaults(func=analyze.run)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
