"""Thin OpenRouter client. Standard library only."""
import json
import time
import urllib.error
import urllib.request

from .paths import KEY_FILE

BASE = "https://openrouter.ai/api/v1"
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 520, 522, 524, 529}


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def api_key():
    if not KEY_FILE.exists():
        raise SystemExit(f"No OpenRouter key file at {KEY_FILE}. Put a key there or set OPENROUTER_KEY_FILE.")
    return KEY_FILE.read_text().strip()


def _request(method, path, body=None, key=None, timeout=900):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode(errors="replace"))


def chat(body, key, retries=3):
    """One chat completion. Retries transient failures. Returns (response, seconds)."""
    delay = 5
    for attempt in range(retries + 1):
        started = time.time()
        try:
            response = _request("POST", "/chat/completions", body, key)
            # OpenRouter reports some upstream failures inside a 200 response
            if "error" in response and "choices" not in response:
                code = (response["error"] or {}).get("code")
                raise ApiError(code if isinstance(code, int) else 502, json.dumps(response["error"]))
            return response, time.time() - started
        except ApiError as e:
            if e.status not in RETRY_STATUS or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == retries:
                raise ApiError(0, f"network error: {e}")
        time.sleep(delay)
        delay *= 3


def key_info(key):
    return _request("GET", "/key", key=key, timeout=30).get("data", {})


def live_prices():
    """{openrouter_id: (input, output)} in dollars per million tokens, or {} if unavailable."""
    try:
        data = _request("GET", "/models", timeout=30)["data"]
    except Exception:
        return {}
    prices = {}
    for m in data:
        try:
            prices[m["id"]] = (float(m["pricing"]["prompt"]) * 1e6, float(m["pricing"]["completion"]) * 1e6)
        except (KeyError, TypeError, ValueError):
            pass
    return prices
