repo: charon
tier: strong
priority: 2
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
  ### EXTENDED 2026-07-19 — SR-8 IS THE SAME SIX MODULES, AND ITS "DONE" IS A FALSE RECEIPT.
  This ticket ABSORBS the SR-8 wiring work; no separate SR-8 ticket is to be created. Two
  independent passes reached these same six modules from opposite directions (this ticket from the
  detector's blindspot, SR-8 from an operator-approved "WIRE all 6 modules" scope), which is
  corroboration, not duplication.
  SR-8 WAS MARKED DONE AND NEVER BUILT — a second REPO-DECL-CENTRAL [[gates-must-actually-run]]
  [[document-model-self-report-lies]]. Rig commit 50af47c ("SR-8 found ABSENT") still names SR-8 as
  the open wire-or-remove decision. SR-8's done-marker is therefore a FALSE RECEIPT and the ticket
  must RETURN TO LIVE STATUS. Do NOT delete the marker by hand: marker integrity is owned by
  MARKER-PROOF-MECHANIZE (write-time proof refusal + fleet/checks/marker-proof.sh), which is the
  MECHANISM that must retire it. SR-8's marker is a concrete fixture case for that ticket.

  RE-VERIFIED ON PRODUCT MASTER ebaec2e, 2026-07-19 (supersedes the 2026-07-16 line numbers below,
  which have DRIFTED — the construction site moved into a module-spec table):
    - constructor kwargs: src/charon/proxy_server.py:490-500 (observability:493,
      request_inspector:496, session_affinity:497, speculative_executor:498, consensus_router:499,
      virtual_key_manager:500).
    - construction: src/charon/gateway.py:81-102, via the `_MODULE_SPECS` lambda table
      (Observability:81, RequestInspector:89, SessionAffinity:91, SpeculativeExecutor:93,
      ConsensusRouter:97, VirtualKeyManager:102) — NOT gateway.py:258-296 as first recorded.
    - storage: src/charon/proxy_server.py:~575-586 via `self.modules.get("<name>")`.
    - INVOCATION SITES: still ZERO for all six. Total refs across src/charon/ are 5 each
      (7 for Observability: +types.py:200 ObsTarget docstring) and EVERY ref is
      define / import / kwarg / factory-register — none is a call. The only `self.<attr>`-shaped
      hit outside those lines is gateway.py:675 `if cfg.request_inspector is not None:` — a CONFIG
      presence test, not an invocation of the instance.
    - DETECTOR STILL BLIND: `python3 tools/check_inert_code.py` -> `check_inert_code: OK`, rc=0,
      65 dead symbols all dispositioned, and NOT ONE of the six appears among them.

  SCOPE SPLIT — (a) IS NOT OPTIONAL, (b) IS AN OPERATOR DECISION:
    (a) THE DETECTOR FIX IS THE CLASS FIX AND IS MANDATORY. It ships in this ticket regardless of
        what happens to the six modules. Fixing six modules by hand leaves the detector blind to
        the seventh.
    (b) WIRE-OR-REMOVE IS PER-MODULE AND IS THE OPERATOR'S CALL. The ticket must SURFACE the
        choice for each of the six with its rationale (what wiring would cost, what removing would
        lose, what the module was for) and RECORD the operator's answer. It must NOT silently
        pick, and it must not treat the pre-existing WIRING-AUDIT-MATRIX map as the decision
        already made — that map is INPUT to the decision, not the decision
        [[adversarial-review-must-not-silently-override-operator]]. A disposition written without
        a recorded operator answer fails this ticket.

  ANTI-OVER-BLOCK IS AS BINDING AS THE DETECTION (see FAIL-ON-REVERT (2)). The fix must flag a
  constructed-but-never-invoked instance AND must NOT flag a genuinely-used one. A detector that
  reds on live code gets suppressed into uselessness — which is how it went blind originally.

  WARNING — `check_inert_code` RUNNING GREEN TODAY IS EXACTLY THE FALSE-GREEN CLASS. Its OK is the
  DEFECT under repair, not evidence of health. A test that still passes with the detector fix
  REMOVED is WORTHLESS here: it is measuring the blindness, not the sight. Reviewer: physically
  revert the detector diff and confirm test (1) goes RED before accepting.

  --- original 2026-07-16 body follows ---
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
        EXTENDED 2026-07-19: each of the 6 entries must ALSO carry a non-empty recorded rationale
        for its wire|retire choice (the operator's answer per scope-split (b)). An entry with an
        empty/absent rationale -> RED. This is what stops the disposition pass from silently
        deciding what is an operator call.

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
note: EXTENDED 2026-07-19 — absorbed the SR-8 wiring scope (same six modules, reached
  independently) rather than boarding a duplicate ticket. SR-8's done-marker is a false receipt;
  SR-8 returns to live status and MARKER-PROOF-MECHANIZE is the mechanism that retires the marker
  (do not hand-delete). Evidence re-verified on product master ebaec2e; construct-site line numbers
  corrected (gateway.py:81-102 `_MODULE_SPECS`, not :258-296). Detector still GREEN with all six
  inert. Scope is now explicitly (a) MANDATORY detector class-fix + (b) per-module wire-or-remove
  surfaced as an OPERATOR decision with recorded rationale.
  Created 2026-07-16 from fleet/session-notes/2026-07-16-evidence/audit-harvest.md item 2
  (WIRING-AUDIT-MATRIX rows 9-14). Dep-gated behind CAPABILITY-ACTUALS-DEADREF-CLEANUP (hard collision
  on both owned tools/ files). Detector fix is the leverage — it repairs WORK-GATE-UNIVERSAL Gate B.
</content>
</invoke>
