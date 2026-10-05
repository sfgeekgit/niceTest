#!/usr/bin/env python3
"""Download the extracted prompts listed in unofficial/manifest.json at their pinned commits."""
import json
import pathlib
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent / "unofficial"


def main():
    manifest = json.loads((HERE / "manifest.json").read_text())
    for f in manifest["files"]:
        if "error" in f:
            continue
        url = f"https://raw.githubusercontent.com/{f['repo']}/{f['commit']}/{f['path']}"
        dest = HERE / f["local"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(urllib.request.urlopen(url, timeout=60).read())
        print(dest.relative_to(HERE))


if __name__ == "__main__":
    main()
