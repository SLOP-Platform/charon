# SESSION — SUBSTRATE GATE: is the branch work already on master? (re-scoped)

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `design-review`.
**READ-ONLY.** No edits, no commits, no landing, no branch deletion.

## WHY THIS IS A RE-RUN — the previous review answered the WRONG QUESTION
A prior review was asked "is `feat/substrate-first-gate-v2` canonical, and can v1 be retired?" It
answered MERGE-v2 / RETIRE-v1 — correct for the question asked. The merge then threw **13 conflicts
including three add/add**, because **master ALREADY HAS a substrate-first gate**, landed at `03ba2b1`
and since fixed by `06b1764` ("satisfy code by BASE-REF ticket owns, not only diff-touched board").
`fleet/checks/substrate_first_gate.py`, `fleet/tests/substrate-first-gate.test.sh` and
`fleet/state/EVAL-REGISTRY.md` are ALL live on master right now.

Neither the reviewer nor the manager asked whether master had moved past BOTH branches. The merge was
aborted; nothing was lost. **The manager's framing was the defect, not the reviewer's work.**

## THE ONLY QUESTION THAT MATTERS NOW
**What, if anything, does `feat/substrate-first-gate-v2` contain that master's LANDED gate does not?**

Not "which branch is better". Not "should v2 merge". Just: is there surviving value, and if so, what
is the smallest diff that captures it?

## METHOD
Compare BOTH branches against MASTER's current gate, not against each other.
* `git diff --stat master...feat/substrate-first-gate-v2` (THREE dots — two-dot LIES, it renders
  master's later additions as branch deletions and has already caused wrong verdicts here)
* Read master's live `fleet/checks/substrate_first_gate.py` and its test IN FULL first. That is the
  baseline. Everything else is measured against it.
* For each capability the branch claims — notably **"closes nine adversarial evasions"** — determine
  whether master's version ALREADY closes it. Pick at least three evasions and test them against
  MASTER's gate directly. If master already blocks them, the branch adds nothing there.
* `06b1764` was a FIX to the landed gate. Check whether the branch predates it and would REGRESS it.

## POSSIBLE OUTCOMES — all four are acceptable, say which honestly
1. **NOTHING SURVIVES** — master's gate covers everything. Both branches abandoned. This is a
   perfectly good result; it deletes ~4000 lines of merge risk. Do not manufacture value to avoid it.
2. **A SMALL DIFF SURVIVES** — name the specific hunks/tests worth cherry-picking, as a minimal patch.
   Give the exact files and what each adds.
3. **THE BRANCH IS BETTER** — master's gate is materially weaker. Then say what master MISSES, and
   whether replacing it would regress `06b1764`'s fix.
4. **UNSAFE-TO-JUDGE** — say what you would need.

## RULES
- READ-ONLY. Do not edit, commit, land, cherry-pick or delete. You produce a recommendation.
- **Stop at sufficient evidence for the verdict. Do NOT debug the code under review** — a reviewer
  today burned a session root-causing a bug when a failing test had already settled the verdict.
- Run master's gate to see it work; break it externally to see it fail. A gate you never saw go RED
  is unverified.
- A zero-hit grep is NOT evidence — read the code.
- Say what you proved by RUNNING vs by READING.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-SUBSTRATE-SUPERSEDED.md`.
Lead with one line: **NOTHING-SURVIVES | SMALL-DIFF | BRANCH-IS-BETTER | UNSAFE**, then the evidence.
Then emit the SESSION REPORT v1 block (spec: `fleet/SESSION-REPORT-FORMAT.md`; validate with
`bash fleet/check-session-report.sh <file>`).

## Dependencies & sequence
- **Depends on: NOTHING.** Read-only, owns one report file, cannot collide.
- **Blocks:** disposition of `feat/substrate-first-gate` and `-v2` (both currently unlandable).
- **Wave:** review lane, P0.
