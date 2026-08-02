repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: ci-infra
branch: fix/preflight-late-leg-starvation
depends_on:
owns: fleet/state/PREFLIGHT-LATE-LEG-STARVATION.md, docs/review-log/PREFLIGHT-LATE-LEG-STARVATION.md
serial_justified: |
  One dispatch order in one file. There is nothing to parallelise and two tabs would reorder the
  same list against each other.
substrate: N/A
substrate-novel: |
  No tool adopted or built. Every detector already exists and is already dispatched; the defect
  is purely that an early noisy leg starves the later ones of wall-clock and of the operator's
  attention. The novel slice is ordering and output discipline.
accept: |
  MEASURED 2026-08-02: `bash fleet/preflight.sh` emits HUNDREDS of reconcile-merged AMBIGUOUS /
  UNRESOLVABLE lines. `detect_stranded_work` — which prints the stranded-work-cadence verdict, the
  gate for the work-loss class — is dispatched at line 884, AFTER that flood. A 200s-capped run
  never reached it at all; the operator's uncapped run surfaced the line only after a long wait
  and a screen of noise.
  Detectors after the flood, all effectively unread: detect_stranded_work, detect_cg_drift,
  detect_gateway_token_drift, detect_config_drift, detect_service_watchdog, detect_fixture_bypass,
  detect_gate_integrity.
  A check nobody reaches is a check nobody has, which is the built-but-inert class wearing a
  different hat.
  Done contract:
  1. Cap or summarise repeated reconcile-merged findings (they are one CLASS, not N findings) —
     print the count and the distinct shapes, not every row.
  2. Guarantee the verdict lines are reachable: emit a compact SUMMARY of every leg's verdict at
     the END regardless of upstream volume, so no leg can be starved by another's output.
  3. Fail-on-revert: with the fix reverted, a run capped at 200s must NOT reach the cadence
     verdict; with it, it must.

## Dependencies & Sequence

P1. Depends on nothing, but is the natural COMPANION to OWNS-OVERLAP-DISAMBIGUATE: that ticket
removes the CAUSE of the flood, this one ensures no future noisy leg can starve the late ones
again. Land either order; landing both is what makes preflight trustworthy.

## MEASURED BASELINE + ADVERSARIAL CORRECTIONS 2026-08-02

A live run was measured, then the proposed remedies were adversarially reviewed and several were
REJECTED. Both halves are recorded so the next session inherits the evidence AND the traps.

MEASURED (a full `bash fleet/preflight.sh` run):
  - **1105 lines, 67 functions, 13 detect legs**
  - **699 output lines conveying 6 verdicts** (`clean`/`WARN`/`RED`) — signal-to-noise **0.86%**
  - **`reconcile-merged` alone = 175 lines, 25% of ALL output**, and those 175 are only **35
    distinct message SHAPES** repeated ~5x each
  - `detect_stranded_work` (the work-loss gate) is leg **7 of 13**, dispatched at line **884** —
    BEHIND the flood. `detect_gate_integrity` is LAST. A 200s-capped run reaches NEITHER.
  - What works well and must be preserved: the `--- OPERATOR ACTIONS ---` block and the
    `!! FOREMAN VERDICT !!` banners ARE visually distinct and unconditional. They correctly
    surfaced `[DEFECT] COLLISIONS present` and `[ADVISORY] STARVING TIERS: frontier`.

**CORRECTION — a claim in PRIORITY-TODO sec.C is WRONG, and my first review repeated it worse.**
sec.C states "16 `|| return 0` fail-open guards in preflight.sh". A first pass here reported "39".
BOTH ARE FALSE. Measured:
    `|| return 0` (a LEG silently gives up) = **1**
    `|| true`     (cleanup / deliberate boot-safety) = **38**
They are unrelated constructs. The 38 are `rm`/`mkdir` cleanup and the documented "never block
session boot" idiom — converting them would BREAK boot safety. **There is exactly ONE leg-level
fail-open.** Do not launch a 39-guard audit; fix the one and move on.

REMEDIES — with the adversarial verdict on each, DO NOT implement naively:
 1. CAP REPEATED SHAPES (count + distinct shapes, detail behind a flag). **RISK: this is
    SUPPRESSION**, the class DIVERGED-BRANCH-TRIAGE explicitly forbids — silence is how a class
    returns. Only safe if a NEW shape REDs and full detail stays reachable. The shape-normaliser is
    itself a defect surface: a sloppy one merges two different findings into one.
 2. VERDICT SUMMARY. **RISK: "at the end" is fragile under the very timeout that motivated it** —
    a 200s kill yields NO summary at all, worse than partial output. And a summary produced by the
    same pass can silently omit a leg that CRASHED. Needs the bidirectional property: assert every
    REGISTERED leg produced a verdict, and emit incrementally or early.
 3. REORDER BY CONSEQUENCE. **RISK: data flow unchecked** — 9 references to shared `state/`; legs
    may write what later legs read. Check dependencies BEFORE reordering. Also beware encoding
    today's topic as permanent priority; prefer "cheap and decisive first".
 4. ~~Audit 39 fail-open guards~~ **REJECTED — the premise was a miscount (see CORRECTION).**
 5. ~~Split `--brief` / `--full`~~ **REJECTED.** The session-start hook calls preflight, so brief
    WOULD be the default path and any leg omitted from it becomes a new blind spot. Two output
    paths is two things to drift. Make the SINGLE output concise instead.

META-LESSON, recorded because it is the reusable part: the first review measured what preflight
EMITS and then recommended restructuring how it WORKS, without reading a single leg implementation.
The only proposal that survived adversarial review unscathed was the one grounded purely in
measurement. **Read the legs before restructuring them.**
