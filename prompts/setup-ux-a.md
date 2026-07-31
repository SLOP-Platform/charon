Three first-run setup-UX fixes for the `charon setup` wizard, all in ONE function
(`_cmd_setup` in `src/charon/cli.py`) so they ship as ONE PR. Canonical tier: **high**
(fleet `opus`). Dogfood-driven (charon-vm 2026-06-27): a real `charon setup` run added
provider `opencode-zen`, stored the key, imported ALL 49 models into the catalog — but the
"model served by '<provider>'" prompt showed NOTHING, the user hit a blank Enter, and setup
finished "Done. 0 model(s) configured" → a silently non-functional gateway.

READ FIRST (read-only, understand the real functions before touching anything):
- `src/charon/cli.py` → `_cmd_setup` (~L269-360) — the wizard; the inner `ask()` helper;
  the catalog-import offer that calls `_import_models(name)`; the `while True:` "model served
  by '<name>'" loop that calls `config.add_model(...)` and appends to the local
  `added_models` list; the final `print("\nDone. {len(added_models)} model(s) configured…")`.
- `src/charon/cli.py` → `_import_models(name, *, free_only, into_pool, quiet)` → returns
  `(added, skipped)` (the imported ids land in the CATALOG = `models.json`).
- `src/charon/config.py` → `load_models()` returns `{model_id: {"free":…, "cost_rank":…,
  "provider":…}}`; `add_model(...)`; `add_models_bulk(...)`. (READ-ONLY — do NOT edit
  config.py; `load_models()` already gives you everything you need to surface the catalog.)
- `src/charon/providers.py` → `PRESETS` (the preset dict the wizard prints as "Presets: …")
  and `list_models(name, overrides, *, api_key=…)` (the LIVE catalog probe).

KEY INSIGHT (the real bug): `_import_models` writes the imported models into the CATALOG
(`models.json`) via `add_models_bulk`, but the wizard's local `added_models` list (used for
the final count AND for the optional failover pool) is ONLY appended to inside the manual
"model served by '<name>'" loop. So importing 49 models leaves `added_models == 0`: the
import→serve step is DISCONNECTED, the serve prompt shows no list, and the user is told
"0 model(s) configured". Fix the disconnect, don't paper over it.

DELIVERABLE 1 — surface the catalog at the "model served by '<name>'" prompt (TIER-RECS
Phase A core).
- Right before the manual serve loop for a provider, look up that provider's already-imported
  models from the catalog: `config.load_models()` filtered to entries whose `provider == name`
  (these are exactly what `_import_models` just wrote). SHOW them (ids, with a free/paid hint
  if cheap) so the user picks from REAL options instead of typing a model id blind.
- Make the import→serve connection OBVIOUS: when the provider has N imported/catalog models,
  OFFER a fast path BEFORE the blank prompt — e.g. "serve all N imported models? [Y/n]" and/or
  "pick from these" — and feed the chosen ids into `added_models` (so they count and can join
  the failover pool). Selecting "serve all" should add every one of those catalog ids to
  `added_models` without re-prompting per model. The manual "type an id" path stays as the
  fallback for a custom/unlisted id.
- If the provider has NO catalog models yet (import skipped/failed), keep today's manual
  prompt unchanged (no regression). Optional nicety: if a live probe is trivial you MAY fall
  back to `providers.list_models(...)`, but do NOT make a network call mandatory — the catalog
  read (`load_models()`) is the required, offline source of truth here.

DELIVERABLE 2 — 0-models-served warn guard (correctness).
- At the end of the wizard, if NOTHING ended up configured-to-serve (the user's effective
  served set is empty — i.e. `added_models` is empty AND no catalog models were left in a
  serve-able state), do NOT print the cheery "Done. 0 model(s) configured." Instead WARN
  loudly, e.g.: `⚠ 0 models served — your gateway won't respond to requests`.
- Then OFFER to fix it in place: if there ARE imported/catalog models for the providers just
  configured, offer "serve all N now?" (add them to `added_models`); otherwise point the user
  at the manual path. Only fall through to the normal "Done. N model(s) configured" once the
  served set is non-empty OR the user explicitly declines. Keep the existing success message
  for the N>=1 case byte-identical.
- Use stderr for the warning is fine; keep exit code semantics sensible (a wizard the user
  walked through to completion need not exit non-zero, but the warning MUST be visible).

DELIVERABLE 3 — colorize the provider presets list (UX-POLISH colorize-presets nit).
- The `print("Presets:", ", ".join(sorted(providers.PRESETS)))` line does not stand out, so
  users scroll past it. Apply ANSI color/emphasis so the presets line clearly stands out.
- MANDATORY fallback: honour `NO_COLOR` (any value set → no color) AND degrade to plain text
  on a non-TTY / dumb terminal (`sys.stdout.isatty()` is False, or `TERM=dumb`). Put the
  tiny color helper local to cli.py (a small module-level helper or nested function) — keep it
  stdlib-only (`os`, `sys`), no new dependency, no new file.

TESTS (REQUIRED — add a NEW test file `tests/test_setup_ux.py`; you own it):
- Drive `_cmd_setup` (or the smallest seam that exercises this flow) with monkeypatched
  `input`/`getpass` and an isolated config dir (mirror how `tests/test_setup_tiers.py` /
  `tests/test_setup_web.py` set up a temp config — read them for the pattern).
- Assert the 0-models WARNING fires when the user serves nothing (string match on the warn
  text, e.g. "0 models served").
- Assert the serve prompt SURFACES the imported catalog: pre-seed the catalog with a couple of
  models for a provider, run the wizard, and assert those ids are shown / that "serve all"
  adds them to the served set (and that the final count reflects them).
- Assert the presets line is plain (no ANSI escapes) when `NO_COLOR` is set or stdout is not a
  TTY (capture-based: pytest's captured stdout is non-TTY, so the default path should already
  be plain — assert no `\x1b[` leaks there; if you expose the colorizer as a helper, unit-test
  it directly with NO_COLOR set vs a forced-TTY flag).
- Keep ALL existing setup tests passing (backward-compatible behavior for the N>=1 happy path).

CONSTRAINTS:
- Touch ONLY the files in your board `owns:` — `src/charon/cli.py` and
  `tests/test_setup_ux.py`. Do NOT edit `src/charon/config.py` or `src/charon/providers.py`
  (read-only); `config.load_models()` already exposes the catalog. If the work genuinely needs
  another file, STOP and run `release.sh setup-ux-a` with a one-line reason — do NOT widen scope.
- PRODUCT-CLEAN: no SLOP / fleet / build-rig / runner reference may leak into the product.
- Provider/agent-AGNOSTIC: nothing hardcoded to a specific provider (opencode-zen, anthropic,
  …) or agent. Works for any OpenAI-compatible provider in `PRESETS` or a custom one.
- Affects ONLY the setup CONFIG step — NEVER the gateway hot request path.
- Stdlib-only core; no new dependency; no `pip install -e`; no secrets committed.
- Backward-compatible: the existing "Done. N model(s) configured" success path (N>=1) and the
  manual model-entry fallback must be preserved.
- Gate GREEN on EVERY commit: `PYTHONPATH=src python3 -m pytest -q` · `ruff check` ·
  `mypy src tests` · `python3 tools/check_boundary.py src` · `python3 tools/check_version.py`.
  Conventional Commits. Write your review note as `docs/review-log/SETUP-UX-A.md` (your own
  fragment — NEVER append to the shared `docs/REVIEW-LOG.md`).
- Open a DRAFT PR (base master) and STOP — do not mark ready, do not merge; the manager lands it.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
