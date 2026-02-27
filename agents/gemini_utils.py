"""
gemini_utils.py v2.3 — Session-Aware Multi-Key, Multi-Model Fallback

Place at: mic-growth-engine/agents/gemini_utils.py

CRITICAL — HOW TO GET MORE QUOTA:
  Each API key must come from a DIFFERENT Gmail/Google account.
  Keys from the same account share ONE quota pool.
  7 keys from 1 account = same as 1 key.
  7 keys from 7 different Gmail accounts = 7x quota.

  Create free accounts at: aistudio.google.com
  Get API key → add to .env as GEMINI_API_KEY_2, _3, _4...

FREE QUOTA PER ACCOUNT (as of Feb 2026):
  gemini-2.0-flash-lite  →  1,500 req/day  ← USE THIS FIRST (highest quota)
  gemini-2.0-flash       →  1,500 req/day  ← second
  gemini-2.5-flash       →  ~50 req/day    ← last resort (preview, very limited)

.env SETUP (one key per Gmail account):
  GEMINI_API_KEY=key_from_gmail_account_1
  GEMINI_API_KEY_2=key_from_gmail_account_2
  GEMINI_API_KEY_3=key_from_gmail_account_3
"""

import os
import re
import json
import time
from datetime import datetime, timezone
from google import genai
from dotenv import load_dotenv

load_dotenv()

# ── MODEL CHAIN ─────────────────────────────────────────────
# ORDER MATTERS: highest free quota first, lowest last
# gemini-2.5-flash is preview — only ~50 req/day free, use last
FALLBACK_MODELS = [
    "gemini-2.0-flash-lite",  # 1,500/day free — fastest, highest quota ← START HERE
    "gemini-2.0-flash",       # 1,500/day free — reliable
    "gemini-2.5-flash",       # ~50/day free preview — last resort only
]

MAX_RETRIES      = 2
QUOTA_STATE_FILE = os.path.join("data", "quota_state.json")


# ── QUOTA STATE ─────────────────────────────────────────────
class _QuotaState:
    def __init__(self):
        self._state = self._load()

    def _today_utc(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self):
        try:
            os.makedirs("data", exist_ok=True)
            with open(QUOTA_STATE_FILE, "r") as f:
                state = json.load(f)
            if state.get("date") != self._today_utc():
                print("[QUOTA STATE] New day — resetting.")
                return self._fresh()
            return state
        except (FileNotFoundError, json.JSONDecodeError):
            return self._fresh()

    def _fresh(self):
        return {"date": self._today_utc(), "exhausted": []}

    def _save(self):
        os.makedirs("data", exist_ok=True)
        with open(QUOTA_STATE_FILE, "w") as f:
            json.dump(self._state, f, indent=2)

    def is_exhausted(self, key_index, model):
        return [key_index, model] in self._state["exhausted"]

    def mark_exhausted(self, key_index, model):
        entry = [key_index, model]
        if entry not in self._state["exhausted"]:
            self._state["exhausted"].append(entry)
            self._save()
            print(f"    [STATE] Marked exhausted: Key {key_index + 1} / {model}")

    def summary(self, api_keys, models):
        total = len(api_keys) * len(models)
        dead  = len(self._state["exhausted"])
        return (f"Quota state ({self._today_utc()}): "
                f"{total - dead}/{total} combinations available, {dead} exhausted.")


_quota_state = _QuotaState()


# ── KEY LOADING ─────────────────────────────────────────────
def _load_api_keys():
    keys, seen = [], set()
    candidates = [
        os.getenv("GEMINI_API_KEY"),
        *[os.getenv(f"GEMINI_API_KEY_{i}") for i in range(2, 11)]
    ]
    for key in candidates:
        if key and key.strip() and key.strip() not in seen:
            keys.append(key.strip())
            seen.add(key.strip())
    if not keys:
        raise ValueError("[FATAL] No Gemini API keys found in .env")
    return keys


# ── MAIN ENTRY POINT ────────────────────────────────────────
def gemini_with_retry(client, build_request_fn, models=None, max_retries=MAX_RETRIES):
    """
    Multi-key, multi-model fallback with session memory.
    Skips exhausted (key, model) pairs instantly — no wasted calls.
    """
    model_chain = models or FALLBACK_MODELS
    api_keys    = _load_api_keys()

    # Check if anything is available before starting
    available = [
        (ki, m) for ki in range(len(api_keys))
        for m in model_chain
        if not _quota_state.is_exhausted(ki, m)
    ]
    if not available:
        raise RuntimeError(
            f"\n[FATAL] {_quota_state.summary(api_keys, model_chain)}\n"
            "All API keys and models are exhausted for today.\n"
            "Solutions:\n"
            "  1. Add more keys: GEMINI_API_KEY_2=... in .env\n"
            "     ⚠️  Each key MUST be from a DIFFERENT Gmail account.\n"
            "     Keys from the same account share one quota pool.\n"
            "  2. Create a new Google AI Studio project at aistudio.google.com\n"
            "  3. Wait until midnight UTC for daily reset"
        )

    self_obj = _extract_self(build_request_fn)

    for key_idx, api_key in enumerate(api_keys):
        key_label = f"Key {key_idx + 1}/{len(api_keys)}"

        alive_models = [m for m in model_chain if not _quota_state.is_exhausted(key_idx, m)]
        if not alive_models:
            print(f"    [SKIP] {key_label} — all models exhausted this session.")
            continue

        try:
            current_client = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"    [KEY] Could not init {key_label}: {e}")
            continue

        for model in model_chain:
            if _quota_state.is_exhausted(key_idx, model):
                continue

            for attempt in range(1, max_retries + 1):
                try:
                    result = _call_with_client(build_request_fn, current_client, model, self_obj)

                    if key_idx > 0 or model != model_chain[0]:
                        print(f"    [FALLBACK] ✓ Used {model} ({key_label})")
                    return result

                except Exception as e:
                    err = str(e)

                    # 404 = model retired/unavailable
                    if "404" in err or "NOT_FOUND" in err:
                        print(f"    [DEAD] {model} — not available (404). Skipping.")
                        _quota_state.mark_exhausted(key_idx, model)
                        break

                    # Non-quota error → raise immediately
                    is_quota = (
                        "429" in err
                        or "RESOURCE_EXHAUSTED" in err
                        or ("quota" in err.lower() and "limit" in err.lower())
                    )
                    if not is_quota:
                        raise

                    # Daily quota exhausted
                    is_daily = (
                        bool(re.search(r"limit['\": ]+0\b", err))
                        or ("quota" in err.lower() and "exceeded" in err.lower())
                    )
                    if is_daily:
                        _quota_state.mark_exhausted(key_idx, model)
                        print(f"    [QUOTA] {model} ({key_label}) daily exhausted → next combo")
                        break

                    # Per-minute rate limit → wait and retry
                    if attempt < max_retries:
                        m = re.search(r"retryDelay['\": ]+(\d+(?:\.\d+)?)", err)
                        wait = float(m.group(1)) + 2 if m else 10 * attempt
                        print(f"    [429] {model} ({key_label}) rate limited. "
                              f"Waiting {wait:.0f}s (attempt {attempt}/{max_retries})...")
                        time.sleep(wait)
                    else:
                        _quota_state.mark_exhausted(key_idx, model)
                        print(f"    [429] {model} ({key_label}) retries exhausted → next combo")

        if key_idx < len(api_keys) - 1:
            remaining = sum(
                1 for ki in range(key_idx + 1, len(api_keys))
                for m in model_chain
                if not _quota_state.is_exhausted(ki, m)
            )
            if remaining > 0:
                print(f"    [KEY] Switching from {key_label} → Key {key_idx + 2} "
                      f"({remaining} combos remaining)")

    raise RuntimeError(
        f"\n[FATAL] {_quota_state.summary(api_keys, model_chain)}\n"
        "All API keys and models are exhausted for today.\n"
        "Solutions:\n"
        "  1. Add more keys: GEMINI_API_KEY_2=... in .env\n"
        "     ⚠️  Each key MUST be from a DIFFERENT Gmail account.\n"
        "     Keys from the same account share one quota pool.\n"
        "  2. Go to aistudio.google.com → sign in with a different Gmail → Get API key\n"
        "  3. Wait until midnight UTC for daily reset"
    )


def print_quota_status():
    api_keys    = _load_api_keys()
    model_chain = FALLBACK_MODELS
    print(f"\n[QUOTA] {_quota_state.summary(api_keys, model_chain)}")
    for ki in range(len(api_keys)):
        for m in model_chain:
            status = "✗ EXHAUSTED" if _quota_state.is_exhausted(ki, m) else "✓ available"
            print(f"  Key {ki + 1} / {m:<28} {status}")
    print()


# ── INTERNAL HELPERS ────────────────────────────────────────
def _extract_self(fn):
    if not callable(fn):
        return None
    try:
        code    = getattr(fn, '__code__', None)
        closure = getattr(fn, '__closure__', None)
        if code and closure and 'self' in code.co_freevars:
            idx = code.co_freevars.index('self')
            obj = closure[idx].cell_contents
            if hasattr(obj, 'client'):
                return obj
    except Exception:
        pass
    return None


def _call_with_client(build_request_fn, client, model, self_obj=None):
    if self_obj is not None:
        original = self_obj.client
        try:
            self_obj.client = client
            return build_request_fn(model)
        finally:
            self_obj.client = original
    return build_request_fn(model)