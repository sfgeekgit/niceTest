#!/usr/bin/env python3
"""Regenerate docs/index.md (the project page) from README.md. Edit the README, then run this."""
import pathlib
import re

REPO = "https://github.com/sfgeekgit/remorse-eval"
ROOT = pathlib.Path(__file__).resolve().parent.parent


def absolute(match):
    text, target = match.group(1), match.group(2)
    if re.match(r"https?://|#", target):
        return match.group(0)
    kind = "tree" if target.endswith("/") else "blob"
    return f"[{text}]({REPO}/{kind}/main/{target})"


def main():
    readme = (ROOT / "README.md").read_text()
    # the page theme prints the title itself
    body = re.sub(r"\A# .*\n+", "", readme)
    # links to files in the repo do not resolve on the site
    body = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", absolute, body)
    body = body.replace("(Details in the results directory)", f"(Details in the [results directory]({REPO}/tree/main/results))")
    (ROOT / "docs" / "index.md").write_text(f"[View the repository on GitHub]({REPO})\n\n{body}")


if __name__ == "__main__":
    main()
