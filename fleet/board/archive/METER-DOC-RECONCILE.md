repo: charon
tier: economy
difficulty: 2
work_class: money-path
branch: feat/meter-doc-reconcile
depends_on:
owns: src/charon/proxy.py, tests/test_meter_doc_reconcile.py
accept: |
  ADVERSARIAL REVIEW REQUIRED (money-path / trust): this ticket changes what the codebase CLAIMS about
  the per-provider cost meter. A wrong claim here is what produced a standing false belief that the
  meter is inert — the reviewer must confirm every retained sentence against the cited call sites, not
  against the docstring it replaces.

  PROBLEM. src/charon/proxy.py's money-path docstrings assert the per-(model,provider) cost ledger is
  NOT wired. The code says otherwise. Both facts VERIFIED 2026-07-16 on product master — do NOT
  re-research, these line numbers are confirmed:
    - LEDGER IS WRITTEN: `grep -c 'provider=route.label' src/charon/forwarder.py` -> **8** sites
      (581, 629, 655, 791, 797, 845, 869, 898).
    - LEDGER IS READ (3 live readers): forwarder.py:532 (`live = observer.all_model_provider_costs()`
      — cost-rank routing), gateway.py:477 (`costs = server.observer.all_model_provider_costs()`),
      balance.py:534 (docstring reference). Definition at proxy.py:591.
    - DOCS LIE: `grep -cE 'Wave-2|Wave 2' src/charon/proxy.py` -> **12** lines (harvest said 10; 12 is
      the verified count today). Verbatim falsehoods include proxy.py:314 and :507 ("this ledger is
      EMPTY under real traffic today") and :566/:569 ("WAVE-2 DEFERRED: this ledger WILL be read by
      Wave-2 cost-rank routing ... deferred to Wave 2"). forwarder.py:532 reads it NOW. Both claims are
      FALSE.

  DO. Correct the ~5 stale docstring blocks in proxy.py (lines ~311, 314, 356, 360, 504, 507, 566, 569,
  579, 586 + the 2 remaining Wave-2 hits) to describe ACTUAL wiring: the ledger is populated by
  forwarder.py's 8 metering sites and consumed by cost-rank routing at forwarder.py:532 and by
  gateway.py:477. Cite the reader file:line IN the docstring so the next drift is self-evident. Do NOT
  change any behavior — this is a docs-truth ticket on a money-path file. Zero functional edits.

  SECOND ACTION (in text only — DO NOT RENAME/MOVE ANY FILE): fleet/board/METER-MODEL-PROVIDER.md.parked
  is a Wave-2 BUILD ticket for work that has ALREADY SHIPPED (the 8 write sites + 3 readers above). Its
  premise is dead. Record that finding in this ticket's PR body + a one-line `note:` recommendation for
  the manager to retire-or-rescope it. The manager owns the disposition; the droid does NOT edit,
  rename, or park/unpark that file.

  FAIL-ON-REVERT (add tests/test_meter_doc_reconcile.py — BOTH tests required):
    (1) BEHAVIOR (proves the docs' claim is false): drive a forward through the meter and assert
        `all_model_provider_costs()` is NON-EMPTY and keyed by (model, provider). Revert the metering
        wiring -> ledger empty -> RED. This is the executable refutation of "EMPTY under real traffic".
    (2) DOC-DRIFT GUARD (proves the fix itself): assert src/charon/proxy.py contains NONE of the
        falsified strings ("EMPTY under real traffic", "WAVE-2 DEFERRED", "deferred to Wave 2") FOR AS
        LONG AS `all_model_provider_costs` has >=1 live reader (assert the reader count >0 in the same
        test, so the guard can never be satisfied by deleting the readers). Re-introduce the stale
        docstring -> RED. Without this test the docs silently re-rot.

  GREEN-IS-NOT-PROOF (explicit): the ENTIRE existing product suite passes TODAY while these docstrings
  are FALSE — docstrings are never executed, so no existing test can ever go red on a doc lie. A green
  run proves NOTHING about this ticket. The meter's own existing tests additionally use fixtures/mocked
  routes, so they pass whether or not the real forwarder path meters. The ONLY acceptable evidence is
  test (1) failing when metering is reverted and test (2) failing when the stale text returns. A
  reviewer who accepts "suite green" has not reviewed this ticket.
scope: |
  Money-path docs-truth reconcile. src/charon/proxy.py asserts the per-(model,provider) cost ledger is
  Wave-2-deferred and "EMPTY under real traffic"; forwarder.py meters into it at 8 sites and reads it at
  :532 for cost-rank routing. This stale doc is the documented origin of the standing "meter is inert"
  belief and of the still-parked METER-MODEL-PROVIDER Wave-2 build ticket for already-shipped work.
  Fix the text, lock it with a doc-drift guard, and hand the .parked disposition to the manager.
  [[charon-meter-inert]] [[confirm-dont-trust-documentation]] [[document-model-self-report-lies]]
  [[always-fix-catalog-mismatches]]
ds: |
  ## Dependencies & sequence
  depends_on: (none) — src/charon/proxy.py is UNOWNED by any live ticket (board-verified 2026-07-16:
    GRACEFUL-DEGRADE owns router.py/failover.py/balance.py; PRICE-REFRESHER owns
    routing_policy/price_refresher.py; METER-KWH-USD-FIX owns gateway.py; ADR0016-DEPLOY-PRICED-
    COMPLETENESS owns routing_policy/cost_rank.py. None own proxy.py).
  concurrency: RUNS NOW, zero-dep. Docs-only on proxy.py + one NEW test file -> parallel-safe with every
    live ticket. Reads (does not edit) forwarder.py/gateway.py, so no owns overlap with their owners.
  reads-only (no owns claim, no build dep): src/charon/forwarder.py (8 write sites + reader :532),
    src/charon/gateway.py:477, src/charon/balance.py:534 — cited as evidence, never modified.
  manager-action (not droid work): retire-or-rescope fleet/board/METER-MODEL-PROVIDER.md.parked once
    this lands — its Wave-2 premise is dead. Reported in the PR body; no file rename by the droid.
  wave: economy refill 2026-07-16. Do FIRST — it is one of three zero-dep economy tickets feeding an
    idle economy tab.
  repo: charon (product).
note: Created 2026-07-16 from fleet/session-notes/2026-07-16-evidence/audit-harvest.md item 4. Zero-dep,
  economy, READY NOW. Docs-truth on a money-path file — ADVERSARIAL REVIEW REQUIRED.
  MANAGER FOLLOW-UP: METER-MODEL-PROVIDER.md.parked builds already-shipped Wave-2 work — retire or rescope.
</content>
</invoke>
