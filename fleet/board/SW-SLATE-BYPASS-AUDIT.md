repo: charon
tier: strong
difficulty: 3
work_class: design-review
priority: 2
branch: docs/sw-slate-bypass-audit
depends_on:
owns: docs/review-log/SWITCHBOARD-BYPASS-AUDIT.md
serial_justified: |
  ONE survey producing ONE artifact. This ticket deliberately owns NO code: its output is a
  dispositioned inventory plus follow-on tickets, because the blast radius is unknown until the survey
  runs. Bounding it as a survey is what keeps it schedulable.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  The run IS a graded sample: record it into fleet/model-scorecard.tsv with the work_class above.
  One checkout, one agent — its OWN worktree, never a shared checkout.
source: |
  Operator decision 7(b), 2026-07-26 (manager session kit-fisto). ADR-0011's own Consequences section
  mandates this audit; it was never scoped as work.
note: |
  ## THE MANDATE (already written, never executed)
  ADR-0011 (Accepted 2026-07-16), Consequences: "Any code path that picks/ranks providers itself is a
  **bypass** and must be converged onto the Switchboard. Known bypasses to fix: `decompose_planner`
  (via `recommend._ask_model`/`_find_trusted_models`), and **an audit of every other `_ask_model` /
  static-slate caller**."

  `decompose_planner` was converged (it is now a DUMB CLIENT behind a `SwitchboardClient` seam). The
  rest of that sentence — the audit — was never done. INV-SW1 says no tool enumerates, ranks, or holds
  its own set of providers/models; nobody has checked whether that is true.

  ## WHY A SURVEY AND NOT A FIX
  The number of bypasses is unknown. A ticket that says "converge them all" cannot be estimated,
  scheduled, or given an owns: list without knowing what they are. This ticket produces the inventory;
  each real bypass then gets its own sized ticket with its own owns:.

  ## METHOD — read, do not pattern-match
  A zero-hit grep is NOT evidence a bypass is absent: a static slate survives renaming, aliasing and
  indirection, and the string does not. Grep may LOCATE candidates; only reading the call site may
  CONCLUDE. Use the owned tooling — `graphify explain` / `graphify path` against the code graph, and
  `tools/check_inert_code.py` — then open each site.

  Sweep for the CONCEPT (a locally-held ordering of providers/models), not one spelling:
  - `_ask_model`, `_find_trusted_models`, `recommend.py` and every caller
  - any module-level list/tuple/dict of provider or model names used to pick one
  - any "tier slate" / "candidate list" / "fallback list" consulted before or instead of the router
  - `fallback.json` consumers (the live file is `{"providers": []}` — prove nothing depends on it
    being non-empty)
  - any `for provider in ...` loop that terminates in an exhausted/give-up branch of its own
  - CLI/console paths and the work-engine, not just the gateway hot path

  ## FOR EACH CANDIDATE, DISPOSITION IT
  Exactly one of: **BYPASS** (picks/ranks providers itself -> needs a convergence ticket, sized);
  **LEGITIMATE** (a display list, a test fixture, a config surface — say WHY it is not selection); or
  **ALREADY CONVERGED** (routes through the Switchboard — name the seam). An undispositioned
  candidate is an incomplete audit.
accept: |
  DONE-CONTRACT:
  - `docs/review-log/SWITCHBOARD-BYPASS-AUDIT.md` exists containing: every candidate site as
    `file:line`, its disposition, and for BYPASS entries a one-line description of the convergence
    needed and a difficulty estimate.
  - Method stated per finding: what was proven by READING the call site vs. located by search. Any
    finding whose only evidence is a search hit is labelled UNCONFIRMED, not asserted.
  - A follow-on ticket authored per BYPASS finding, each with its own `owns:` and D&S. Zero BYPASS
    findings is an ACCEPTABLE outcome — but then state the coverage explicitly (what was swept, what
    was not, and why), because "found nothing" and "looked nowhere" must be distinguishable.
  - Explicitly confirm or refute INV-SW1 for the tree as it stands, with evidence.
  - NON-VACUOUS: an audit listing zero candidates examined is RED.
  - No code changes. A diff touching `src/` is out of contract — findings become tickets, not patches.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately, fully concurrent with the whole wave.** It reads and
  writes one doc; it owns no code and cannot collide.
- **Blocks:** nothing directly. Its OUTPUT (follow-on tickets) feeds a later wave.
- **Wave:** parallel lane, any time.
- **Concurrency safety:** owns one NEW doc; no live ticket owns it.
- **Do NOT duplicate:** check the board's existing `owns:` set before authoring any follow-on ticket —
  a bypass already owned by a live ticket gets a pointer, not a second ticket [[wci-ticket-decompose-method]].
