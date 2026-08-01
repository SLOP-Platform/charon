repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: feat/assign-deterministic-selector
depends_on:
owns: fleet/tests/assign-deterministic-selector.test.sh
substrate: N/A
substrate-novel: |
  The PATTERN is ADOPTED, not invented — it is TASKPLAN's (ellmos-ai) deterministic code-side
  selector, evaluated and recorded by the RESEARCH-WORK-MGMT-LAYER lane (2026-07-31,
  `fleet/handoff-notes/RESEARCH-WORK-MGMT-LAYER.md` Appendix B8) which found TASKPLAN itself
  not adoptable (too early, wrong abstraction) but its SELECTOR pattern the single
  highest-leverage extraction. What is written here is ordering logic over OUR OWN board schema
  (tier / work_class / priority / difficulty / owns / depends_on) — no external tool models that,
  and importing a task framework to get 50 lines of ordering would be the rig-as-product disease.
serial_justified: |
  ONE selection function. Splitting the ordering rules from the honest-no-op contract would ship a
  selector that reorders but still returns a wrong pick when nothing is eligible.
execution: |
  Off-Claude via fleet-droid.sh, own worktree.
source: |
  RESEARCH-WORK-MGMT-LAYER lane (deepseek-v4-pro, 2026-07-31), Appendix B8, ranked NOW /
  HIGH-LEVERAGE. Operator confirmed 2026-08-01: "the TASKPLAN deterministic selector for assign.py
  is the highest-leverage pattern — it directly addresses the 'agent picks the most visible ticket,
  backlog hides' failure mode."
note: |
  ## THE PATTERN (adopted from TASKPLAN, per the research lane)
  **"Moves the decision out of the prompt and into code."** Concretely:
    - Easy/cheap work is EXHAUSTED GLOBALLY before any harder tier is started.
    - `large` / `special` work is NEVER claimed autonomously.
    - UNCLASSIFIED work is INVISIBLE to the selector (it cannot be picked by accident).
    - The selector returns an HONEST NO-OP (`None`) when nothing is selectable — it never
      degrades to "closest match".
    - Deterministic and auditable: **no LLM anywhere in the selection loop.**

  ## THE FAILURE MODE IT FIXES (operator's words)
  "Agent picks the most visible ticket, backlog hides." Today `claim.sh` / `assign.py` filter by
  model-eligibility correctly, but the ORDERING among eligible tickets is essentially FIFO, so
  work that is cheap and unblocking loses to whatever happens to be near the top. Symptom visible
  on the board right now: 46 PRs open, many >370h, while new work kept being started.

  ## SCOPE
  Implement the selector in the assign/claim path. It MUST be:
    - **Deterministic** — same board state ⇒ same pick, every time. A test asserts this by running
      the selector twice over a fixed fixture and comparing.
    - **Auditable** — it must be able to explain WHY it picked what it picked (which rule fired),
      because an unexplainable scheduler cannot be debugged.
    - **Honest** — returns nothing when nothing is eligible. **Never** relax a filter to find a pick.
  Ordering rules to implement, in this precedence:
    1. `priority:` (0 first) 2. cheapest eligible `tier:` exhausted before a costlier one
    3. unblocking work (tickets that other tickets `depends_on:`) before leaf work
    4. lower `difficulty:` before higher, within the same band.
  NEVER auto-selectable: frontier-tier, `parked: true`, missing/invalid `work_class:` or `tier:`.

  **Reuse-check FIRST:** `fleet/assign.py` and `fleet/claim.sh` already exist and already do
  eligibility filtering, and `fleet/wci-contention.sh` already computes contention. This is an
  ORDERING change on top of them — do NOT rewrite the claim path, and do NOT add a second
  selector. If the cleanest shape is ~50 lines inside the existing selection function, that IS the
  answer [[best-not-defensible]]. Confirm the real file/function before writing anything; the
  research note's "~50 LOC change to assign.py" is an ESTIMATE, not a measurement.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline, fixture board. Each RED on the named revert, then GREEN:
    a. determinism: selector run twice over one fixture returns the identical pick.
    b. cheap-tier exhaustion: with economy AND strong work both eligible, economy is picked until
       economy is empty. Revert the ordering rule ⇒ RED.
    c. honest no-op: nothing eligible ⇒ returns NOTHING and exits cleanly. It must NOT pick a
       parked / frontier / unclassified ticket as a fallback. This is the RED LINE.
    d. unclassified invisibility: a ticket with a missing/invalid `work_class:` is never picked.
    e. unblocking-first: a ticket that 2 others depend on outranks an equal-priority leaf.
    f. ANTI-OVER-BLOCK: a normal single eligible ticket is still picked exactly as today.
  Then run against the REAL board and print the ordered pick-list with the reason per pick.

D&S — Deps & Sequence:
  - Depends on: nothing. Do NOT edit `fleet/fleet-droid.sh` (3 tickets already contend for it) —
    this belongs in the assign/claim layer.
