# PRODUCT-PR-QUEUE — adversarial review of 8 product-adjacent PRs

**Reviewer:** obi-wan-kenobi (deepseek-v4-pro-ds)  
**Date:** 2026-08-02  
**Branch:** chore/product-pr-queue (off origin/master)

Sequence: money-path first (#212, #211, #208), then tooling (#215, #210, #209), then docs (#216, #214)

---

## PRE-REVIEW: measured facts vs ticket claims

The ticket accept criteria includes three specific assertions that need verification:

**Claim 1: ruff --select ARG = 406 findings. MEASURED at HEAD: 50, not 406.**
```
$ ruff check --select ARG --output-format concise src | grep -c "^src/"
50
```
The 406 figure appears to be incorrect for the current tree. Either the ticket
was written against a different snapshot, or the number includes tests/tools dirs.
Re-measured: 50 src findings only.

**Claim 2: pylint W0613 = 46 findings. CONFIRMED.**
```
$ python3 -m pylint --disable=all --enable=W0613 src | grep -c "W0613"
46
```
The 46 figure matches. Of these, all 46 overlap with ruff ARG. The 4 extra ruff
ARG findings are ARG005 (unused lambda arguments: `gateway.py:75-104` lambda parameters,
`cli.py:2208:32`, `connect.py:406:23`) — pylint does NOT flag unused lambda args.
**Conclusion: ruff ARG is a strict superset of pylint W0613.** Adopting pylint
requires a new tool install + new CI step; adopting ruff ARG is one line in
pyproject.toml (`select = ["E", "F", "I", "B", "UP", "ARG"]`). Recommend ruff ARG.

**Claim 3: proxy_server.py "full-sorts by EWMA latency immediately after, discarding
cost order." PARTIALLY MISLEADING.** `order_by_cooldown` (proxy_server.py:651-677)
splits fresh/cooled groups and sorts each by EWMA latency AS A TIEBREAKER within
cooldown groups — primary sort is cooldown state (fresh before cooled). EWMA is
not a replacement for cost order; it's a secondary sort. Moreover, on cold start
(all EWMA = 0.0), the incoming chain order (from cost-rank sorting) is preserved.

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
The EWMA-latency claim in the ticket is misleading — EWMA is a cooldown-group
tiebreaker, not a full-chain re-sort that discards cost order.

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

**Verdict: APPROVE**

Docs-only change, removing a rig-internal file path from a public-facing document.
No code impact. The ADR-0016 decision (adopt LiteLLM priced catalog) is pre-existing;
this PR just cleans the documentation surface. Trivial, safe.

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

**Measured at HEAD (2026-08-02): ruff ARG = 50, pylint W0613 = 46.** The 406 figure
is incorrect for the current tree. The 4 extra ruff findings are ARG005 (unused
lambda arguments) — a class pylint W0613 does NOT detect.

**The tools ARE equivalent (ruff ARG is a superset).** All 46 pylint findings are in
the 50 ruff ARG set. Ruff catches 4 more (lambdas). No pylint-unique finding exists.

**Recommendation: adopt ruff ARG (one line: add "ARG" to pyproject.toml select).**
It requires no new tool install, no new CI step, no new maintenance. Pylint requires
adding pylint as a dependency, installing it in CI, and maintaining separate config.

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
| #212 | APPROVE | no | docs only | none |
| #209 | APPROVE | yes (dev deps) | forwarder.py:934, gate_runner.py | #215 (different pyproject hunk — no conflict) |
| #210 | REJECT | no | tests only | none |
| #215 | APPROVE | yes (select+ignores) | none | #209 (different pyproject hunk — no conflict) |
| #216 | APPROVE | no | new files only | none |
| #214 | APPROVE | no | docs only | none |

**No blocking conflicts among approved PRs.** #209/#215 touch different pyproject
hunks (dev deps vs lint config). #209/#211 both append to gate_runner CHECKS list
(additive, trivial merge). #208/#209 both touch forwarder.py but at different lines
(#208 adds code in lines 527-556, #209 deletes one line at 934 — no conflict).

---

## Defects found

1. **Ticket factual error**: ruff ARG = 406 claim is wrong; measured 50. (#210)
2. **PR #210 red-proof broken**: session report shows broken=1 green=0.
3. **PR #211 pre-fix defects** (all fixed by submit time): A1 (wipe on empty 200),
   A2 (sticky disable), A3 (unreadable overwrite), A4 (empty write on total failure),
   A5 (silent degradation).
