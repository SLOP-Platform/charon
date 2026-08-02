# PRODUCT-PR-QUEUE — adversarial review of 8 product-adjacent PRs

**Reviewers:** obi-wan-kenobi (deepseek-v4-pro-ds), plo-koon (deepseek-v4-flash-ds, re-verification 2026-08-01)  
**Date:** 2026-08-02  
**Branch:** chore/product-pr-queue (off origin/master)

Sequence: money-path first (#212, #211, #208), then tooling (#215, #210, #209), then docs (#216, #214)

**Re-verification note:** a second reviewer re-ran every measurement and every suite on
origin/master (54e0dc8). Three verdicts are unchanged but the EVIDENCE in the prior note
was factually wrong: (1) ruff ARG is 45 src-only, not 50 (and the ticket's 406 is wrong
too — 385 full-tree); (2) ruff ARG is NOT a strict superset of pylint W0613 (8 pylint-only
locations exist, all false positives); (3) #212 is NOT docs-only — it ships a 323-line
money-path module. All three are corrected below with measured evidence.

---

## PRE-REVIEW: measured facts vs ticket claims

The ticket accept criteria includes three specific assertions that need verification.
**Re-measured at origin/master (54e0dc8) 2026-08-01 by a second reviewer:**

**Claim 1: ruff --select ARG = 406 findings. BOTH ticket AND prior note are wrong.**
```
$ ruff check --select ARG --output-format concise src | grep -c "^src/"      # 45
$ ruff check --select ARG --output-format concise src tests tools | grep -cE "^(src|tests|tools)/"  # 385
```
The ticket's 406 and the prior note's 50 both fail to reproduce. src-only = **45**;
full tree (src+tests+tools) = 385. The "50" in the prior note is unexplained by any
scope combination measured here.

**Claim 2: pylint W0613 = 46. WRONG, and NOT a strict superset relationship.**
```
$ python3 -m pylint --disable=all --enable=W0613 src | grep -c ": W0613"     # 41
$ python3 -m pylint --disable=all --enable=W0613 src tests | grep -c ": W0613" # 186
```
Measured: **41** src findings (not 46). Critically, ruff ARG is **NOT** a strict
superset of pylint W0613: `comm` on the two finding sets shows **8 pylint-only
locations** — `connect.py:347` (a documented `pass`-stub `_write_cline(w)` whose
`w` is genuinely unused) and `proxy_server.py:485-491` (7 backward-compat `__init__`
kwargs `guardrails`/`semantic_cache`/etc. that ARE consumed via the `locals()` merge
loop at proxy_server.py:511-515 — pylint false-positives them because it can't see
`locals()` indirection). ruff correctly flags NONE of those 8. ruff-only findings are
ARG005 (unused lambda args — `cli.py:2208`, `connect.py:406`, `gateway.py:70-84`) plus
`decompose_planner.py:483` and `routing_policy/base.py:51`. **Neither tool is a strict
superset.** ruff's unique set is real (lambdas + genuine method args); pylint's unique
set is 8 false-positives on code ruff already handles correctly.

**Decision: adopt ruff ARG** (add `"ARG"` to `[tool.ruff.lint].select`). It needs no
new dependency, catches the lambdas pylint cannot, and does NOT false-positive on the
`locals()`-consumed backward-compat kwargs. pylint W0613 would require a new install +
CI step AND 8 baselines for findings that are not real. Verdict on #210 stands REJECT,
but on corrected evidence (45/41, not 50/46, and NOT a superset).

**Claim 3: proxy_server.py "full-sorts by EWMA latency immediately after, discarding
cost order." TICKET IS ESSENTIALLY CORRECT; prior note's rebuttal is wrong.**
`order_by_cooldown` (proxy_server.py:635-663) splits fresh/cooled groups — that part is
cooldown state — but WITHIN the fresh bucket it does `fresh.sort(key=_lat_sort_key)`
(EWMA latency, missing→+inf). EWMA is the PRIMARY sort inside the fresh group, not a
tiebreaker; the incoming cost-ranked order survives only as a stable-sort tiebreak when
latency data is absent (cold start, all +inf → stable sort preserves input order). So on
a warm gateway with latency history, cost order IS discarded by the EWMA pass. This does
not invalidate #208 (the cost fallback still governs cold start and any chain that skips
the pre-sort), but it narrows the live-gateway effect window to cold-start/empty-latency
only.

---

## PR #208 — fix(forwarder): fall back to cost_rank ASC when per-provider meter is empty

**Verdict: APPROVE (DEFENSIVE LAYER; prior bounce was partially justified)**

The 2026-08-01 incident is real: openrouter key cap 403'd while deepseek-direct
(rank 8, funded, ~6x cheaper) sat further down the static chain. The fix changes
empty-meter behavior from "order unchanged" to cost_rank ASC with free-first
priority, using the same `derived_cost_rank` that `build_routes_and_pools` uses.

**Partial bounce confirmed.** The chain IS pre-sorted by `build_routes_and_pools`
(`routing_policy/__init__.py:204`: `sorted(eligible, key=_rank)` where `_rank`
returns `(not free, cost_class_priority, derived_cost_rank)` — the SAME composite
key the PR uses). Every code path that builds pool chains passes through this
function (startup `gateway.py → _resolve_config`, catalog-refresh `bridge()`,
setup-handler `_reload()`). The forwarder re-sort is therefore redundant on EVERY
chain the live gateway ever sees today.

However, the lift of registry building out of the `if live:` block gives the
empty-meter path EXPLICIT documented behaviour instead of implicit. And if any
future code path bypasses `build_routes_and_pools`, the forwarder still produces
correct order. The stable sort means an already-correct chain is unchanged.

5 tests RED on old "order unchanged" fallback; 8 green with fix. Red-proof present.
The EWMA-latency claim in the ticket is NOT misleading — `order_by_cooldown` full-sorts
the fresh bucket by EWMA (`fresh.sort(key=_lat_sort_key)`), discarding cost order once
latency history exists. The fallback's live-gateway effect is therefore limited to
cold-start / empty-latency, but that is exactly the 2026-08-01 incident window (a fresh
fleet had no meter AND no latency data). Re-verified: red-proof holds (5 fail on revert).

**OWNS-OK**: owns `src/charon/forwarder.py`, `tests/test_forwarder_cost_order.py`,
`docs/review-log/FORWARDER-COST-ORDER-FALLBACK.md` — matches changed files.

---

## PR #211 — fix(catalog): persist discovered catalog to models.json on TTL refresh

**Verdict: APPROVE (CRITICAL DEFECTS FOUND AND FIXED PRE-SUBMISSION)**

The most dangerous change of the 8 — a bad write to `models.json` kills every route.
Five defects reproduced and fixed:

- **A1 (CRITICAL):** Empty HTTP 200 treated as truth → catalog wipe. Fix: treated as
  failure, keep last-good.
- **A2 (CRITICAL):** Withdrawal set `refresh_disabled: true` (STICKY operator opt-out,
  persists forever). Fix: now sets `refresh_withdrawn: true` (our mark, reversible).
- **A3 (CRITICAL):** Unreadable `models.json` overwritten with `{}`. Fix: aborts with
  `log.critical`.
- **A4 (CRITICAL):** All-providers-down created empty `models.json`. Fix: persist
  skipped when nothing discovered; zero-enabled-models merge refused.
- **A5:** Failures invisible. Fix: `catalog_refresh_status.json` written every cycle.

Gate `catalog-persist-safety` (wired into `gates.json` + `gate_runner.py`) drives
real `CatalogRefresher` through degraded-upstream attacks against temp state dir —
behavioural, not source grep. Red-proof: pre-fix exits 1, post-fix exits 0.

Write uses config package's atomic `_store._save` (tmp + rename). Only owned files
touched. Consumers enumerated from call graph. Known limitation (single-provider
schema) documented, not a regression.

**One pre-existing defect (NOT introduced here):** `bind()` snapshots the static config
into `self._base` ONCE at startup; `bridge()` rebuilds from `dict(base_routes)` +
discovered. An operator-disabled model via setup handler is RESTORED by the next
`bridge()` from the stale baseline. Fixing this means re-reading the baseline in
`bridge()`, which is out of scope. Flagged as a follow-up.

**OWNS-OK**: owns `src/charon/routing_policy/catalog_refresh.py`,
`tests/test_catalog_refresh_persist.py`, `tools/check_catalog_persist_safety.py`,
`docs/review-log/CATALOG-REFRESH-PERSIST.md`.

---

## PR #212 — docs(price-refresher): drop rig-internal path from a PUBLIC-repo doc

**Verdict: APPROVE-WITH-UNWIRED-CAVEAT (prior note's "docs-only, trivial, safe" is FACTUALLY WRONG)**

The prior note mischaracterised this PR. The diff is NOT docs-only: it ships
`src/charon/routing_policy/price_refresher.py` (323 lines), `tests/test_price_refresher.py`
(305 lines), and a 2986-entry vendored LiteLLM pricing JSON. This is the ADR-0016 step #3
money-path module (a background sourced-price cache feeding `model_pricing`), not a docs
cleanup. The PR title mentions only the docs commit; the branch carries the whole feature.

**Reviewed the module itself.** The bridge has a latent money-path defect:
`_bridge_to_server` (price_refresher.py:~215) writes `srv.model_pricing` keyed by
`f"{prov}/{mid}"` (e.g. `"openrouter/gpt-4o"`), but the forwarder R2 lookup
(`forwarder.py:541`) reads a BARE `mid` (`route.model_id or route.pool_id`) —
verified the composite key can never match (simulated: `'openrouter/gpt-4o'` vs
`'gpt-4o'` → miss). Worse, the bridge **overwrites** `srv.model_pricing` wholesale
(`self._server.model_pricing = srv_mp`), clobbering the working bare-mid pricing
built at startup by `gateway.py:252` (`model_pricing[mid] = price`). If this module is
ever wired in, every R2 cost-rank lookup silently degrades to `{}` (neutral rank 1000).

**However: the module is UNWIRED on this branch.** No reference to `PriceRefresher` /
`price_refresher` exists anywhere in `src/` except the module itself and its test
(grep confirmed). `gateway.py:557` wires only the pre-existing `CatalogRefresher`, not
this. So as-merged it is inert — a new file nothing calls — and cannot regress the live
path today. Verdict: APPROVE the inert addition (new files only, no existing-file edits),
but the review-log MUST record the key-format defect so the wiring ticket fixes the bridge
before any `maybe_start()` lands. This is a "land the guardrails, not the wire-in" pattern.

**Tests verified:** `tests/test_price_refresher.py` runs green (counted with the suite
below). No red-proof run needed — the module is not yet reachable from production code.

---

## PR #209 — feat: DEADCODE-TOOLS-WIRE — adopt vulture+deadcode as a ratcheting merge gate

**Verdict: APPROVE (verified clean adoption; pyproject.toml conflict with #215)**

vulture (100% confidence only) + deadcode adopted as one deduplicated
findings-budget-ratcheting gate. Baseline: 169 findings, shrinking-only ratchet
(BUDGET-OUT-OF-DATE branch fails closed).

**Verified:**
- `forwarder.py:934` deletion is safe: `forward_with_failover` annotated `-> None`,
  every leaf returns/re-raises, the removed `return` is unreachable.
- vulture restricted to 100% confidence avoids 328 double-counts against deadcode.
- 15 red-proof tests: unused-function RED, unreachable-after-try RED, ratchet
  above/below/equal, dedupe, green-path, gate-runner wiring, gates.json
  registration.
- `pyproject.toml` adds `vulture>=2.11` and `deadcode>=2.4` to dev deps.

**CONFLICT ANALYSIS:** PR #209 modifies `[project.optional-dependencies].dev` in
pyproject.toml. PR #215 modifies `[tool.ruff.lint].select` and adds
`[tool.ruff.lint.per-file-ignores]`. These are NON-OVERLAPPING hunks — no merge
conflict. Either can land first; the other rebases cleanly. CONFIRMED: no conflict
with #215.

The `@pytest.importorskip("vulture")` + `@pytest.importorskip("deadcode")` pattern
means the new gate silently skips if the tools aren't installed. This is fine for
dev/test environments but the CI gate runner must have these tools installed. The PR
adds them to `dev` deps — CI must run with dev deps installed.

---

## PR #210 — feat: add red-proof tests for pylint W0613 (unused-argument) detection

**Verdict: REJECT-AS-IS (adopt ruff ARG instead; measured evidence contradicts ticket)**

Ticket says: "MEASURED: ruff --select ARG = 406 findings, pylint W0613 = 46. They
are NOT equivalent; decide on evidence which single tool we adopt."

**Re-measured at HEAD (2026-08-01): ruff ARG = 45, pylint W0613 = 41** (src-only).
Neither the ticket's 406 nor the prior note's 50 reproduces. Full tree: ruff 385,
pylint 186.

**The tools are NOT equivalent and NEITHER is a strict superset.** 8 pylint-only
locations exist, but all 8 are false positives: `connect.py:347` is a documented
`pass`-stub whose arg is genuinely unused (pylint flags it; ruff skips it as a stub),
and `proxy_server.py:485-491` are backward-compat `__init__` kwargs consumed via the
`locals()` merge loop — pylint can't see the indirection and cries W0613, ruff does not.
Ruff's 10 unique findings are ARG005 (lambdas, which pylint cannot detect) plus two
genuine method args (`decompose_planner.py:483`, `routing_policy/base.py:51`).

**Recommendation: adopt ruff ARG (one line: add "ARG" to pyproject.toml select).**
It requires no new tool install, no new CI step, no new maintenance, catches a class
pylint can't (lambdas), and does not false-positive on the `locals()`-consumed kwargs.
Adopting pylint instead would add a dependency + CI step AND require baselining 8
findings that are not real defects.

**If pylint W0613 is still pursued:** the factual error in the ticket (406 findings)
must be corrected. The PR as-written only adds tests — it does NOT wire W0613 into
CI or pyproject.toml. Without the wire-in, the 46-baseline number drifts silently.

The PR's own session report shows `RED-PROOF: broken=1 green=0` — one redproof test
was broken at commit time. Needs resolution before landing.

---

## PR #215 — feat(ci): enable ruff S and BLE security rule families

**Verdict: APPROVE (sound; verified no conflict with #209)**

Switch-on is sound. 70 src findings baselined with written per-file, per-rule
justifications (not a blanket noqa). The two genuine security findings (S602
shell=True in acceptance.py, S104 bind-all in gateway.py) are pinned to their files
with reasons — not swept — so they stay visible and fixable by source-owning tickets.

Red-proof tests assert the families stay selected: removing S or BLE from the select
list causes test failures. Gate: 2384 passed, 3 skipped, 1 xfailed, 1 xpassed.

**Cross-checked against RUFF-SEC-RULES-ON chain.** Only two PRs touch pyproject.toml:
#209 (dev deps) and #215 (select + per-file-ignores). Non-overlapping hunks — no
conflict. Both base off da9f786.

**Per-file ignores for tests:** S602 is deliberately NOT baselined under `tests/**` —
a new `shell=True` in tests WOULD go red. Verified: the `tests/**` per-file-ignores
entry does not list S602.

**Residual risk (acknowledged):** per-file baselines mean new code added to baselined
files is NOT checked for that rule. A source-owning ticket should shrink these entries.

---

## PR #216 — docs(review-log): GATEWAY-GRADE-ORDER-MVP fragment

**Verdict: APPROVE (documentation; new source files, no conflict with other PRs)**

5 files changed: `docs/review-log/GATEWAY-GRADE-ORDER-MVP.md` (review fragment),
`src/charon/capability/product_grades.py` (new), `src/charon/routing_policy/grade_order.py`
(new), `tests/test_grade_order.py` (new), `tests/test_product_grades.py` (new).

The GATEWAY-GRADE-ORDER-MVP design builds outcome-grade ordering as one inseparable
seam: neutral product-grade store + grade-ordering overlay wired into
`litellm.Router.set_custom_routing_strategy`. FAIL-OPEN: empty/missing grades file
→ byte-identical chain order. Gate: 2475 passed, 3 skipped, 1 xfailed, 1 xpassed.

No pyproject.toml edits — no conflict with #215 or #209. No edits to existing source
files — no conflict with #208/#211/#212. All files are new additions. Outside
money-path scope; this is a new routing dimension.

---

## PR #214 — docs(adr-0021): disposition all 52 litellm.Router.__init__ params

**Verdict: APPROVE (documentation-only; verified no code changes)**

Three files changed: `ADOPT-MAP.md` (updated), `docs/adr/0021-litellm-capability-adoption.md`
(new ADR), `tests/test_litellm_capability_map.py` (new test asserting ADR param list
matches INSTALLED `Router.__init__` signature). No product code changes in `src/`.
Low risk. Outside money-path scope.

---

## Cross-PR conflict summary

| PR  | Verdict | pyproject.toml | src edits | conflicts with |
|-----|---------|----------------|-----------|----------------|
| #208 | APPROVE | no | forwarder.py | none |
| #211 | APPROVE | no | catalog_refresh.py, gate_runner.py | #209 (gate_runner — both add CHECKS entry; additive, trivial) |
| #212 | APPROVE (unwired) | no | NEW module only — NOT docs-only (prior note wrong) | none |
| #209 | APPROVE | yes (dev deps) | forwarder.py:934, gate_runner.py | #215 (different pyproject hunk — no conflict, merge-tested) |
| #210 | REJECT | no | tests only | none |
| #215 | APPROVE | yes (select+ignores) | none | #209 (different pyproject hunk — no conflict, merge-tested) |
| #216 | APPROVE | no | new files only | none |
| #214 | APPROVE | no | docs + test only | none |

**No blocking conflicts among approved PRs.** #209/#215 touch different pyproject
hunks (dev deps vs lint config). #209/#211 both append to gate_runner CHECKS list
(additive, trivial merge). #208/#209 both touch forwarder.py but at different lines
(#208 adds code in lines 527-556, #209 deletes one line at 934 — no conflict).

---

## Defects found

1. **Ticket factual error**: ruff ARG = 406 claim is wrong; measured 45 src-only
   (385 full tree). Prior note's "50" is also wrong. (#210)
2. **Prior note factual error**: claimed ruff ARG is a strict superset of pylint
   W0613 (50 vs 46). Measured 45 vs 41 with 8 pylint-only locations (all false
   positives). Neither is a superset; ruff is the correct adoption anyway. (#210)
3. **Prior note factual error**: claimed #212 is "docs-only, trivial, safe". The PR
   ships a 323-line money-path module + 2986-entry vendored JSON. (#212)
4. **Prior note factual error**: claimed proxy_server's EWMA sort is "a secondary
   tiebreaker". It is the PRIMARY sort within the fresh bucket. (#208)
5. **NEW latent money-path defect in #212**: `_bridge_to_server` writes `model_pricing`
   keyed `"prov/mid"` which the forwarder R2 lookup (bare `mid`) can never read, AND
   overwrites the working bare-mid pricing wholesale. Inert until wired — the wiring
   ticket must fix it first.
6. **PR #210 red-proof broken**: session report shows broken=1 green=0.
7. **PR #211 pre-fix defects** (all fixed by submit time): A1 (wipe on empty 200),
   A2 (sticky disable), A3 (unreadable overwrite), A4 (empty write on total failure),
   A5 (silent degradation).
