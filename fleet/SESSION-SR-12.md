# DeepSeek build session — SR-12 opencode-zen preset (VERIFY + CLOSE, add regression test)

You are a Charon build session (DeepSeek V4 Pro). Repo: `/home/stack/code/charon`. Branch off `master`.
SR-12 asked to "re-add the `opencode-zen` built-in provider preset dropped from source." **A pre-check has
already confirmed the preset is PRESENT and CORRECT in `src/charon/providers.py`.** So this is a
**VERIFY + CLOSE** task, not a new build: confirm the preset, add the missing regression test that locks it
in, and report that the ticket is already satisfied.

**This session runs in PARALLEL with the RFL-1 and TOOL-REPAIR sessions — that is SAFE:** those two build
NEW standalone modules; this one touches only `providers.py` + its test. No shared files.

## 1. Ground yourself first
- `/home/stack/code/charon/AGENTS.md` — standing orders (mandatory).
- `src/charon/providers.py` — the `PRESETS` dict and `resolve()`. This is the ONLY source file in scope.
- `tests/test_providers.py` — where the regression test goes; follow its existing style (see
  `test_hosted_presets_present`, `test_huggingface_neuralwatt_presets_present`).

## 2. VERIFY — confirm the current state (this is the first task, not a formality)
Open `src/charon/providers.py` and confirm ALL of the following are already true. (They are, per pre-check —
your job is to independently re-verify, not to re-add anything.)
- `PRESETS["opencode-zen"]` exists with `base_url == "https://opencode.ai/zen/v1"` and
  `key_env == "OPENCODE_ZEN_KEY"`.
- `PRESETS["opencode-go"]` exists with `base_url == "https://opencode.ai/zen/go/v1"` and the same
  `key_env == "OPENCODE_ZEN_KEY"`.
- The optional `neuralwatt` preset the ticket mentions ALSO already exists
  (`https://api.neuralwatt.com/v1`, `NEURALWATT_API_KEY`) — so there is nothing to add there either.

If — and ONLY if — any of the above is actually WRONG or MISSING, make the minimal preset fix to match the
values above (mechanical `PRESETS` entry, no logic). Otherwise **change no source** — the presets are
correct as-is.

## 3. DO — add the missing regression test (this is the real deliverable)
There is currently **no explicit test asserting the `opencode-zen` / `opencode-go` presets** (the suite only
covers other providers generically), so the exact bug SR-12 was filed for — the source silently dropping
`opencode-zen` — could regress unnoticed. Add a focused regression test to `tests/test_providers.py`:
- `test_opencode_zen_go_presets_present` (name to taste): assert `providers.resolve("opencode-zen")` yields
  `base_url == "https://opencode.ai/zen/v1"` and `key_env == "OPENCODE_ZEN_KEY"`, and
  `providers.resolve("opencode-go")` yields `base_url == "https://opencode.ai/zen/go/v1"` and the SAME
  `key_env == "OPENCODE_ZEN_KEY"`. Mirror the assertion style of `test_huggingface_neuralwatt_presets_present`.

## 4. Scope — non-negotiable
- branch: `feat/sr-12-opencode-zen-preset` (off latest `master`).
- **owns:** `src/charon/providers.py` (only if a fix is genuinely needed — expected: NO change),
  `tests/test_providers.py` (add the regression test). Touch nothing else. If you think you need any other
  file, **STOP and flag it**.
- Product-clean: no fleet/SLOP/runner/`/home/stack`/personal strings in `src/`. Stdlib-only (this module is
  already stdlib `urllib`/`json`).

## 5. Rules — non-negotiable
- **Gate before commit** — BOTH must be green:
  ```
  python3 -m charon.cli gate && PYTHONPATH=src python3 -m pytest -q
  ```
  `python3 -m charon.cli gate` runs ruff/mypy/boundary/version/gate-registry; pytest is the separate test
  pass. Do NOT use a bare `mypy src/charon` — it misses the test files and reddens CI.
- Commit with a conventional message (e.g. `test(SR-12): lock in opencode-zen/opencode-go presets (already satisfied)`).
- **Commit your work but DO NOT push and DO NOT open a PR.** Stop after committing — a Claude reviewer + the
  operator gate every merge.

When committed, report the branch name + final `pytest` counts, AND state plainly in your report:
**"SR-12 was already satisfied in source — the opencode-zen/opencode-go presets were present and correct; I
only added the regression test."** (If you found a genuine discrepancy, describe exactly what you fixed.)

## Dependencies & Sequence
Touches only `providers.py` (verify, likely no change) + a NEW regression test in `tests/test_providers.py`
— **disjoint from `proxy_server.py`** entirely. **Parallel-safe** with SESSION-RFL-1 (new `quota.py`) and
SESSION-TOOL-REPAIR (new `tool_repair.py`) — no shared files, run all three concurrently.
