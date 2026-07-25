repo: charon
tier: strong
difficulty: 3
work_class: money-path
priority: 1
branch: fix/ruff-security-rules
depends_on: GW-CUTOVER-LIVE-WIRE
dep-kind: build
real-dep: GW-CUTOVER-LIVE-WIRE owns pyproject.toml (alongside forwarder.py, proxy_server.py,
  tests/test_gw_cutover_live_wire.py) and this ticket must edit the SAME file to enable the ruff rule
  sets. Single-writer sequencing on a shared owned file — rebase onto its merge, never co-write.
  Verified 2026-07-24: GW-CUTOVER-LIVE-WIRE is the ONLY other live claimant of pyproject.toml.
owns: pyproject.toml
owns-provisional: |
  `owns:` DELIBERATELY LISTS ONLY pyproject.toml, AND THAT UNDERSTATES THE BRANCH. The ticket was
  requested while the fix set was still open; by the time it was written the sub had COMMITTED
  f4605c3 ("adopt ruff bandit (S) + blind-except (BLE) rulesets; triage all 85 findings"), which
  touches 32 FILES (+158/-77): pyproject.toml, 27 files under src/charon/, and 4 under tools/.
  Declaring all 32 in `owns:` would claim files that other LIVE tickets already own (see ds: for the
  enumerated collisions) and would red the board's owns-collision check. That is a REAL CONFLICT to
  resolve at landing, NOT a bookkeeping detail to paper over by widening this field.
  THE CLAIMANT MUST, BEFORE LANDING: reconcile the touched-file list against the owners named in ds:,
  and either (a) rebase behind them, or (b) split the pure-lint hunks in contended files out of this
  branch. Do not widen `owns:` to 32 paths to make validate_board quiet — that converts a detected
  collision into a silent one [[never-ignore-preexisting-issues]].
priority-why: |
  P:1 — security is a merge-blocking RATCHET on this rig, and this is not a hypothetical lint upgrade:
  the findings include a live `shell=True` and a bind-all-interfaces, i.e. real exposure that ships
  today. It is P:1 rather than P:0 because it is dep-blocked behind GW-CUTOVER-LIVE-WIRE for
  single-writer sequencing on pyproject.toml, so it CANNOT be started until that lands — stamping P:0 on
  work that is structurally unstartable ranks it above 38 startable P:0s and buys nothing. It is not
  P:2/P:4 because a security checker reporting CLEAN over a `shell=True` is a FALSE GREEN, which this
  rig treats as worse than a known red [[security-is-a-ratchet-gate]] [[gates-must-actually-run]].
source: 2026-07-24 — ticket requested while a sub was still finishing the work, so it could commit
  WITHOUT WORK_LEASE_BYPASS=1. By the time the ticket was written the sub had ALREADY COMMITTED
  f4605c3 on branch fix/ruff-security-rules. Same root cause as the other bypasses today: no ticket
  mapped the branch. See TICKET-MAP-GATE, which fixes the class at DISPATCH.
count-discrepancy: |
  The work was requested as "72 findings"; the landed commit f4605c3 says "triage all 85 findings".
  RECORDED, NOT RECONCILED — I did not re-run the linter, so I do not know whether the delta is scope
  growth, a different rule selection, or a miscount. The reviewer must confirm the real number against
  a live run before accepting "all findings triaged" [[document-model-self-report-lies]]
  [[confirm-dont-trust-documentation]]. Either figure still contains the two named real exposures.
note: |
  THE FINDING IS A FALSE GREEN, NOT A MISSING FEATURE. Our hand-rolled tools/check_security.py — 330
  lines — reports CLEAN. Enabling ruff's `S` (flake8-bandit) and `BLE` (blind-except) rule sets over the
  same tree surfaces 72 FINDINGS, including:
    - a `shell=True` subprocess invocation, and
    - a bind-all-interfaces listener.
  Both are exactly what a security check exists to catch, and the owned checker walks past them. This is
  the same shape as the four non-enforcing gates found today: the gate RAN, it was GREEN, and it was
  measuring nothing [[gates-must-actually-run]].

  THE CLASS FIX IS THE ADOPTION, NOT THE 72 FIXES. ruff is already the project's linter; `S`+`BLE` are
  rule sets it already ships. Turning them on replaces 330 hand-rolled lines with configuration
  [[audit-hand-rolled-vs-best-in-class]] [[adopt-substrate-build-only-novel-slice]]. The 72 findings are
  the backlog the adoption exposes, not the deliverable.

  DISPOSITION OF tools/check_security.py IS PART OF THIS TICKET AND MUST BE EXPLICIT: either it is
  RETIRED (because ruff subsumes it) or the specific checks it makes that ruff does NOT are named and
  kept. Leaving a 330-line checker in the tree that demonstrably reports clean over a `shell=True`, next
  to a ruff config that catches it, is how the false green comes back [[harmless-cruft-bites]].
accept: |
  - `pyproject.toml` enables ruff rule sets `S` and `BLE`, and the security lint is a BLOCKING gate
    (non-zero exit), not an advisory print. A gate that cannot fail the merge is not a ratchet.
  - EVERY one of the 72 findings is DISPOSITIONED — FIX (preferred) or an inline `# noqa: <RULE>` with a
    ONE-LINE WRITTEN JUSTIFICATION. A blanket file-level or repo-level suppression is REFUSED; so is a
    bare `# noqa` with no rule id and no reason. Same standard already applied to
    BANDIT-PREEXISTING-FINDINGS — keep the two consistent, and check for overlap before re-fixing a
    finding that ticket already dispositioned.
  - THE TWO NAMED EXPOSURES ARE FIXED, NOT SUPPRESSED: the `shell=True` invocation and the
    bind-all-interfaces listener. A `# noqa` on either fails this ticket.
  - `tools/check_security.py` is explicitly RETIRED or its non-overlapping checks are named and kept
    (see note:). Silence on this point fails the ticket.
  - RED-PROOF BY EXECUTION, non-vacuous: introduce a fresh `shell=True` in a scratch file -> the gate
    exits NON-ZERO naming the rule; remove it -> exit 0. Report BOTH exit codes. A run that examines
    ZERO files is RED, never a silent pass [[gates-must-actually-run]].
  - `charon.cli gate` GREEN, no new REDs.
  - ADVERSARIAL REVIEW (reviewer != builder) — security default.
scope: |
  Enable ruff `S`+`BLE` as a blocking gate in pyproject.toml, disposition the 72 findings it surfaces
  (fix, or noqa with a written reason), fix the two named real exposures, and settle the fate of the
  hand-rolled tools/check_security.py that reports clean over them. Configuration + dispositions, not a
  new security tool [[no-stiff-single-provider-tools]] does not apply; this is adopt-over-hand-roll.
serial_justified: |
  One rule-set enablement and its finding-disposition pass are a single unit: the findings do not exist
  until the rules are on, and turning the rules on without dispositioning them lands a permanently-red
  gate that the next session switches off. Splitting them ships either an unenforced config or an
  un-landable red.
ds: |
  ## Dependencies & sequence
  - depends_on: GW-CUTOVER-LIVE-WIRE — HARD, dep-kind build. See real-dep: shared single-owner of
    pyproject.toml. Rebase onto its merge; do NOT run as a concurrent second writer of that file
    [[one-checkout-one-agent]].
  - LAND ORDER: LITELLM-ORDER-PRECALL -> GW-CUTOVER-LIVE-WIRE -> this ticket. The security ratchet
    sitting third is a deliberate single-writer call, not a de-prioritisation of security; the
    alternative is two concurrent writers of pyproject.toml, which is the collision class this board
    exists to prevent.
  - ENUMERATED OWNS COLLISIONS ON THE COMMITTED BRANCH (f4605c3, verified 2026-07-24). Four of the 32
    touched files are ALREADY OWNED by live tickets. Each must be rebased behind, or the lint hunk
    split out — this branch must not be a concurrent second writer of any of them:
      * src/charon/forwarder.py    <- ORDER-A-COST-PRIMARY-LAND, FT-WIRE-QUOTA, GW-CUTOVER-LIVE-WIRE
      * src/charon/proxy_server.py <- GW-CUTOVER-LIVE-WIRE, ORDER-A-COST-PRIMARY-LAND
      * src/charon/gateway.py      <- FIX-PROVIDER-KEY-EXFIL, WIRE-GRADING-PRIOR-LIVE,
                                      GATEWAY-NONTOKEN-METERING, FT-WIRE-QUOTA
      * src/charon/api.py          <- API-DECOMPOSE-CYCLE-FIX
    The declared `depends_on: GW-CUTOVER-LIVE-WIRE` covers pyproject.toml + forwarder.py +
    proxy_server.py. The gateway.py and api.py owners are NOT yet sequenced — resolve before landing;
    gateway.py alone has FOUR live claimants and is the worst of them.
  - CHECK FOR OVERLAP BEFORE FIXING: BANDIT-PREEXISTING-FINDINGS (rig repo) dispositions bandit findings
    under the same fix-or-justified-noqa standard. Different repo, so no owns collision, but the same
    finding classes — reuse its dispositions rather than re-deriving them.
  - `owns:` IS DELIBERATELY NARROW — see owns-provisional:. Reconcile, do not widen to silence the gate.
  - repo: charon (PRODUCT). No rig leak [[product-vs-build-rig-boundary]].
