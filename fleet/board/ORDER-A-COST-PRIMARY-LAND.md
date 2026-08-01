repo: charon
tier: strong
difficulty: 3
priority: 1
work_class: routing
branch: feat/ordering-cost-primary
owns: src/charon/forwarder.py, src/charon/proxy_server.py, tests/test_boundary.py, tests/test_latency_signal.py, tests/test_routing_proxy.py
serial_justified: Rebase-and-land of a SINGLE existing commit (16dbdc2) whose cost-primary ordering +
  slow-failover change spans forwarder.py + proxy_server.py as one logical unit with its 3 tests;
  splitting it would fracture one coherent routing change.
depends_on: GW-CUTOVER-LIVE-WIRE, FORWARDER-COST-ORDER-FALLBACK
real-dep: FORWARDER-COST-ORDER-FALLBACK shared src/charon/forwarder.py — the cost-order fallback is the live P0 defect and lands first; order-a (latency/slow-failover) rebases onto it. GW-CUTOVER-LIVE-WIRE shared src/charon/forwarder.py surface — merge-order so the cost-primary
  ordering rebases onto the settled cutover forwarder.py rather than colliding; rebasing onto the
  later state is also SAFER (order-a must reconcile with live routing regardless).
source: scratchpad WORKTREE-TRIAGE-34.md SALVAGE (D1 triage, 2026-07-23); operator directive "salvage order-a"
note: |
  SALVAGE of real, WANTED work stranded in worktree order-a on branch feat/ordering-cost-primary
  (single commit 16dbdc2 "feat(ROUTER): Option A cost-primary ordering + slow failover + pre-existing
  test fixes", +49/-4 across forwarder.py/proxy_server.py + 3 tests). Confirmed NOT superseded: master
  still has the OLD latency-sort and no is_slow_provider slow-failover — this is the cost-primary
  ordering + slow-provider failover the operator has repeatedly wanted. [[charon-failover-bug-and-tier-fallback]]
accept: |
  - Rebase feat/ordering-cost-primary (16dbdc2) onto CURRENT origin/master (product moved ~30+ commits;
    resolve conflicts in forwarder.py/proxy_server.py against the live ordering/failover code). Do NOT
    rebuild from scratch — preserve/port the cost-primary ordering + slow-failover logic + its tests.
  - Product gate GREEN (charon.cli gate) + the 3 touched test files pass; the slow-failover path has a
    test proving a slow provider is failed over (latency-is-a-failure-class).
  - Open a PR; ADVERSARIAL REVIEW before merge (reviewer != builder) — routing/failover hot-path.
  - Reconcile with any ordering/failover changes that landed since 16dbdc2 (cost-primary must compose
    with funding_class ordering already live, not fight it).
scope: |
  Land the stranded cost-primary ordering + slow-failover work through normal review. After it lands,
  the order-a worktree is safe to reap (branch ref preserved). Product repo (native required-checks).
ds: |
  ## Dependencies & sequence
  No build prereq. Rebase-and-land of an existing branch. Verify cost-primary ordering does not
  regress the live funding_class_order (SSOT 1<3<2<4) before merge.
