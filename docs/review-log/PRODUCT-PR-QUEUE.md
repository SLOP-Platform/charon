# PRODUCT-PR-QUEUE — adversarial review fragment

**Reviewer:** obi-wan-kenobi (deepseek-v4-pro-ds)
**Date:** 2026-08-02
**Branch:** chore/product-pr-queue (off origin/master)

## Scope

8 PRs reviewed in ticket order: #208, #211, #212, #215, #210, #209, #214, #216.

---

## #208 — FORWARDER-COST-ORDER-FALLBACK

**Verdict: APPROVE (DEFENSIVE LAYER, not a no-op in principle)**

**Bounce claim analysis.** The prior review bounced this as a "strict no-op" on three
grounds. Each was verified against the live tree:

1. **"the chain is already sorted with the identical key at startup."** CONFIRMED.
   `build_routes_and_pools` (`routing_policy/__init__.py:204`) sorts every pool chain
   by `sorted(eligible, key=_rank)` where `_rank` returns `(not free,
   cost_class_priority, derived_cost_rank)` — the SAME composite key the PR's
   `_cost_rank_key` uses. Every code path that builds pool chains (startup
   `gateway.py → _resolve_config`, catalog-refresh `bridge()`, setup-handler
   `_reload()`) passes through this function. The forwarder's re-sort is therefore
   redundant on EVERY chain the live gateway ever sees today.

2. **"proxy_server.py full-sorts by EWMA latency … discarding cost order."**
   PARTIALLY CONFIRMED. `order_by_cooldown` (`proxy_server.py:654-677`) splits
   fresh/cooled and sorts each by EWMA latency, which does discard cost rank within
   those groups once latency data exists. On cold start (all EWMA = 0.0), the
   incoming order is preserved. But even then, the R2 reorder runs BEFORE
   `order_by_cooldown` is called — latency is only a tiebreaker after cooldown, not
   a replacement for the pre-filter chain order.

3. **"the live catalog has 10 of 861 models priced so the sort key is degenerate."**
   UNABLE TO VERIFY in this worktree — `config/models.json` does not exist on-disk
   in the checkout (gitignored or deployment-only). If true, unpriced models all
   derive `cost_rank=1000` and the stable sort is a no-op regardless.

**Why APPROVE despite the no-op findings.** The change lifts registry building out of
the `if live:` block and gives the empty-meter path EXPLICIT documented behaviour
(free-first → metered → cost_rank ASC → static tiebreak) instead of an implicit
"hope the chain order stays correct." If any future code path builds pool chains
without passing through `build_routes_and_pools`, the forwarder still produces a
correct order. The 8-test suite is green, 5 of them RED on revert. No product-risk
regression: the sort is stable, so an already-correct chain is unchanged.

---

## #211 — CATALOG-REFRESH-PERSIST

**Verdict: APPROVE (defects found-and-fixed pre-submission)**

The write-back to `models.json` is the highest-risk path — a bad write kills every
route. Five defects reproduced before fixing, each verified fixed:

- **A1**: empty HTTP 200 treated as truth → now treated as failure (keep last-good).
- **A2**: withdrawal set `refresh_disabled: true` (sticky operator opt-out) → now
  sets `refresh_withdrawn: true` (reversible).
- **A3**: unreadable `models.json` written as `{}` → now aborts with `log.critical`.
- **A4**: all-providers-down created empty `models.json` → now skipped.
- **A5**: failures invisible → `catalog_refresh_status.json` written every cycle.

Gate `catalog-persist-safety` (wired into `gates.json`) drives real
`CatalogRefresher` through degraded-upstream attacks against temp state dir.
Behavioural, not source grep. Red-proof: pre-fix exits 1, post-fix exits 0.

Write uses config package's atomic `_store._save` (tmp + rename). Only owned files
touched. Consumers enumerated from call graph. Known limitation (single-provider
schema) documented, not a regression.

---

## #212 — PRICE-REFRESHER

**Verdict: APPROVE (docs-only: drops rig-internal path from PUBLIC repo)**

PR #212 changes only `docs/review-log/PRICE-REFRESHER.md`. Drops rig-internal
file-path references from a PUBLIC-repo document. No source code changes. No risk.

---

## #215 — RUFF-SEC-RULES-ON

**Verdict: APPROVE**

**Cross-check against RUFF-SEC-RULES-ON chain.** Only two open PRs touch
`pyproject.toml`: #209 (adds vulture/deadcode to `dev` deps) and #215 (adds S/BLE
to `select` + per-file-ignores). These are non-overlapping hunks — #209 modifies
`[project.optional-dependencies].dev`, #215 modifies `[tool.ruff.lint].select` and
adds `[tool.ruff.lint.per-file-ignores]`. No merge conflict. Land order is
non-semantic; either can land first, the other rebases cleanly.

**Switch-on surface measured at HEAD:** 70 src findings (not "72" — the ticket's
prior snapshot), 4616 test findings, 13 tools findings. Each baselined per-file,
per-rule, with written reason. The ONE genuine S602 `shell=True` finding
(`acceptance.py:52`) is pinned, not swept — a src-owning ticket must fix it.

Red-proof tests (`test_lint_security_rules.py`) verify: removing `"S"` from select
goes RED (2 fail), restored → green. Gate: 2384 passed, 3 skipped, 1 xfailed, 1
xpassed.

**One residual concern (NOT blocking):** the `tests/**` per-file-ignores blanket
exempts S602 from all test files. The review note says "S602 is never exempted for
`tests/**`" — but the per-file-ignores entry for `tests/**` does NOT list S602, so
new `shell=True` in tests WOULD go red. Verified: this is correct; S602 is not
baselined for tests.

---

## #210 — PYLINT-UNUSED-ARGS

**Verdict: REJECT-AS-IS (adopt ruff ARG, not pylint W0613)**

**Key measurement — the ticket claims ruff ARG = 406 findings. MEASURED at HEAD: 50.**
```
$ ruff check --select ARG --output-format concise src | grep -c "^src/"
50
$ python3 -m pylint --disable=all --enable=W0613 src | grep -c "W0613"
46
```

The PR's review note correctly states pylint W0613 ≈ 46. The 406 figure in the
ticket is incorrect for the current tree.

**The tools are NOT equivalent — ruff ARG is a strict superset.** 46 findings are
identical between the two. Four extra ruff findings are `ARG005` (unused lambda
arguments: `gateway.py:75-104` lambda `sd`/`d`, `cli.py:2208:32` lambda `a`,
`connect.py:406:23` lambda `w`) — pylint does NOT flag unused lambda arguments.

**Recommendation: adopt ruff ARG.** It requires no new tool installation (ruff is
already the project linter), no new CI step, no new maintenance. The change is ONE
line in pyproject.toml: add `"ARG"` to `select`. Compare to pylint W0613 which
requires adding pylint as a dependency, installing it in CI, and maintaining
separate configuration.

The PR as-written only adds tests for pylint W0613 — it does NOT wire W0613 into CI
or `pyproject.toml`. Without the wire-in, the 46-baseline number drifts silently. A
follow-on ticket would be needed to complete adoption.

If W0613 is pursued, the factual error in the ticket (ruff ARG = 406) must be
corrected and the case for pylint over the superset tool must be argued explicitly.

---

## #209 — DEADCODE-TOOLS-WIRE

**Verdict: APPROVE (verified clean adoption)**

vulture (100% confidence only) + deadcode adopted as one deduplicated
findings-budget-ratcheting gate (`tools/check_deadcode_tools.py`). Baseline: 169
findings, shrinking-only ratchet (BUDGET-OUT-OF-DATE branch fails closed).

**Verified:**
- `forwarder.py:934` deletion is safe: `forward_with_failover` annotated `-> None`,
  every leaf returns/re-raises, the removed `return` is unreachable.
- vulture restricted to 100% confidence avoids 328 double-counts against deadcode.
- 15 red-proof tests: unused-function RED, unreachable-after-try RED, ratchet
  above/below/equal, dedupe, green-path, gate-runner wiring, gates.json
  registration.
- `pyproject.toml` adds `vulture>=2.11` and `deadcode>=2.4` to dev deps — no
  conflict with #215 (different hunk).

---

## #214 — LITELLM-CAPABILITY-ADOPTION (ADR-0021)

**Verdict: APPROVE (design pass, no code changes)**

PR #214 is a DESIGN PASS only: updates `ADOPT-MAP.md` with complete file:line deletion
map, adds `docs/adr/0021-litellm-capability-adoption.md` (52-param disposition table
with ADOPT/DECLINE/DEFER verdicts), and adds `tests/test_litellm_capability_map.py`
(asserts ADR's param list matches INSTALLED `Router.__init__` signature — prevents
silent drift on litellm upgrade). No product code changes in `src/`. Low risk.

---

## #216 — GATEWAY-GRADE-ORDER-MVP

**Verdict: APPROVE (verified self-contained, no cross-PR conflict)**

Two new source files + two new test files. Product-grade store (`product_grades.py`)
enforces rig→product boundary (AST guard test, stdlib-only). Grade-order overlay
(`grade_order.py`) hooks into `Router.set_custom_routing_strategy`. FAIL-OPEN:
empty/missing grades file → byte-identical chain order. Accept-test minimum bar
(grade orders, byte-identical cold start) both met. Gate: 2475 passed, 3 skipped, 1
xfailed, 1 xpassed.

No pyproject.toml edits — no conflict with #215 or #209. No edits to existing
source files — no conflict with #208/#211/#212.

---

## Cross-PR conflict matrix

| PR | pyproject.toml | src edits | conflicts with |
|---|---|---|---|
| #208 | no | forwarder.py | none |
| #209 | yes (dev deps) | forwarder.py:934 | #208 (same file, different hunks — mergeable) |
| #210 | no | tests only | none |
| #211 | no | catalog_refresh.py, gate_runner.py | #209 (gate_runner.py — same hunk, different entry. Both add a line; merge strategy resolves) |
| #212 | no | docs only | none |
| #214 | no | docs + tests only | none |
| #215 | yes (select + ignores) | none | #209 (different pyproject.toml hunks — no conflict) |
| #216 | no | new files only | none |

**No blocking conflicts.** The #211/#209 overlap in `gate_runner.py` CHECKS list is
additive (both append one non-conflicting entry). Land order: #209 first → #211
rebases to include the deadcode-tools line before its catalog-persist-safety entry,
or vice versa. Either order trivially resolves.

## Defect summary

1. **Ticket factual error**: ruff ARG = 406 claim is wrong; measured 50. (#210)
2. **#208 bounce partially wrong**: the chain IS pre-sorted, but the bounce's
   EWMA-discard argument is misleading — EWMA is a tiebreaker within cooldown groups,
   not a replacement for the pre-filter chain order. The PR adds explicit documented
   fallback behavior; APPROVE as defensive layer.
3. **#211 pre-fix defects (all fixed):** A1 (wipe on empty 200), A2 (sticky
   disable), A3 (overwrite on unreadable), A4 (empty write on total failure), A5
   (silent degradation).

