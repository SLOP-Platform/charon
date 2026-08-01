repo: charon-private
tier: economy
priority: 0 # inherited: blocks a P0 ticket
difficulty: 2
work_class: ci-infra
branch: feat/repo-decl-central
depends_on: VERIFY-MERGED-REPO-AWARE
real-dep: VERIFY-MERGED-REPO-AWARE — that branch lands the canonical PRODUCT_REPO/PRODUCT_SLUG/
  FLEET_REPO/FLEET_SLUG declarations in fleet/_lib.sh (the half of this ticket that was designed).
  This ticket is the REMAINING half: migrating the hardcoded consumers. Building the consumer
  migration before the declarations exist would re-declare them a second time — the exact drift this
  ticket removes. Disjoint owns BY DESIGN (that branch owns _lib.sh; this ticket must NOT touch it).
owns: /home/stack/charon-private/fleet/handoff.sh, /home/stack/charon-private/fleet/retire-done.sh, /home/stack/charon-private/fleet/handoff-check.sh, /home/stack/charon-private/fleet/land-needs-push.sh
accept: |
  RE-OPENED 2026-07-18 — THE CODE NEVER LANDED. Read the note: field before scoping.

  SCOPE IS NOW THE CONSUMERS ONLY. Do NOT add the declarations to fleet/_lib.sh — branch
  `fix/verify-merged-repo-aware` lands PRODUCT_REPO / PRODUCT_SLUG / FLEET_REPO / FLEET_SLUG there
  (verified: that branch's diff touches fleet/_lib.sh, +92 lines). Re-adding them is a SECOND copy
  and recreates the drift class. Source them; never redeclare them.

  DO. Every rig tool that still HARDCODES the literal `/home/stack/code/charon` sources _lib.sh and
  uses PRODUCT_REPO / FLEET_REPO instead. VERIFIED remaining sites (re-grep before editing; line
  numbers drift):
    - fleet/handoff.sh
    - fleet/retire-done.sh
    - fleet/handoff-check.sh
    - fleet/land-needs-push.sh
  Each tool that reasons about "a repo" must state WHICH repo explicitly — no assumed cwd.

  FAIL-ON-REVERT (REQUIRED): a test that sets CHARON_PRODUCT_REPO to a temp path and asserts a
  consumer (retire-done / handoff-check) actually TARGETS that path, not the hardcoded default.
  Revert the consumer migration -> the consumer returns to the literal -> the test goes RED.
  Assert the RESOLVED path the consumer uses, not merely that it sources _lib.sh (sourcing a file
  proves nothing about which path the code then reads).

  GREEN-IS-NOT-PROOF: the rig suite is green RIGHT NOW with all four hardcodes live — nothing
  exercises the product/fleet boundary, so the suite CANNOT go red on a wrong-repo resolution. That
  is precisely how this ticket was previously closed against a PRODUCT-repo docs commit while zero
  code shipped. A green suite is zero evidence here.
scope: |
  ROOT CAUSE (found 2026-07-10, re-confirmed 2026-07-18): the product/fleet split is load-bearing but
  the coupling is implicit — the product path is re-declared/hardcoded across rig files with
  inconsistent names. This is the origin of the recurring "wrong-repo" bug class: the done-merge gate
  checked the PRODUCT repo for FLEET tickets (item-3 false reds); the fleet handoff gate runs
  PRODUCT-shaped pytest/ruff in the FLEET repo (F21/F24). Centralizing the declaration removes the
  class. The declarations are landing via VERIFY-MERGED-REPO-AWARE; this ticket converges the
  consumers. [[no-hardcoded-cross-boundary-paths]] [[product-vs-build-rig-boundary]]
  [[config-ssot-git-manifest]] [[confirm-dont-trust-documentation]]
ds: |
  ## Dependencies & sequence
  depends_on: VERIFY-MERGED-REPO-AWARE — real prereq, justified in the real-dep: field above. Land
    that branch FIRST, then migrate the consumers onto the declarations it introduces.
  boundary: RIG-ONLY ([[product-vs-build-rig-boundary]]). No product-repo file is edited by this
    ticket. Do NOT touch fleet/_lib.sh — its single writer is VERIFY-MERGED-REPO-AWARE.
  single-writer WARNING (fleet/handoff.sh): GH-SEAM-CHOKEPOINT and FOREMAN-MULTI-TRIGGER also edit
    fleet/handoff.sh, but declare it in REPO-RELATIVE form while this ticket declares it ABSOLUTE —
    so validate_board's exact-string owns-collision check CANNOT see the overlap. The collision is
    REAL regardless. Manager: sequence this ticket's handoff.sh edit after those two land, or hand
    the whole handoff.sh surface to one tab. Touch the file ONCE
    ([[optimize-execution-wallclock-tokens]]).
  not-covered-by (checked, genuinely disjoint): SSOT-DRIFT-GATE COMPOSES per-fact SSOTs via
    SSOT-REGISTRY.tsv and its own reuse: field names REPO-DECL-CENTRAL as the owner of the repo-path
    fact — it ENFORCES, it does not own. REPO-MAP-CONVERGE owns the OTHER consumer set
    (validate_board.sh / preflight.sh / checks/base-integrity.sh) and is sequenced after this.
  concurrency: blocked until VERIFY-MERGED-REPO-AWARE lands; then a single-writer pass over 4 rig
    scripts. Do NOT decompose per-file — that recreates the multi-writer defect being fixed.
  wave: rig board correction 2026-07-18.
  repo: charon-private (rig).
note: |
  RE-OPENED 2026-07-18 — PHANTOM MERGE CORRECTED. This ticket was marked done on 2026-07-16 with the
  marker `merged:c44e7bda0ee835afa01c7a9e876e5df3e2a7162d`. THE CODE NEVER LANDED:
    - That sha DOES NOT EXIST in the rig repo (Nnyan/charon-private) — `git cat-file -t` fails on it.
    - It resolves in the PRODUCT repo (SLOP-Platform/charon) as "Merge pull request #163 from
      SLOP-Platform/feat/repo-decl-central", whose ENTIRE diffstat is
      `docs/review-log/REPO-DECL-CENTRAL.md | 34 ++++` — ONE docs file, 34 insertions, DOCS-ONLY.
    - Zero PRODUCT_REPO / FLEET_REPO declarations and zero consumer migrations shipped anywhere.
  ROOT CAUSE of the false close: this is a RIG ticket that carried no `repo:` field, so done.sh's
  verify_merged defaulted to the PRODUCT repo and accepted a PRODUCT commit as proof for RIG work.
  The `repo: charon-private` field above is now set. The general fix is ticketed as
  REPO-FIELD-REQUIRED; the done.sh/_lib.sh repo-awareness fix is VERIFY-MERGED-REPO-AWARE.
  SCOPE CHANGE ON RE-OPEN: the canonical PRODUCT_REPO/PRODUCT_SLUG/FLEET_REPO/FLEET_SLUG declarations
  are being landed by branch `fix/verify-merged-repo-aware`, so fleet/_lib.sh has been REMOVED from
  this ticket's owns. Whoever picks this up scopes it to the REMAINING consumers only — the hardcoded
  /home/stack/code/charon sites in handoff.sh, retire-done.sh, handoff-check.sh, land-needs-push.sh —
  and does NOT redo the _lib.sh decls.
  MERGE-CONFLICT HEADS-UP: branch fix/verify-merged-repo-aware edits
  fleet/board/archive/REPO-DECL-CENTRAL.md (+1 line); this file has been moved back to
  fleet/board/REPO-DECL-CENTRAL.md, so that hunk will need resolving when the branch lands.
