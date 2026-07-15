---
description: "RESOLVED on origin/master — silent-downgrade double-bill fixed by _normalize_model_id rsplit(final-segment) + SR-1 regression tests (tests/test_proxy_downgrade.py). Historical detail of the leak retained below."
metadata: 
name: charon-silent-downgrade-leak
node_type: memory
originSessionId: a8f924d0-22f6-4f2b-ac52-79591b72effd
type: project
tags: [charon, debugging]
last_referenced: 2026-07-13
---
CONFIRMED 2026-07-03 via live `/charon/status` on the operator's gateway (<COORDINATOR_HOST>): `recent_failovers` = 50/50 entries are billed-and-discarded 200s. This is the cause of the "opencode session balance burning fast" symptom.

ROOT CAUSE: the silent-downgrade failover discards an already-billed upstream 200 and refetches from the next provider. `_normalize_model_id` (`src/charon/proxy.py:174-184`) strips only the FIRST `/` segment, so a provider that echoes a fully-qualified id (opencode-zen returns `accounts/fireworks/models/deepseek-v4-pro` for a request of `deepseek-v4-pro`) normalizes to `fireworks/models/deepseek-v4-pro` ≠ `deepseek-v4-pro` → `classify()` sets `pseudo_success` (`proxy.py:243-252`) → failover loop discards it with `count_usage=False` and continues (`proxy_server.py:756-760` non-stream, `:814-817` stream). Every such request bills opencode-zen (discarded) + opencode-go (served) = 2×.

INVISIBLE because: discarded calls use `count_usage=False`, AND these models have no pricing → `cost_usd: 0.0`. So Charon's own status under-reports while providers bill everything. The universal SpendLimiter (`spend_limits.py`, one global cumulative cap across all providers — good) canNOT catch this: it only records `cost > 0`, and discarded calls never reach `record()`.

FIX (known, ~2 lines): compare the FINAL path segment — `return model_id.rsplit("/", 1)[-1]` — kills the observed 100% false-positive while genuine downgrades still differ. Stronger: serve the downgrade with the existing `X-Charon-Downgrade` header (`proxy_server.py:778/820`) instead of discard-and-rebill. Add a regression test: a namespaced 200 must be SERVED, not failed over. NOTE the naive version-suffix case (`gpt-4o` vs `gpt-4o-2024-11-20`) needs care — plain `startswith` is too loose (`gpt-4` vs `gpt-4o`).

RESOLVED 2026-07-05 (verified on `origin/master`): `_normalize_model_id` (`src/charon/proxy.py:197-209`) now returns `model_id.rsplit("/", 1)[-1]` (FINAL segment), and the pseudo-success check (`proxy.py:278`) compares normalized returned vs expected — so a namespaced 200 (`accounts/fireworks/models/deepseek-v4-pro` vs bare `deepseek-v4-pro`) no longer false-flags as a downgrade and is NOT discarded-and-rebilled. Docstring cites SR-1 + the double-bill root cause. Regression tests live in `tests/test_proxy_downgrade.py` (SR-1: fully-qualified/bare/single-prefix returns are NOT pseudo-success; a genuine family difference still flags). Build-rig red `silent-downgrade-double-bill` CLOSED in `fleet/reds.tsv` (2026-07-05:auto-verified). Line:col citations for the OLD buggy code below (`proxy.py:174-184`, `:243-252`) are pre-fix and no longer accurate.

Smart Routing (see [[SMART-ROUTING.md]] grounding doc) does NOT touch this — the discard lived in the core failover loop below all modules. Relates to [[charon-project-state]], [[charon-production-readiness-mindset]]. STATUS 2026-07-03: FIXED + tested — SR-1 on `feat/prod-install` (branch `fix/SR-1-namespaced-model-id`, 827 pass) and backport `hotfix/v0.2.1` off `v0.2.0` (168 pass, commit 0b99a8f). Tickets SR-1..SR-10 written to the fleet board.

TWO DECISIONS from this incident, to be registered in `docs/DECISIONS.md` (the product's binding register) via the implementing tickets — NOT hand-edited:
- **DEPLOY = image-only / single-producer (Owner: OP, Settled):** deploy `docker-compose.yml` has EXACTLY ONE producer — never both `build:` and `image:`; semver tags never `:latest`; CI is sole builder; images SHA-stamped. SR-10 mechanizes (its accept check fails if a service declares both). Driven by the fact that prod ran an unknown/older build (`v0.2.0`) than anyone realized — the opacity that hid this leak.
- **FAILOVER-BILLING (Owner: OP+AI, Settled):** the gateway never discards-and-rebills an already-billed 200; model-id equality is namespace/segment-tolerant (compare final `/`-segment), and a genuine downgrade is served-with-`X-Charon-Downgrade`, not re-billed. Principle is firm (OP); the matching heuristic (e.g. version-suffix handling) is AI-revisable. SR-2 writes the REVIEW-LOG entry + registers the row.

Operator's gateway token was pasted in-session on 2026-07-03 → rotate on redeploy.
