# PROVIDER-URL-HELPER — dedup provider URL/path construction (self-contained)

You are working in an isolated git worktree checked out from `origin/master`. Everything you
need is in this repo. Do NOT register anywhere, do NOT wait on any other ticket — just make the
change below and stop.

## What's broken

"Take a stored `base_url`, strip trailing slashes, append an endpoint suffix" is reimplemented
inline in several places with subtly different edge-case handling:

- `src/charon/providers.py:175` — `url = base.rstrip("/") + "/models"`
- `src/charon/discover.py:32,34` — `base_url.rstrip("/") + "/models"` and `... + "/v1/models"`
- `src/charon/config/keyprobe.py:37,61` — `raw_base = base_url.rstrip("/")` then
  `raw_base + "/chat/completions"` (and a `/models` variant)

A fix to one copy never propagates to the others. Dedup them behind ONE helper.

## Required change

Add stdlib-only helpers to `src/charon/providers.py` (where `ProviderPreset`/`PRESETS` already
live — the natural home for "turn a preset's base into a concrete URL"). **The two public
helper names are prescribed — use exactly these:**

```python
def models_url(base_url: str) -> str: ...   # returns the resolved /models (or /v1/models) URL
def chat_url(base_url: str) -> str: ...      # returns the resolved /chat/completions URL
```

You may add small internal helpers (e.g. `join_endpoint(base, path)`) as needed, but
`models_url` and `chat_url` MUST be importable from `charon.providers`.

Then replace every inline `rstrip("/") + "<suffix>"` site listed above with a call to the
appropriate helper — in `providers.py`, `discover.py`, and `config/keyprobe.py`.

### Hard constraints

1. **No behavior change to any resolved URL.** Every existing provider preset must resolve to
   the EXACT SAME `/models`, `/v1/models`, and `/chat/completions` URL after this change as
   before — including bases with a non-trivial path such as `https://opencode.ai/zen/v1` or
   `https://opencode.ai/zen/go/v1`. This is a pure dedup refactor, not a routing change.
2. **Keep the existing SSRF / link-local / metadata-host guard unchanged.** If a validation
   guard already exists at a call site, reuse it — do not weaken, remove, or fork a second copy
   of it. Validation-logic-free dedup.
3. **Preserve the `/models` vs `/v1/models` distinction** that `discover.py` makes — the two
   call sites at `discover.py:32` and `:34` resolve to different suffixes for a reason; do not
   collapse them into one.
4. Touch only: `src/charon/providers.py`, `src/charon/discover.py`,
   `src/charon/config/keyprobe.py`, and their tests
   (`tests/test_providers.py`, `tests/test_discover.py`, `tests/test_config.py`). Do NOT edit
   `src/charon/cli.py` or the proxy/forwarder.

## Acceptance (what will be checked)

1. `from charon.providers import models_url, chat_url` succeeds.
2. No inline `rstrip("/") + "/<models|chat/completions>"` construction remains in the three
   source files (the dedup actually happened).
3. `pytest tests/test_providers.py tests/test_discover.py tests/test_config.py` passes
   (no regression — resolved URLs unchanged).
4. **`tests/test_providers.py` contains at least one NEW test function whose name matches
   `test_models_url_*` or `test_chat_url_*`** (e.g. `test_models_url_base_with_path_segment`).
   This is checked mechanically (a grep-by-name over the diff), not just "the suite passes" —
   the pre-existing test suite already passes on an untouched checkout, so re-running it alone
   proves nothing. You MUST add a genuinely new test function under one of those two name
   prefixes that exercises `models_url` / `chat_url` directly (a normal base, and a base with an
   existing path segment such as `https://opencode.ai/zen/v1`) for this ticket to be accepted.

### DOGFOOD_TEST_CMD (discriminating — helper exists + new named test added + dup gone + no regression)

```
PYTHONPATH=src python3 -c "from charon.providers import models_url, chat_url" \
  && python3 -c "import re,sys; c=open('tests/test_providers.py').read(); \
       sys.exit(0 if re.search(r'def test_(models_url|chat_url)_\w+', c) else 1)" \
  && /home/stack/charon-private/fleet/benchmark/lib/grep-code-only.sh \
       'rstrip\("/"\)[[:space:]]*\+[[:space:]]*"/(v1/)?(models|chat/completions)"' \
       src/charon/providers.py src/charon/discover.py src/charon/config/keyprobe.py \
  && PYTHONPATH=src python3 -m pytest tests/test_providers.py tests/test_discover.py tests/test_config.py -q
```

This fails on unmodified `origin/master` today (`models_url`/`chat_url` don't exist yet — the
import alone fails, and separately no `test_models_url_*`/`test_chat_url_*` test name exists
either — two independent reasons it's RED before a fix) and only passes once a real dedup + a
genuinely-named new test are both present (verified against a throwaway `git worktree`,
2026-07-13 — RED-proof=OK per `fleet/benchmark/test-quality-gate.py`, not TOO-EASY).
