"""Where things live."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
PROMPTS = ROOT / "prompts"
DATA = pathlib.Path(os.environ.get("REMORSE_EVAL_DATA", ROOT / "data"))
KEY_FILE = pathlib.Path(os.environ.get("OPENROUTER_KEY_FILE", "~/.config/openrouter/remorse-eval.key")).expanduser()
