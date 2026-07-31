repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 0
branch: feat/brief-evidence-lint
depends_on:
owns: fleet/checks/brief-evidence.sh, fleet/tests/brief-evidence.test.sh
serial_justified: |
  ONE guard and its red-proof. The lint without the suite is an unproven gate; the suite without
  the lint asserts nothing. The invocation wiring is the point of the ticket — a lint with no
  callsite is precisely the inert-gate defect it exists to prevent.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
  Verified-funded legs 2026-07-31: deepseek-v4-pro, minimax-m3-together. NOTE devstral-2512 and
  gemini-2.5-pro are served by the gateway but are NOT in opencode.json's charon provider list
  (36 of 2567), so opencode silently falls back to gpt-5.4 (dead pool) — do not use them.
source: |
  Operator, 2026-07-31: "how can we fix the fact that you were not demanding a file:line or a
  command transcript for the manager sessions?" Recommendation approved.
note: |
  ## FACTS (verified)
  - `fleet/state/agent-briefs/` has NO gate of any kind. Verified: `grep -rln "agent-briefs"
    fleet/checks/ fleet/tests/` returns only `fleet/tests/worker-lifecycle.test.sh`, which
    references the path incidentally and does not lint briefs.
  - Every OTHER high-blast-radius manager artifact IS gated: `fleet/land.sh`,
    `fleet/board-lock.sh`, `fleet/preflight.sh`, `fleet/handoff-check.sh`,
    `fleet/check-session-report.sh`.
  - `fleet/MANAGER-OPERATING-RULES.md` §11 now carries the rule "AN UNSOURCED MANAGER CLAIM IS
    NOT A FACT — and it propagates", which names this lint as its mechanization.
  - `fleet/BRIEF-TEMPLATE.md` now requires `## FACTS (verified)` and `## FRAMING (hypothesis)`.
  - The DTC protocol already encodes the same defense as G3 (`contextContent` facts-only,
    because a curated framing is a bias vector every lens inherits):
    `/home/stack/code/mediastack/docs/DTC-CONSOLIDATED.md`.

  ## FRAMING (hypothesis — challenge it)
  A brief is the manager's highest-blast-radius output: it is not a claim, it is the METHOD that
  N agents execute simultaneously. One unverified premise therefore contaminates a whole wave at
  once, and no worker can distinguish a measured fact from the manager's guess because both
  arrive in the same voice. Gating the brief is believed to be the cheapest effective chokepoint.
  If you find a better one — or find that linting briefs is theatre because the real damage is in
  conversational prose that no lint can reach — SAY SO. That verdict would be worth more than the
  lint.

  ## WHAT TO BUILD — SMALL, COMPOSED, NOT A NEW GATE FAMILY
  `fleet/checks/brief-evidence.sh <brief.md>`:
  - RED when a brief has no `## FACTS` section.
  - RED when a line inside `## FACTS` carries no evidence marker — no `file:line`, no `$ command`,
    no quoted output.
  - RED when `## FRAMING` is missing the standing challengeability line.
  - GREEN otherwise. Advisory-vs-blocking is YOUR call to propose (see GUARDS).

  **ANTI-ACCRETION IS A HARD CONSTRAINT.** `fleet/checks/gate-creation-standard.sh` opens by
  stating it "COMPOSES existing lenses — it does NOT mint per-instance checker scripts". Obey
  that. Wire this into an EXISTING callsite (`fleet/spawn-worker.sh`, which already gates on TUI
  readiness, is the natural one — it is the moment a brief becomes operative). Do NOT invent a
  new gate framework, a new registry, or a new runner.

  ## GUARDS
  - **Blocking a spawn on a lint is itself a risk**: a gate that blocks real work gets disabled,
    and a disabled gate is not a gate [[gates-must-actually-run]]. Propose the escalation
    (advisory-then-blocking? warn on legacy briefs, block on new ones?) and say how many of the
    EXISTING briefs in `fleet/state/agent-briefs/` would fail on day one — count them.
  - The lint checks that a claim is SOURCED. It cannot check that a source is CORRECT. Do not
    oversell it; state this limit in the script header.
  - Do not edit `fleet/MANAGER-OPERATING-RULES.md` or `fleet/BRIEF-TEMPLATE.md` — both already
    landed and are outside your `owns:`.

  ## DONE CONTRACT — RED, GREEN, AND A REAL RUN
  - Hermetic suite under `mktemp -d`, offline. Breaks EXTERNALLY SPECIFIED — do not choose your
    own; each must be watched RED then GREEN, both transcripts pasted:
      a. brief with NO `## FACTS` section -> RED
      b. `## FACTS` line with a bare assertion and no evidence marker -> RED
      c. `## FACTS` line with `path/to/file.py:123` -> GREEN
      d. `## FACTS` line with `$ cmd` + output -> GREEN
      e. `## FRAMING` present but missing the challengeability line -> RED
      f. ANTI-OVER-BLOCK: a fully compliant brief -> GREEN, exit 0. A lint that fails everything
         is as useless as none.
      g. FAIL-CLOSED: unreadable/missing brief file -> RED, never a silent pass.
  - Run it against the REAL `fleet/state/agent-briefs/*.md` and report the pass/fail count with
    names. Several were written before the template existed; that count IS the day-one blast
    radius the operator needs to see.

D&S — Deps & Sequence:
  - Depends on: nothing. Rule §11 and BRIEF-TEMPLATE.md are landed.
  - Blocks: nothing structurally; it is the forcing function behind the §11 rule.
  - Related: UNREVIEWED-WORK-ALARM (same wave, same "a rule without a chokepoint is not a rule"
    class). Disjoint `owns:` — no collision.
