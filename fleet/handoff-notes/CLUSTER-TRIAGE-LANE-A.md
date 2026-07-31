# CLUSTER TRIAGE — LANE A

## Summary

| Branch | Ticket | Age | Commits | Verdict | One-line what-it-does | PR? |
|---|---|---|---|---|---|---|
| feat/substrate-first-gate-v2 | — | 11d | 3 | LAND | Substrate gate v2: replace hand-rolled parser, close 9 adversarial evasions, add rig CI test suite | N/A |
| feat/fixture-bypass-gate | — | 11d | 3 | LAND | Mechanize fixture-bypass + gate-integrity (the gate on the gates), wire into preflight | N/A |
| review/reconcile-gate-design | REVIEW-RECONCILE-GATE-DESIGN | 8d | 1 | LAND | Adversarial review verdict on UNIFIED-RECONCILIATION-GATE-DESIGN (PR #178) | N/A |
| feat/ticket-lifecycle-canary | TICKET-LIFECYCLE-CANARY | 7d | 3 | LAND | Hermetic control-plane ticket-lifecycle canary (mint→claim→build→land→retire) | N/A |
| feat/ordering-cost-primary | — | 20d | 1 | REWORK | Option A cost-primary ordering + slow failover + 3 pre-existing test fixes (product repo) | N/A |

## Prior-verdict checks

### feat/substrate-first-gate-v2 — prior verdict: NOTHING-SURVIVES → **OVERTURNED**

**Evidence:** Commits 03ba2b1 and 06b1764 (cited by prior review) ARE on master, but they are V1 FIXES. This branch has 3 V2 commits on top of them. Master still has the OLD `substrate_first_gate.py` parser — proven:

```
$ git -C .../SUBSTRATE-GATE-V2 show master:fleet/checks/substrate_first_gate.py | grep -n "fnmatch\|parse_frontmatter\|_base_ref_tip\|ls-tree"
35:import fnmatch
101:    return parse_frontmatter(raw)
104:def parse_frontmatter(raw: str) -> dict:
338:def _base_ref_tip(root: str) -> str | None:
```

Branch removes all of these — a real, unlanded rewrite. Additionally:

```
$ git -C .../SUBSTRATE-GATE-V2 ls-tree --name-only master -- fleet/tests/rig-ci-scope.test.sh fleet/tests/large-file-guard.test.sh
(empty — neither file exists on master)
```

The branch adds `rig-ci-scope.test.sh` (323 lines) and `large-file-guard.test.sh` (110 lines) — both absent from master. **This is real work. The prior verdict was wrong.**

## Per branch

### feat/substrate-first-gate-v2 (SUBSTRATE-GATE-V2)
- **What it does:** V2 substrate gate — replaces the V1 hand-rolled parser, closes 9 adversarial evasions, moves gate timing to DECISION point (not session start), fixes B5 pre-existing failure surfaced by the gate. Adds comprehensive rig-ci-scope test suite and large-file-guard test.
- **Evidence:** Three-dot diff: 31 files, +1147/-753. Two-dot diff restricted to those paths confirms all changes are unlanded. Merge-base: e8d25d3 (2026-07-17). No board ticket exists (neither active nor archived).
- **Verdict:** **LAND** — OVERTURN prior NOTHING-SURVIVES verdict. Real, wanted work that still applies.
- **Conflict risk vs master:** Low on the Python (substrate_first_gate.py simplifies by removing code — cleanup, not new logic). Medium on fleet/checks/rig-ci-scope.sh (shared with FIXTURE-BYPASS-GATE). Low elsewhere.
- **Lost if dropped:** Parse rewrite closing 9 adversarial evasions. Rig CI test infrastructure (the rig had NO CI tests before this). Large-file-guard test. Multiple board file additions including REVIEWER-DOGFOOD-REDS and memory/ infrastructure.

### feat/fixture-bypass-gate (FIXTURE-BYPASS-GATE)
- **What it does:** Mechanizes two new gates: `fixture-bypass.sh` (detects test suites green over production paths they never run — 6 confirmed instances in one day) and `gate-integrity.sh` (the gate on the gates — 4 distinct shapes of "gate reads as protection but provides none"). Simplifies `rig-ci-scope.sh` and wires both into `preflight.sh`.
- **Evidence:** Three-dot diff: 7 files, +1156/-298. Two-dot confirms 4 new files (fixture-bypass.sh, gate-integrity.sh, and their test suites) do not exist on master. Merge-base: 0a66517 (12 days ago).
- **Verdict:** **LAND** — solid mechanized gate infrastructure. No board ticket exists.
- **Conflict risk vs master:** Low on the gate-integrity and fixture-bypass scripts (wholly new). Medium on preflight.sh (wiring integration — may need reconciliation with any other preflight additions). Low on rig-ci-scope.sh (simplifies existing).
- **Lost if dropped:** Fixture-bypass detection class (catches green-over-unrun-paths — a defect class that produced 6 false-greens). Gate-integrity detector (a meta-gate — it's the only thing asking "is this gate alive?"). Preflight wiring for both. This is the defensive layer that makes all other gates trustworthy.

### review/reconcile-gate-design (REVIEW-RECONCILE-GATE-DESIGN)
- **What it does:** Adversarial review verdict on the UNIFIED-RECONCILIATION-GATE-DESIGN (PR #178). Recommends APPROVE-FOR-OPERATOR with 2 NEEDS-REVISION items. Ground-truthed against live repos; no design prose accepted at face value.
- **Evidence:** Three-dot diff: 1 file, 243 insertions (`fleet/state/REVIEW-RECONCILE-GATE-DESIGN.md`). Active board ticket exists at `fleet/board/REVIEW-RECONCILE-GATE-DESIGN.md`.
- **Verdict:** **LAND** — this is a design review artifact. It captures a delivered adversarial verdict that the operator needs before spawning build tickets from PR #178. Landing it makes the review durable.
- **Conflict risk vs master:** None — single new file, no modification of existing files.
- **Lost if dropped:** The adversarial review verdict on the unified reconciliation gate design, including 2 revision items the operator must resolve. No code loss.

### feat/ticket-lifecycle-canary (TICKET-LIFECYCLE-CANARY)
- **What it does:** Fully hermetic control-plane ticket-lifecycle canary. Composes 3 existing detectors (gate-parity.sh, reconcile-merged.sh, stuck-ticket-loud.sh) into one mint→claim→build→land→retire dogfood test. Uses a throwaway board fixture — never touches live board or PR state.
- **Evidence:** Three-dot diff: 6 files. Two-dot restricted: 2 genuinely new files (+401 lines): `fleet/tests/ticket-lifecycle-canary.test.sh` (284 lines) and `fleet/board/PLANE-CANARY-REGISTRY.md` (117 lines). Remaining 4 files are base-sync no-ops. Active board ticket exists at `fleet/board/TICKET-LIFECYCLE-CANARY.md` with full spec.
- **Verdict:** **LAND** — clean, well-specified test infrastructure. Board ticket is active and complete. Hermetic design avoids blast radius.
- **Conflict risk vs master:** None — two new files only, no modifications to existing files.
- **Lost if dropped:** Control-plane lifecycle test coverage. The data-plane already has `flow-canary.test.sh` — this is the control-plane equivalent. Without it, ticket lifecycle defects (lanes-UNLAUNCHABLE, merged-NOT-retired, unclaimable-P0-SILENT) have no automated dogfood.

### feat/ordering-cost-primary (order-a — **PRODUCT** repo)
- **What it does:** Uses cost as primary sort key (removes latency-based sort from proxy_server.py fresh bucket). Adds slow-provider skip in failover loop (Option A: slow=failover, never strand). Fixes 3 pre-existing test failures (PYTHONPATH for subprocess spawns in test_boundary.py, test_routing_proxy.py; updated latency signal assertions). Full suite: 1497 passed.
- **Evidence:** Three-dot diff: 5 product files. Two-dot restricted: +144/-493. Branch has sat 20 days. Single commit: 16dbdc2.
- **Verdict:** **REWORK** — the intent is correct but the branch is stale. It forked from an old master point; the diff is almost entirely deletions of code master added since (493 lines deleted vs 144 added). The actual router changes are a minority of the diff. The branch needs a rebase onto current product master and conflict resolution before it can land.
- **Conflict risk vs master:** High. The product repo has moved substantially in 3 weeks. The branch's forwarder.py and proxy_server.py will likely have merge conflicts.
- **Lost if dropped:** Cost-primary ordering (Option A — the agreed design). Slow-provider failover logic. 3 pre-existing test fixes that make pytest pass without manual PYTHONPATH setup. All recoverable from the commit message and can be re-derived.

## Recommended landing ORDER

1. **REVIEW-RECONCILE-GATE-DESIGN** (land first — zero conflict, single new file, zero risk)
2. **TICKET-LIFECYCLE-CANARY** (land second — two new files, zero conflict, ready on master)
3. **FIXTURE-BYPASS-GATE** (land third — preflight.sh wiring should be checked; rig-ci-scope.sh conflicts with SUBSTRATE-GATE-V2 if both simplify the same file)
4. **SUBSTRATE-GATE-V2** (land fourth — shares rig-ci-scope.sh with FIXTURE-BYPASS-GATE; sequence one after the other to resolve)
5. **feat/ordering-cost-primary** needs rebase before landing — defer to operator on product repo priority.

## Anything I could not determine

- **GH PRs:** `gh` CLI not available on this rig. Could not determine if any branch has an open PR.
- **SUBSTRATE-GATE-V2 / FIXTURE-BYPASS-GATE board tickets:** Neither has a board file. These may have been spontaneous in-session builds without formal tickets. If the operator wants them tracked, they'll need board files created before landing.
- **ORDER-A gate status:** The product repo has its own gate mechanism; without `gh` I could not check if this branch would pass product CI/gates.
- **SUBSTRATE-GATE-V2 memory/ files:** The branch force-adds `fleet/memory/` files; unclear if corresponding `.gitignore` negations exist. Should verify preflight passes clean.
