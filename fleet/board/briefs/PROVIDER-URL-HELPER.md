# SESSION — PROVIDER-URL-HELPER: dedup provider URL/path construction

**Model:** strong tier — refactor touching three files with subtle "don't change any
resolved URL" correctness bar.
**Repo:** charon · **Ticket:** PROVIDER-URL-HELPER
**Base branch/worktree:** `refactor/provider-url-helper` at
`/home/stack/code/charon-fleet-PROVIDER-URL-HELPER` (an isolated worktree off latest
`origin/master` — do NOT work in the shared main tree `/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run tests after.
3. This ticket `depends_on: PROVIDER-PROBE-FIX` (real-dep: shared writer of config.py's
   `validate_provider_key` region and providers.py's base_url handling). Confirm that ticket
   is merged before starting; if not, this ticket is not yet claimable.
4. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "PROVIDER-URL-HELPER"`, `status: "in-progress"`); heartbeat via `update`.

## FILES OWNED (touch only these)
- `src/charon/providers.py`
- `src/charon/config.py`
- `src/charon/discover.py`
- `tests/test_providers.py`

`src/charon/cli.py` is READ-ONLY reference context (it has its own endpoint-derivation call
site per the original fragility finding) — it is NOT in owns. If you find this refactor
genuinely requires editing `cli.py`, STOP and flag it rather than touching a file outside
scope; it belongs to another ticket.

## THE TASK (what's broken)
Provider endpoint URL/path construction — "take a stored `base_url`, strip trailing
slashes, append an endpoint suffix" — is independently reimplemented in at least three
places:
- `providers.py` (~line 248): `base.rstrip("/") + "/models"` — used by whatever caller
  resolves a preset's models endpoint.
- `config.py`'s `validate_provider_key` (~lines 467, 472, 491):
  `raw_base = base_url.rstrip("/") if base_url else ""`, then
  `raw_base + "/models"` and `raw_base + "/chat/completions"` — plus its OWN inline copy of
  the SSRF/link-local/metadata-host guard (config.py:455-460), separate from any guard
  `providers.py`/`discover.py` might apply.
- `discover.py` — re-derives a models/chat endpoint from a stored `base_url` independently
  again (read the file; find its exact call site(s) before changing anything).

Each site re-implements the same "strip trailing slash, string-concat a suffix" logic with
its own subtly different edge-case handling (e.g. does it handle a base that already ends in
a path segment like `https://opencode.ai/zen/v1`? does it validate the scheme/host at all?).
A fix to one copy (like PROVIDER-PROBE-FIX's fix to the SSRF-adjacent probe logic) doesn't
propagate to the others — this duplication is exactly what let the provider-probe bug
(fragility finding #4) go unnoticed as long as it did.

## REQUIRED CHANGE
Add ONE stdlib-only helper — put it in `providers.py` since that's where `ProviderPreset`
already lives (the natural home for "how do I turn a preset's base into a concrete URL").
Shape (adjust names to fit the existing module's conventions, but keep the two-function
split):
```python
def validate_base_url(base_url: str) -> str:
    """Validate scheme (http/https) and refuse link-local/metadata hosts. Returns the
    base with trailing slashes stripped. Raises ValueError on an invalid base."""
    ...

def join_endpoint(base_url: str, path: str) -> str:
    """Join `path` onto `base_url` with exactly one `/` between them, no double slashes,
    no dropped path segments for a base that already has a path (e.g. .../zen/v1)."""
    ...

def models_url(base_url: str) -> str: ...
def chat_url(base_url: str) -> str: ...
```
The validation logic should be LIFTED from `config.py`'s existing guard (config.py:455-460:
scheme check + `169.254.` / `metadata.google.internal` refusal) — move it here, don't fork a
second copy. `config.py`'s `validate_provider_key` should then CALL this helper instead of
its own inline `rstrip`/concat, and `discover.py` should do the same for whatever endpoint(s)
it derives.

**No behavior change to any provider's actual resolved URL.** This is a dedup refactor, not a
routing change — every existing provider preset (`opencode`, `openrouter`, `nanogpt`,
`deepseek`, etc., see `providers.py`'s `PRESETS` dict) must resolve to the EXACT SAME
`/models` and `/chat/completions` URL after this change as before, including the ones with a
non-trivial base path like `https://opencode.ai/zen/v1` or `https://opencode.ai/zen/go/v1`.

## ACCEPTANCE CRITERIA
- `PYTHONPATH=src python3 -m pytest tests/test_providers.py tests/test_config.py tests/test_discover.py -q` green.
- **No-behavior-change test (required):** for every entry in `providers.py`'s `PRESETS`
  dict, assert `models_url(preset.base_url)` and `chat_url(preset.base_url)` match the URL
  each site would have produced BEFORE the refactor (hardcode the expected strings for a
  representative sample including at least one nested-path base like the `opencode` presets —
  this is the regression guard that catches an accidental behavior change).
- A test that a link-local/metadata base (`http://169.254.169.254/...`,
  `http://metadata.google.internal/...`) is rejected by `validate_base_url` — proving the
  SSRF guard survived the move intact.
- `config.py`'s `validate_provider_key` and `discover.py`'s endpoint derivation no longer
  contain their own inline `rstrip("/")`+concat — grep-verifiable (`grep -n 'rstrip' src/charon/config.py src/charon/discover.py` should show materially less than before, ideally none for URL construction specifically).

## MERGE GATE (not pytest-alone)
FULL CI from the worktree, ALL green before this is merge-eligible:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`
Standard review — the reviewer's main job is diffing every provider preset's resolved
`models_url`/`chat_url` before vs. after to confirm zero behavior change, and confirming the
SSRF guard logic was MOVED, not duplicated (config.py should no longer have its own copy).

## Dependencies & sequence
- **depends_on:** PROVIDER-PROBE-FIX (real-dep: shared writer of config.py/providers.py).
  Wave 2 relative to that ticket — the fleet auto-claims this once PROVIDER-PROBE-FIX
  merges+done.sh. Rebase onto that merge; do not run as a concurrent second writer of
  config.py/providers.py.

## REPORT BACK (short — no diffs)
Files changed, test names, gate pass/fail, and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "refactor(providers): dedup provider URL/path construction into a shared helper"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.
