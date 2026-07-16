repo: charon
tier: strong
difficulty: 4
work_class: ci-infra
branch: feat/inert-instance-detect
depends_on: CAPABILITY-ACTUALS-DEADREF-CLEANUP
owns: tools/check_inert_code.py, tools/inert-code-disposition.json, tests/test_inert_instance_detect.py
serial_justified: check_inert_code.py and inert-code-disposition.json are one detector + its own schema
  unit, not two independent surfaces — the detector's classification logic is written against the
  disposition file's exact shape, so two concurrent writers would leave the detector and the
  disposition disagreeing on what an entry means. Same checker+its-own-data-file pairing already
  accepted on COVERAGE-META-GATE (rule-coverage.sh + RULE-REGISTRY.tsv). The disposition pass is
  meaningless until the detector can SEE the instance-inert pattern, so the two cannot be built in
  parallel — they are strictly sequential halves of one change.
accept: |
  PROBLEM (the detector is GREEN and BLIND — 6 live examples already in the tree). Six gateway modules
  are constructed and stored but NEVER INVOKED. VERIFIED on product master 2026-07-16 — do NOT
  re-research:
    RequestInspector, SessionAffinity, Observability, SpeculativeExecutor, ConsensusRouter,
    VirtualKeyManager = **0 invocation sites each**. All six are constructed at gateway.py:258-296 via
    `_module_inst`, stored on GatewayProxyServer (proxy_server.py:559-566), and are never reached from
    `_handle()` -> `forward_with_failover()`.
  DETECTOR BLINDSPOT CONFIRMED: `python3 tools/check_inert_code.py` -> **`check_inert_code: OK`** (GREEN)
  and NONE of the six appear in tools/inert-code-disposition.json. The detector tracks SYMBOL
  reachability (import/construct), so construct-and-store LOOKS reachable. Each module has 5-7 textual
  refs — all of them import/construct/store, none an invocation. The detector cannot see
  "constructed-and-stored-but-never-INVOKED".

  WHY IT MATTERS (this is the leverage, not the 6 modules): WORK-GATE-UNIVERSAL's **Gate B** ("no
  inert/unwired code ships ... run tools/check_inert_code.py + graphify wiring-gap check; REFUSE merge
  if not FULLY WIRED") is built ON this detector. Gate B ships GREEN-BUT-BLIND unless the detector
  learns this pattern — i.e. the universal work gate would CERTIFY INERT CODE AS WIRED. Fixing the
  detector fixes the gate for every future ticket; wiring the 6 modules one-by-one does not.
  [[gates-must-actually-run]]: verify the gate EXECUTED and can actually FAIL, not that CI is green.

  DO (ONE detector fix + ONE disposition pass >> 6 per-module wiring tickets):
    (a) Teach tools/check_inert_code.py the INSTANCE-INERT pattern: a symbol that is constructed and/or
        stored on an object but has NO call/attribute-invocation reachable from an entrypoint is INERT,
        even though its constructor is reachable. Distinguish construct/store from INVOKE — that
        distinction is the entire ticket.
    (b) DISPOSITION each of the 6 as wire|retire in tools/inert-code-disposition.json. REUSE, do not
        re-derive: fleet/state/WIRING-AUDIT-MATRIX.md's "INERT-to-WIRED Wiring Map" already specifies
        the ONE intervention per module. Do not invent a 7th plan.
    (c) Do NOT wire the 6 modules in this ticket and do NOT edit gateway.py / proxy_server.py — they are
        not owned here. This ticket makes the BLINDNESS visible and dispositioned; the wiring/retirement
        is downstream work the disposition file schedules.
    (d) The detector must stay quiet on legitimate construct-then-store-then-invoke-later patterns —
        a detector that cries wolf gets disposition-suppressed into uselessness, which is how it went
        blind in the first place.

  FAIL-ON-REVERT (tests/test_inert_instance_detect.py — REQUIRED, all three):
    (1) THE CORE ASSERTION: feed the detector a FIXTURE module that is constructed + stored on an object
        but never invoked -> detector RED. Add a real invocation -> GREEN. Revert the detector change ->
        the fixture stops failing -> the test fails. This is the one test that proves the blindspot is
        closed.
    (2) NO FALSE POSITIVE: a fixture constructed, stored, AND later invoked -> GREEN. Guards (d).
    (3) DISPOSITION IS HONEST: assert every one of the 6 named modules is present in
        inert-code-disposition.json with an explicit wire|retire disposition. Silently dropping one ->
        RED. Prevents "fixing" the detector by suppressing its findings.

  GREEN-IS-NOT-PROOF (explicit, and it is the literal subject of this ticket): `check_inert_code: OK`
  is GREEN TODAY with 6 provably-inert modules in the tree. The detector's own green output is the
  DEFECT, not evidence. The full product suite is likewise green, because the 6 modules are constructed
  (so imports resolve) and never invoked (so nothing can break). Green therefore proves nothing here —
  it is exactly the false signal being fixed. This session already shipped 19/19 and 40/40 green PRs
  while the real path was broken because every test used fixtures; note the trap is INVERTED here:
  fixtures are CORRECT for test (1) (you must synthesize an inert module to prove the detector fires),
  but the fixture must drive the REAL detector entrypoint, not a re-implementation of its logic inside
  the test. Reviewer: confirm test (1) actually goes red when the detector diff is reverted, and that
  no module was dispositioned as "keep/false-positive" without a written justification.
scope: |
  Teach tools/check_inert_code.py the construct-and-store-but-never-INVOKED pattern, and disposition the
  6 known-inert gateway modules (RequestInspector, SessionAffinity, Observability, SpeculativeExecutor,
  ConsensusRouter, VirtualKeyManager — 0 invocation sites each) as wire|retire using the wiring map that
  already exists in WIRING-AUDIT-MATRIX.md. The detector currently reports OK while all 6 sit inert,
  which means WORK-GATE-UNIVERSAL's Gate B would certify inert code as fully wired. One detector fix +
  one disposition pass, not 6 wiring tickets.
  [[gates-must-actually-run]] [[reviews-use-our-own-tools]] [[decomposed-by-design-not-reactive]]
  [[confirm-dont-trust-documentation]]
ds: |
  ## Dependencies & sequence
  depends_on: CAPABILITY-ACTUALS-DEADREF-CLEANUP — HARD owns-collision, must land first. It already owns
    tools/check_inert_code.py + tools/inert-code-disposition.json (plus src/charon/decompose_sizing.py).
    Two concurrent writers on a detector + its own disposition schema is the exact
    checker-and-its-data-file pair that must never be split across simultaneous claims. It is currently
    IN REVIEW (state/submitted), so this ticket becomes claimable as the manager lands it. Shared owns =
    the dep is self-evidently real (validate_board's WCI check treats overlapping owns as a plausible
    dep and does not require a real-dep marker).
  serial-note: see the top-level `serial_justified:` field — detector + its own schema are one unit.
  unblocks (why this is high-leverage, NOT a build dep either direction): WORK-GATE-UNIVERSAL's Gate B
    consumes this detector. Gate B is only as good as check_inert_code.py, and ships green-but-blind
    until this lands. WORK-GATE-UNIVERSAL owns fleet/checks/work-gate.sh + hooks + its test (disjoint
    files, rig repo) — no owns overlap, no edit to it here, so no dep edge in either direction.
  reads-only (no owns claim, no edit): src/charon/gateway.py:258-296, src/charon/proxy_server.py:559-566
    (the 6 construct/store sites — cited as evidence), fleet/state/WIRING-AUDIT-MATRIX.md (reuse its
    existing INERT-to-WIRED map rather than re-deriving one).
  out-of-scope (deliberately): actually wiring or retiring the 6 modules. This ticket dispositions them;
    the interventions are downstream tickets the manager boards from the disposition file.
  wave: strong refill 2026-07-16. Frontier may claim down.
  repo: charon (product).
note: Created 2026-07-16 from fleet/session-notes/2026-07-16-evidence/audit-harvest.md item 2
  (WIRING-AUDIT-MATRIX rows 9-14). Dep-gated behind CAPABILITY-ACTUALS-DEADREF-CLEANUP (hard collision
  on both owned tools/ files). Detector fix is the leverage — it repairs WORK-GATE-UNIVERSAL Gate B.
</content>
</invoke>
