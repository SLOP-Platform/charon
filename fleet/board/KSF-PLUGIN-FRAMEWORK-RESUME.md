repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: design-review
branch: eval/ksf-plugin-framework-resume
depends_on:
owns: fleet/state/KSF-PLUGIN-FRAMEWORK-RESUME.md, docs/review-log/KSF-PLUGIN-FRAMEWORK-RESUME.md
serial_justified: |
  One architectural question about one framework. Parallel lanes would each form a different
  picture of what KSF currently IS, which is the confusion this ticket exists to end.
substrate: N/A
substrate-novel: |
  Nothing external is adopted here - this is an audit of a framework WE built (Keystone,
  /home/stack/code/keystone) plus a decision about whether it should host adopted test tooling.
  No external tool can answer "what happened to our own framework and is it the right host".
  Adopt-first is enforced INSIDE the deliverable - if the answer is that KSF should be replaced by
  something off-the-shelf, that verdict is explicitly in scope and must not be softened.
execution: |
  Off-Claude, SG tab. AUDIT + DESIGN lane - measure and report. Wire nothing, land nothing,
  merge nothing. The stranded branch is TRIAGED here, not landed here.
source: |
  Operator, 2026-08-02 - "I had previously asked for a framework that all projects plug into not
  sure what happened to that." MEASURED THE SAME DAY - it became Keystone (KSF). Ticket
  KSF-LOAD-BEARING is archived + DONE, and its own text says its four preconditions are what make
  KSF "capable of gating ANYTHING outside itself". So the framework EXISTS and the operator does
  not know its status - that gap is the ticket.
note: |
  ## THE THREE QUESTIONS, IN ORDER
  ### Q1 — WHAT IS KSF TODAY, ACTUALLY?
  Not what the docs claim [[confirm-dont-trust-documentation]]. Establish by RUNNING -
    - Is it installable right now? Install it into a clean venv and report the exact outcome.
    - What does it actually DO - enumerate its gates, and for each say whether it EXECUTES
      anywhere (`tools/gates.json`, `gate_runner.CHECKS`, CI). A registered-but-dead gate emits a
      GREEN RECEIPT for an absent check - that exact defect is documented in this rig.
    - WHO PLUGS INTO IT TODAY? Count real consumers - charon product, charon-private rig,
      anything else. If the answer is ZERO, say so plainly. A framework nothing plugs into is a
      library, and calling it a framework is how it stayed invisible.
    - Relationship to `fleet/state/WORK-FRAMEWORK-WIRING-PLAN.md` and
      `WORK-FRAMEWORK-TOOL-SCAN.md` (whose verdict was ~0% adopt / ~100% wiring) - is that plan
      executed, partially executed, or abandoned? That scan PREDATES the adopt-first lens shift,
      so its "0% adopt" conclusion must be re-examined, not inherited.

  ### Q2 — THE STDLIB-ONLY COLLISION
  MEASURED 2026-08-02 - keystone `pyproject.toml:8` describes it as a "stdlib-only enforcement
  layer" and a `dependencies=[]` posture is enforced by `tools/check_arch.py` and
  `tools/check_boundary.py`. Adopting pytest-bdd or Hypothesis would be the FIRST dependency.
  A branch already removes the prohibition - `chore/remove-stdlib-only-prohibition` @ `ca7d046`
  ("chore: remove stdlib-only / dependencies=[] prohibition (adopt-first)"), 14 files,
  -215/+85, PUSHED WITH NO PR. It is one of 211 `pushed-no-pr` findings.
  Required output -
    - REVIEW that branch as a real PR. Does it remove the prohibition CLEANLY, or does it also
      remove protections we still want? -215 lines is a lot of deleted enforcement; say exactly
      what protection each deletion drops.
    - Is stdlib-only still defensible for the CORE with dependencies allowed in PLUGINS? That was
      the recorded architecture - stdlib CORE plus best-in-class PLUGINS. If that split still
      holds, adopting pytest-bdd in a PLUGIN may need NO prohibition removal at all, which would
      be the cheapest possible answer. Test that hypothesis explicitly.
    - Recommend LAND / LAND-WITH-CHANGES / CLOSE, with reasons.

  ### Q3 — IS KSF THE RIGHT HOST FOR A SHARED TEST FRAMEWORK?
  The operator wants ONE framework every project plugs into. Answer whether that should be KSF,
  or plain pytest configuration shared via a package, or something off-the-shelf. Consider -
    - What "plugging in" would concretely MEAN - a pytest plugin, a shared conftest, an installed
      package, a copied config? Name the mechanism, do not hand-wave "integration".
    - The multi-repo reality - charon (public product) and charon-private (rig) are separate
      repos with separate CI. How does a shared framework reach both WITHOUT a vendored copy that
      drifts? This is the actual hard part; treat it as such.
    - Whether adopting `pytest` + plugins directly, with a thin shared config package, beats
      maintaining KSF as a bespoke layer. Under adopt-first, "ours already exists" is NOT a
      reason to keep it, and sunk cost is not an argument [[no-rig-as-product-adopt-dont-handroll]].
accept: |
  DELIVERABLE `fleet/state/KSF-PLUGIN-FRAMEWORK-RESUME.md` containing -
  a. A one-paragraph plain answer to "what happened to the framework I asked for" - written for
     the OPERATOR, not for an engineer. This is the primary deliverable.
  b. Q1 - KSF's real current state, with the install result, the gate-execution table and the
     consumer COUNT. Every claim backed by a command.
  c. Q2 - a full review of `ca7d046` with a LAND / LAND-WITH-CHANGES / CLOSE recommendation, and
     an explicit answer on whether the CORE-stdlib / PLUGIN-deps split avoids the need for it.
  d. Q3 - a named hosting recommendation with the concrete plug-in mechanism and the multi-repo
     distribution answer.
  e. A RISK section - what breaks if we adopt, and what rots if we do not.
  f. If KSF should be retired or replaced, say so directly. That verdict is in scope.
scope: |
  Audit, review and written recommendation. Lands nothing, merges nothing, adds no dependency,
  does not modify Keystone. Tool-level BDD and Hypothesis verdicts belong to the other two lanes.

## Dependencies & Sequence

- **depends_on: none.** Reads both repos, keystone, and the stranded branch.
- Runs in PARALLEL with BDD-FRAMEWORK-EVAL and HYPOTHESIS-FAILOVER-EVAL. Disjoint owns.
- FEEDS BOTH - its Q2 answer determines whether either tool CAN be adopted, so its verdict is the
  gating one. If it finds the CORE/PLUGIN split removes the blocker, both other lanes get cheaper.
- Synthesised with the other two by the MANAGER into ONE recommendation to the operator.
