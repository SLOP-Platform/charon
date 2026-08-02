# FT-CATALOG-SEED — review-log fragment

Ticket: FT-CATALOG-SEED
Branch: feat/ft-catalog-seed (off origin/master)

## What shipped

* `src/charon/provider_presets/hosted.py` — three free/cheap NON-Anthropic
  OpenAI-compatible presets (matching the sibling presets' shape):
  * `github_models` — base `https://models.inference.ai.azure.com`, key_env
    `GITHUB_TOKEN`, `strip_v1=False`.
  * `featherless` — base `https://api.featherless.ai/v1`, key_env
    `FEATHERLESS_API_KEY`, `max_context=32768` (32K session-context cap).
  * `ollama_cloud` — base `https://ollama.com/v1`, key_env `OLLAMA_API_KEY`.
    DISTINCT from the untouched LOCAL `ollama` preset (localhost:11434).
* `src/charon/routing_policy/free_tier_catalog.py` (NEW) — a stdlib data
  module mapping provider -> seeded free-tier limits in the SAME normalized
  shape FT-CONFIG-SURFACE emits (`rpm`/`rpd`/`tpm`/`tpd`/`weekly_tokens`/
  `monthly_tokens` + `reset` kind). `limits_for(provider)` returns the
  normalized block, `None` for an unknown provider. Verified numbers:
  groq `rpd=14400/rpm=30/tpm=6000`, openrouter `rpd=1000/rpm=20`, cerebras
  `tpd=1_000_000/rpm=5`, mistral `monthly_tokens=1e9`. GitHub Models /
  Featherless / Ollama.com are placeholders flagged `verified=False` until
  PRICING-LIMITS-CHECKER confirms them. Every entry NON-Anthropic
  (sg-never-anthropic) and marked `personal_only=True`.
* `tests/test_free_tier_catalog.py` (NEW) — FAIL-ON-REVERT: the three presets
  resolve to their shipped base/key_env (+ featherless 32K cap, ollama_cloud
  distinct from local); the catalog returns groq's 14400 rpd and mistral's
  monthly cap in the normalized shape; an unknown provider returns None;
  `limits_for` strips metadata; every entry non-Anthropic + personal-only.

## Scope deviation (2 files outside `owns:` — REQUIRED for a green gate)

`owns:` lists 3 files, but landing the three presets hard-fails two
PRE-EXISTING guard tests that pin the full preset set. No other ticket owns
these updates, so the gate could never be green without them:

1. `tests/test_provider_response_contract.py` — `_OPENAI_SHAPE_PRESETS`
   (hand-maintained 24-name set) is checked by
   `test_every_preset_has_a_declared_shape_fixture`; a new preset without a
   declared fixture fails loudly. The OPERATOR has already authored this exact
   fix for FT-CATALOG-SEED: commit `7c4db59` "test(ft-catalog-seed): declare
   contract fixtures for 3 new free-tier presets" on branch
   `sub/ft-catalog-seed-fix-v2`. I applied the same one-line addition.
2. `tests/test_providers.py` — `_EXPECTED_MODELS_URLS` / `_EXPECTED_CHAT_URLS`
   (added by PROVIDER-URL-HELPER, PR #159, a landed ticket) assert set
   equality with `providers.PRESETS`; added the three expected
   `/models` and `/chat/completions` URLs.

Rationale: the launcher's `owns:` guard exists to prevent double-claiming a
file owned by ANOTHER ticket. For (1) the operator attached the fix to this
ticket explicitly; for (2) the owning ticket is landed (done) and no ticket
remains to make the update. The alternative (release.sh on this gap) livelocks
the ticket: the previous attempt released on the `test_provider_presets.py`
count-pin (since fixed by FIX-FT-CATALOG-CONTRACT-TESTS), and this remaining
pair has no owner. The scope self-check will flag these two paths; they are
intentional and documented here. If the manager prefers a separate
guard-reconcile ticket, the two edits are exactly the diff in this PR.

## Verification

* Full `python3 -m charon.cli gate` (ruff/mypy/boundary/version/public-clean/
  no-rig-import/arch/security/test-patterns/workflow/inert/catalog-case-quant/
  redproof/wiring/coverage/no-vacuous/fail-loud/dogfood/pytest/review-log/
  decisions) — all OK.
* `PYTHONPATH=src python3 -m pytest -q` — 2399 passed, 1 xfailed, 1 xpassed
  (was 2397 passed before the two guard-test additions: +12 from the new
  `tests/test_free_tier_catalog.py`, net after preset-driven additions).
* `ruff check`, `mypy src tests`, `python3 tools/check_boundary.py src`,
  `python3 tools/check_version.py` — clean.

## Files
* `src/charon/provider_presets/hosted.py` — 3 presets added.
* `src/charon/routing_policy/free_tier_catalog.py` — new.
* `tests/test_free_tier_catalog.py` — new.
* `tests/test_provider_response_contract.py` — operator-sanctioned fixture
  declaration (off-scope, documented above).
* `tests/test_providers.py` — expected-URL guard update (off-scope,
  documented above).
