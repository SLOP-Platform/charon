# Fix-wave build plan — 4 operator-approved fixes → collision-free droid waves

**Author:** planning sub-session for the Charon fleet MANAGER · 2026-07-09 · READ-ONLY (no code/tickets/commits).
**Sources:** `scratch/provider-cost-rationalization.md`, `scratch/test-gap-audit.md`, `fleet/ADR-UNIVERSAL-RESPONSE-ADAPTER.md`.
**Rig mechanics verified:** `fleet/fleet-droid.sh` (tier-pool self-feeding tab), `fleet/claim.sh` (claims `*.md` only — `.md.parked` is NOT claimable; honours `tier` rank + `depends_on` via `state/done/`), `fleet/done.sh` (manager marks done AFTER a MERGED PR → unblocks dependents), `fleet/validate_board.sh` (HARD-RED on two LIVE tickets sharing an `owns` file with no dep ordering; a `depends_on` edge makes it a legal hand-off), `fleet/wci-contention.sh` (god-file detector, threshold 4).

Tiers: canonical `frontier|strong|economy` → `opus|sonnet|haiku` (fleet-droid resolves via `charon tier resolve`, falls back opus/sonnet/haiku).

---

## WCI pass (WCI-METHOD.md)

**Step 1 — DEDUP.** Three existing board tickets overlap this batch and MUST be reconciled first (manager pre-steps below):
- `CLINE-UNWRAP-SHIM.md.parked` — **SUPERSEDED** by Fix 4 (the ADR says so explicitly). Mark superseded / remove; do not activate.
- `DTC-8-TEST-PATTERNS.md` (LIVE) — owns `tools/check_test_patterns.py` + `tests/test_check_test_patterns.py`; **both files already exist on disk**. Fix 3 extends the same lint file → owns-collision. Reconcile (see pre-steps).
- `TEST-EXERCISES-CHANGE-GUARD.md.parked` — same *theme* (fail-on-revert) but owns git hooks + `.github/workflows/ci.yml` only → **no file collision** with Fix 3; leave parked.

**Step 2/3 — CONTENTION AXIS / god-file.** `fleet/wci-contention.sh 4` over this batch → **no DECOMPOSE CANDIDATE** (no file owned by ≥4 tickets; no god-file split needed). The only shared file is `src/charon/forwarder.py`, owned by **Fix 1 AND Fix 4** (2 owners) → resolve by **serialising into different waves** with a `depends_on` hand-off (legal per validate_board.sh). All other owns are disjoint.

**Step 4/5 — RE-SLICE → WAVES, SEQUENCE.** Bleed-stoppers (Fix 1 billing, Fix 2 false-downgrade) first + independent test-harden (Fix 3) in a parallel Wave 1; durable adapter (Fix 4, lower urgency, shares forwarder.py) in Wave 2.

---

## TICKET 1 — `BILLING-EST-COST-FIX`  (Fix 1, priority 1, money-path)

- **tier:** `frontier`  · **work_class:** `money-path` · **branch:** `fix/billing-est-cost`
- **depends_on:** *(empty)*
- **owns:** `src/charon/forwarder.py`, `tests/test_forwarder_billing.py` *(new)*
- **scope:** Stop fabricating spend. At `forwarder.py:315` and `:400`, `srv.spend_limiter.record(cost if cost > 0 else est_cost)` records the phantom `est_cost` floor (`_pre_flight_estimate`, defined :141; `(request_bytes/4)·$1.5e-6`) whenever real cost is 0 — which is ALWAYS for free/flat providers reporting `cost==0` → the fictional $223 in spend.json. Fix: only substitute `est_cost` when cost is genuinely **unpriced/unknown**, NEVER when the provider reported a real $0 or the model is free/flat. Distinguish `cost_source in {"free","provider(0)"}` (record 0) from `unpriced`. Apply to BOTH the non-stream (:315) and stream (:400) record sites. **Bonus latent bug (same file, fold in):** `forwarder.py:296-300` feeds the WHOLE decoded JSON body to `response_normalizer.normalize(...)`, but the normalizer is specified to operate on `choices[0].message.content` only — STANDARDIZE_MD runs regex over the entire envelope. Fix so the post-hook only touches message content.
- **accept (per-ticket):** `PYTHONPATH=src python3 -m pytest tests/test_forwarder_billing.py -q`
- **FAIL-ON-REVERT test:** `test_flat_provider_zero_cost_not_billed_est_floor` — drive `forward_with_failover` (non-stream AND stream paths) against a stub upstream that reports `cost_usd==0` on a free/flat route; assert `spend_limiter.record` was called with **0.0**, not the est_cost floor. RED today (records the floor); GREEN only with the fix; RED again on revert. Second assertion `test_response_normalizer_receives_content_not_whole_body`: post-hook is handed `choices[0].message.content`, not the JSON envelope.
- **model:** strongest coder — **opus** (frontier). Money-path metering; do not economize.
- **review:** ADVERSARIAL (money-path, touches spend recording) before merge.
- **runtime follow-up (MANAGER/operator, NOT the droid — post-merge+deploy):** reset `/data/spend.json` `spent_usd` 223.28 → 0 on the live box (`10.0.1.60`). Note in ticket as an out-of-band step; not part of the PR.

## TICKET 2 — `NORMALIZE-CASE-QUANT-FIX`  (Fix 2, priority 2, money-path)

- **tier:** `frontier` · **work_class:** `money-path` · **branch:** `fix/normalize-case-quant`
- **depends_on:** *(empty)*
- **owns:** `src/charon/proxy.py`, `tests/test_normalize_model_id.py` *(new — deliberately NOT `tests/test_proxy_downgrade.py`, which SR-1 owns; avoids test-file collision)*, `tools/check_catalog_case_quant.py` *(new detector, relates #30)*
- **scope:** `_normalize_model_id` (`proxy.py:247`, currently `model_id.rsplit("/",1)[-1]`) is case-sensitive and keeps quant suffixes, so a provider that echoes `Kimi-K2.7-Code` (vs pool `kimi-k2.7-code`) or `GLM-5.2-FP8` (vs `glm-5.2`) is false-flagged `pseudo_success` → recorded as a quality FAILURE (`forwarder.py:312`) and served with a spurious `X-Charon-Downgrade` (this is why NeuralWatt scores 0/4 while actually working). Make normalization **case-insensitive** and **quant-suffix aware** (strip `-FP8`, `-FP16`, `-BF16`, `-Q4…`, `-INT8`, etc.) on BOTH the expected and returned id before comparison — without breaking the SR-1 namespaced-id fix (still compare final path segment). Add a small **detector** (`tools/check_catalog_case_quant.py`, wired into `gates.json`/`charon.cli gate`) that flags catalog/live model-id case+quant mismatches — mechanizes the #30 catalog-mismatch directive.
- **accept (per-ticket):** `PYTHONPATH=src python3 -m pytest tests/test_normalize_model_id.py -q`
- **FAIL-ON-REVERT test:** `test_quant_case_variant_is_not_downgrade` — feed `classify()` expected `kimi-k2.7-code` / `glm-5.2` against returned `Kimi-K2.7-Code` / `GLM-5.2-FP8`; assert `obs.pseudo_success is False` (a clean success, no `X-Charon-Downgrade`). RED today (case/quant mismatch → pseudo_success True); GREEN with fix; RED on revert.
- **model:** **opus** (frontier). Money-path classify/scoring correctness.
- **review:** ADVERSARIAL (touches the classify/downgrade money path).

## TICKET 3 — `TEST-HARDEN-CONTRACT`  (Fix 3, priority 3, test hardening)

- **tier:** `strong` *(one tier down — test work)* · **work_class:** `tests` · **branch:** `feat/test-harden-contract`
- **depends_on:** *(empty — cline-pass is xfail'd, so NO dependency on Fix 4; see dependency resolution below)*
- **owns:** `tests/conftest.py`, `tests/test_provider_response_contract.py` *(new)*, `tools/check_test_patterns.py`, `tests/test_check_test_patterns.py`
- **scope:** Kill the self-fulfilling-mock blind spot (`conftest.py:54-60` + ~14 inline handlers all return canonical OpenAI shape, so foreign-envelope bugs are invisible — this is why the cline defect passed green). Add:
  1. **Parametrized provider-contract test** (`test_provider_response_contract.py`) over every `ProviderPreset` in `providers.py`: for each preset, drive a non-stream completion through the proxy against a mock returning THAT preset's known raw shape, and assert the CLIENT response has a **top-level `choices` list AND a top-level `usage` dict**. A new preset with no declared shape fixture fails the parametrization loudly.
  2. **`check_test_patterns.py` lint extension** (self-mirroring-mock rule): flag any proxy/forwarder test whose upstream mock body is authored inline AND whose assertions only read *inside* `choices` — nudges toward the contract fixture. Extend `tests/test_check_test_patterns.py` to cover the new rule.
  3. Update `conftest.py` only as needed to support the contract fixture (still the sole ticket touching conftest.py).
- **accept (per-ticket):** `PYTHONPATH=src python3 -m pytest tests/test_provider_response_contract.py tests/test_check_test_patterns.py -q`
- **FAIL-ON-REVERT test:** the self-mirroring-mock lint itself — `test_check_test_patterns_flags_self_mirroring_mock` asserts the new rule fires on a fixture that mocks canonical output AND only asserts inside `choices`. RED without the rule, GREEN with it, RED on revert. (The contract test is the durable class-killer; the lint test is the crisp revert-guard.)
- **model:** **sonnet** (strong). Mechanical test/lint work, clear spec.
- **review:** standard (not money-path code; it's the test harness).

## TICKET 4 — `RESPONSE-ADAPTER-UNIVERSAL`  (Fix 4, priority 4, money-path, LOWER urgency)

- **tier:** `frontier` · **work_class:** `bugfix` (money-path) · **branch:** `feat/response-adapter-universal`
- **depends_on:** `BILLING-EST-COST-FIX`  *(REAL shared-file prereq: Fix 4 plugs into the same `forward_with_failover` non-stream 200 path Fix 1 edits — must rebase onto Fix 1's forwarder.py, never a concurrent second writer. This edge is what makes the shared `forwarder.py` ownership legal under validate_board.sh.)*
- **owns:** `src/charon/response_adapters.py` *(new)*, `src/charon/providers.py`, `src/charon/gateway.py`, `src/charon/proxy_server.py`, `src/charon/forwarder.py`, `tests/test_response_adapters.py` *(new)*, `tests/test_proxy_server.py`
- **scope:** Implement `fleet/ADR-UNIVERSAL-RESPONSE-ADAPTER.md` (T1–T5; T6 streaming DEFERRED). New `response_adapters.py`: `ResponseAdapter` Protocol, `IdentityAdapter`+`IDENTITY` singleton (default for every provider), `ClineAdapter` (unwrap `{"data":{…choices…},"success":true}` → inner OpenAI object; idempotent+total), `_ADAPTERS` registry + `get_adapter`. Plumb an `adapter` key mirroring `wire`: field on `ProviderPreset` (providers.py) → resolve in `_route_from_spec` (gateway.py) → field on `UpstreamRoute` (proxy_server.py) → resolved once per attempt in the forwarder. Plug into `forward_with_failover` on the **non-streaming 200 path** (between `_drain` and `_extract`, ~line 271) behind an `if route.adapter:` guard so the IDENTITY path stays byte-identical; also the non-200 error unwrap (guarded). Add `cline-pass` preset with `adapter="cline"`, `strip_v1`, no-`/models` note. Restores real `usage` metering for cline non-stream (the silent-undercount half).
- **accept (per-ticket):** `PYTHONPATH=src python3 -m pytest tests/test_proxy_server.py tests/test_response_adapters.py -q`
- **FAIL-ON-REVERT test:** `test_proxy_nonstream_cline_shaped_upstream_returns_openai_body` (integration) — stub upstream returns a wrapped `{"data":{…choices,usage…},"success":true}` body on a route with `adapter="cline"`; drive one non-stream request; assert the CLIENT body has top-level `choices` (content matches inner) AND that `usage`/cost was recorded non-zero via the observer/spend path. Reverting the shim → served body lacks `choices` → RED. Plus `test_identity_provider_body_byte_identical` (default path unchanged) and the config-flow test (`provider: cline-pass` → `UpstreamRoute.adapter=="cline"`).
- **model:** **opus** (frontier). Money-path failover/metering with subtle side-effects — ADR §10 mandates strongest coder.
- **review:** ADVERSARIAL (money-path + touches the classify/usage/spend path Fix 1 just changed).

---

## Dependency resolution — Fix 3 contract test vs Fix 4 adapter (the required decision)

Fix 3's provider-contract test asserts every preset yields top-level `choices`+`usage` through the proxy. For `cline-pass` that only holds once Fix 4's adapter lands. **Chosen sequencing: Fix 3 does NOT depend on Fix 4.** The contract test marks `cline-pass` with `@pytest.mark.xfail(reason="cline non-stream envelope unwrapped by RESPONSE-ADAPTER-UNIVERSAL", strict=False)`. Rationale:
- Fix 4 is demoted to LOWER urgency; blocking the test-hardening (Fix 3) behind it would strand the class-killer.
- `strict=False` means that once Fix 4 lands the cline case simply xpasses — **no cross-ticket file edit required**, so Fix 4 never has to touch `test_provider_response_contract.py` (which Fix 3 owns). Clean decoupling: neither ticket edits the other's files.
- Fix 4 ships its OWN cline coverage in `tests/test_response_adapters.py` + `tests/test_proxy_server.py` (files Fix 4 owns). A later trivial cleanup can drop the xfail.

This keeps Fix 3 in Wave 1 (parallel) instead of pushing it to Wave 3.

---

## WAVES

**Wave 1 (parallel, owns-disjoint — verified no shared file):**
| Ticket | tier | owns (disjoint) |
|---|---|---|
| `BILLING-EST-COST-FIX` | frontier | forwarder.py, test_forwarder_billing.py |
| `NORMALIZE-CASE-QUANT-FIX` | frontier | proxy.py, test_normalize_model_id.py, check_catalog_case_quant.py |
| `TEST-HARDEN-CONTRACT` | strong | conftest.py, test_provider_response_contract.py, check_test_patterns.py, test_check_test_patterns.py |

No file appears in two Wave-1 tickets → `validate_board.sh` clean; max concurrency = 3.

**Wave 2 (after Fix 1 is MERGED + `done.sh`'d):**
| Ticket | tier | owns |
|---|---|---|
| `RESPONSE-ADAPTER-UNIVERSAL` | frontier | response_adapters.py, providers.py, gateway.py, proxy_server.py, **forwarder.py**, test_response_adapters.py, test_proxy_server.py |

Wave 2 is gated purely by the `depends_on: BILLING-EST-COST-FIX` edge — `claim.sh` will not release Fix 4 until Fix 1 sits in `state/done/` (which `done.sh` only writes after a MERGED PR). So Fix 4 can be left LIVE and the frontier pool auto-claims it the instant Fix 1 lands; no manual un-park needed. (Conservative alternative: keep Fix 4 `.md.parked` and un-park after Fix 1's adversarial review + merge — use this if you want an explicit human gate between the two forwarder.py writers.)

**Merge gate (every ticket):** FULL CI — `ruff` + `mypy` + `PYTHONPATH=src python3 -m charon.cli gate` — NOT pytest alone. Money-path tickets (1, 2, 4) → adversarial review before merge. Builds happen in worktrees off master (fleet-droid handles this).

---

## MANAGER pre-steps (run these FIRST; this plan does NOT run them)

1. **Reconcile overlaps (DEDUP):**
   - Mark `board/CLINE-UNWRAP-SHIM.md.parked` **SUPERSEDED** by `RESPONSE-ADAPTER-UNIVERSAL` (ADR states this) — move to `board/archive/` or annotate; do not activate.
   - Reconcile `board/DTC-8-TEST-PATTERNS.md`: `tools/check_test_patterns.py` + `tests/test_check_test_patterns.py` already exist on disk. If DTC-8 has landed, mark it done/close it so `TEST-HARDEN-CONTRACT` is the sole live owner of those two files (else `validate_board.sh` RED: owns-collision LIVE). If DTC-8 is genuinely un-built, fold its scope into Fix 3 instead of running both.
   - Leave `TEST-EXERCISES-CHANGE-GUARD.md.parked` as-is (different owns; no collision).
2. **Write 4 prompt files** under `/home/stack/charon-private/prompts/`: `billing-est-cost.md`, `normalize-case-quant.md`, `test-harden-contract.md`, `response-adapter-universal.md`. Each brief ends with an explicit **LAST STEP (required): `git add -A && git commit`, then report the commit SHA** — and on its **own separate line**: *do NOT push, do NOT open a PR, do NOT merge* (the launcher publishes; deny-list blocks push inside the session).
3. **Create 4 board tickets** with the fields above (`tier`, `work_class`, `branch`, `depends_on`, `owns`, `accept`, `prompt`, `scope`, `note`). Create Wave-1 three as active `.md`; create Fix 4 as active `.md` with `depends_on: BILLING-EST-COST-FIX` (or `.md.parked` for the conservative gate).
4. **Validate:** `cd /home/stack/charon-private && fleet/validate_board.sh` (expect clean: forwarder.py hand-off justified by the depends_on edge) and `fleet/wci-contention.sh 4` (expect no DECOMPOSE CANDIDATE).
5. Add `real-dep:` line to Fix 4 explaining the forwarder.py hand-off (validate_board.sh requires a `real-dep:`/`depends_on` justification for a disjoint-owns/shared-owns dep).

---

## EXACT operator tab commands

fleet-droid is a **self-feeding tier pool** (one tab claims any at-or-below-tier ticket, rides through dependency gaps). Per-ticket "command" = the tier tab that will claim it. Open Wave-1 concurrency = **2 frontier tabs + 1 strong tab**:

```
# Tab A — frontier pool (claims BILLING-EST-COST-FIX, then RESPONSE-ADAPTER-UNIVERSAL after Fix 1 lands)
cd /home/stack/charon-private && fleet/fleet-droid.sh frontier --wait 3 --retries 10

# Tab B — second frontier pool (claims NORMALIZE-CASE-QUANT-FIX in parallel with Tab A)
cd /home/stack/charon-private && fleet/fleet-droid.sh frontier --wait 3 --retries 10

# Tab C — strong pool (claims TEST-HARDEN-CONTRACT)
cd /home/stack/charon-private && fleet/fleet-droid.sh strong --wait 3 --retries 10
```

Per-ticket mapping:
- `BILLING-EST-COST-FIX` → **frontier** tab (A or B). `fleet/fleet-droid.sh frontier --wait 3 --retries 10`
- `NORMALIZE-CASE-QUANT-FIX` → **frontier** tab (the other of A/B). `fleet/fleet-droid.sh frontier --wait 3 --retries 10`
- `TEST-HARDEN-CONTRACT` → **strong** tab (C). `fleet/fleet-droid.sh strong --wait 3 --retries 10`
- `RESPONSE-ADAPTER-UNIVERSAL` → **frontier** tab — auto-claimed by a freed Tab A/B once `BILLING-EST-COST-FIX` is merged + `done.sh`'d (the `--wait 3 --retries 10` self-feed rides the gap). No extra tab needed; keep one frontier tab alive through Wave 1→2.

Manager marks each merged ticket done: `cd /home/stack/charon-private && fleet/done.sh <TICKET-ID>` (requires a MERGED PR).
