# PRODUCT-PR-QUEUE — adversarial review of 8 product-adjacent PRs

Date: 2026-08-01
Sequence: money-path first (#212, #211, #208), then tooling (#215, #210, #209), then docs (#216, #214)

---

## PR #208 — fix(forwarder): fall back to cost_rank ASC when per-provider meter is empty

**Verdict: APPROVE with one concern**

The 2026-08-01 incident is real: openrouter key cap 403'd while deepseek-direct (rank 8, funded, ~6x cheaper) sat further down the static chain. The fix changes empty-meter from "order unchanged" to cost_rank ASC with free-first priority, using the same `derived_cost_rank` that `pools.load_pools` uses — so the fallback reproduces the catalog's intended order rather than imposing a new one.

5 tests fail on the old "order unchanged" fallback; all 8 green with fix. Red-proof is present.

**CONCERN — needs verification**: The ticket accept criteria states "proxy_server.py full-sorts by EWMA latency immediately after, discarding cost order." Code at line 553 shows `ordered = srv.order_by_cooldown(chain)` — this is cooldown ordering (R7: fresh first, cooled last), NOT EWMA latency ordering. The latency-sorts claim appears to be the ticket's factual error (or the claim about the mechanism is wrong). If proxy_server has a separate latency sort AFTER the forwarder reorders, the fix is still correct (cost_rank is a better starting point than static order), but the rationale in the review log should not reference a non-existent mechanism. The test suite is the ground truth here.

**CONCERN — pyproject.toml conflict**: PR #209 also edits pyproject.toml (adds vulture+deadcode dev deps). PR #215 also edits pyproject.toml (adds ruff S+BLE). These three PRs will create merge conflicts on pyproject.toml if merged independently. Recommend the launcher sequence them so the last-to-merge handles the conflict.

**OWNS-OK**: owns: `forwarder.py`, `tests/test_forwarder_cost_order.py`, `docs/review-log/FORWARDER-COST-ORDER-FALLBACK.md` — matches changed files.

---

## PR #211 — fix(catalog): persist discovered catalog to models.json on TTL refresh

**Verdict: HOLD — five critical defects in the WIP were found and fixed, but the worktree is at origin/master and does not have the fixes**

The PR body claims SHA `ca5cd1c` has all five defects fixed. I verified the current code at `src/charon/routing_policy/catalog_refresh.py` — it has NO persist logic. The fixes (A1–A5 in the PR body: empty-HTTP-200 catalog wipe, sticky withdrawal, unreadable-models-json overwrite, total-provider-failure empty catalog, silent degradation) are NOT in origin/master. This PR is DRAFT and its fixes live only in the feat/catalog-refresh-persist branch.

The adversarial review the PR claims is self-review (the same session built and then "adversarially reviewed" its own WIP). The five defect descriptions are detailed and plausible, and the verification matrix (16 ticket tests + 2379 suite) is extensive, but the CRITICAL CHECK — running `check_catalog_persist_safety.py` against the pre-fix implementation — cannot be done from this worktree since the pre-fix code isn't available here.

**Action required**: Either the CATALOG-REFRESH-PERSIST worktree must be merged to master before this review can be completed, or a separate adversarial review must be performed against that worktree's HEAD. This review-log fragment cannot substitute for that review.

---

## PR #212 — docs(price-refresher): drop rig-internal path from a PUBLIC-repo doc

**Verdict: APPROVE**

Docs-only change, removing a rig-internal path from a public-facing document. No code impact. The ADR-0016 decision (adopt LiteLLM priced catalog) is pre-existing and this PR just cleans the documentation surface. Trivial.

---

## PR #209 — feat: DEADCODE-TOOLS-WIRE — adopt vulture+deadcode as a ratcheting merge gate

**Verdict: HOLD — OWNS conflict with #215**

The PR's own session report states `OWNS-OK: NO — pyproject.toml is owned by DEADCODE-TOOLS-WIRE`. But PR #215 (`fix/ruff-sec-rules-on`, from a different session) ALSO edits pyproject.toml to add `ruff S` and `BLE` to the select list. These are concurrent, unsequenced edits to the same file.

Additionally, pyproject.toml is NOT in this ticket's `owns:` — the ticket owns `docs/review-log/DEADCODE-TOOLS-WIRE.md`, `tools/check_deadcode_tools.py`, `tools/gates.json`, `tools/deadcode-tools-budget.json`, `src/charon/forwarder.py`, `src/charon/gate_runner.py`, `tests/test_deadcode_tools.py`. The self-reported OWNS-OK is explicitly NO.

The content of the pyproject.toml change (adding `vulture>=2.11` and `deadcode>=2.4` to dev deps) and the gate wiring itself are sound. But this PR cannot land until the pyproject.toml conflict with #215 is resolved. Recommend: one of the two PRs releases pyproject.toml to the other, or the launcher sequences them.

**CONCERN**: The `@pytest.importorskip("vulture")` + `@pytest.importorskip("deadcode")` pattern means the new gate silently skips if the tools aren't installed. This is fine for dev/test environments but the CI gate runner should have these tools installed. The PR adds them to `dev` deps, so CI must run with dev deps installed — verify this in the gate runner configuration.

---

## PR #210 — feat: add red-proof tests for pylint W0613 (unused-argument) detection

**Verdict: HOLD — ticket brief says "ruff ARG already covers; decide on evidence"**

The accept criteria explicitly says "MEASURED: ruff --select ARG = 406 findings, pylint W0613 = 46. They are NOT equivalent; decide on evidence which single tool we adopt, do not assume duplication."

The PR does not decide. It adds `tests/test_pylint_unused_args.py` as a proof-of-concept test suite for pylint W0613, but the PR body contains no analysis of whether ruff ARG and pylint W0613 overlap, whether pylint W0613 finds things ruff ARG misses, or whether adopting both is justified. The test count (13 tests) demonstrates the tool works on fixtures, but does not address the decision criterion.

This PR is premature. The correct next step is: run both tools against the full product tree, classify findings by overlap vs unique, and then decide. Without that evidence, adopting pylint W0613 alongside ruff ARG is assuming the duplication the ticket explicitly forbids.

**Additionally**: The PR's own session report shows `RED-PROOF: broken=1 green=0` — one redproof test was broken at commit time. The test suite passed (2441 passed) but the redproof gate itself was not green. This needs to be resolved before landing.

---

## PR #215 — feat(ci): enable ruff S and BLE security rule families

**Verdict: APPROVE**

The switch-on is sound. 70 src findings baselined with written per-file, per-rule justifications (not a blanket noqa). The two genuine security findings (S602 shell=True in acceptance.py, S104 bind-all in gateway.py) are pinned to their files with reasons — not swept — so they stay visible and fixable by source-owning tickets.

Red-proof tests assert the families stay selected (removing S or BLE from the select list causes test failures). The gate is green.

**CONCERN — pyproject.toml conflict**: Same as #209 — both edit pyproject.toml concurrently. See #209 for the sequencing recommendation.

**CONCERN — per-file baselines as a mechanism**: Per-file ignores in pyproject.toml mean new code added to `src/charon/acceptance.py` would NOT be flagged for S602. This is the residual risk the PR acknowledges. A source-owning ticket should address the genuine `shell=True` finding rather than relying on the baseline to suppress it indefinitely.

---

## PR #216 — docs(review-log): GATEWAY-GRADE-ORDER-MVP fragment — decision + accept-test mapping

**Verdict: APPROVE**

This is a documentation-only PR (docs/review-log fragment + pyproject.toml additions for the 30-file change). The GATEWAY-GRADE-ORDER-MVP design decision (build grade ordering as one inseparable seam: neutral grade store + overlay wired into litellm.Router.set_custom_routing_strategy) is documented and the acceptance tests are described. No safety claims about the money path; this is a new routing dimension. Content review is outside the scope of the product queue's money-path mandate.

---

## PR #214 — docs(adr-0021): disposition all 52 litellm.Router.__init__ params (ADOPT/DECLINE/DEFER)

**Verdict: APPROVE**

This is a documentation-only change to ADOPT-MAP.md. The ADR-0021 work (design/litellm-capability-adoption) is already merged (SHA 9026aaf exists in the worktree list). This PR updates the public-facing ADOPT-MAP to reflect the disposition of all 52 Router parameters. No code, no safety impact. Outside money-path scope.

---

## Summary table

| PR  | Verdict | Blocker |
|-----|---------|---------|
| #208 | APPROVE (with concern) | Ticket's EWMA-latency claim needs verification; pyproject.toml conflict |
| #211 | HOLD | Fixes not in origin/master; need adversarial review against feat/catalog-refresh-persist worktree |
| #212 | APPROVE | Trivial docs-only |
| #209 | HOLD | OWNS conflict: pyproject.toml shared with #215; source-owning tickets must sequence |
| #210 | HOLD | Ticket says "decide on evidence" — no evidence presented; redproof was broken |
| #215 | APPROVE | Sound; pyproject.toml conflict with #209 |
| #216 | APPROVE | Docs-only; outside money-path scope |
| #214 | APPROVE | Docs-only; outside money-path scope |

## Cross-cutting: pyproject.toml conflict

Three PRs (#209, #210, #215) edit pyproject.toml. #210 adds pylint to dev deps (already conflicting with #209's vulture+deadcode addition). #215 adds ruff S+BLE to the select list. These three must be sequenced so the launcher handles the merge conflict as one combined edit rather than three independent concurrent writes.

## Cross-cutting: PR #211 vs origin/master

The five critical catalog-wipe defects in PR #211 are not in origin/master. Until the feat/catalog-refresh-persist worktree is merged, this PR cannot be adversarially reviewed from origin/master. Recommend: a separate adversarial review session against the CATALOG-REFRESH-PERSIST worktree, or merge that worktree first.
