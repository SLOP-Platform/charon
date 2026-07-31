repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 1
branch: feat/session-report-wire
depends_on: DROID-LIFECYCLE-REAP, LAUNCHER-CRASH-PARTIAL-DETECT
owns: fleet/fleet-droid.sh, fleet/JOIN-PROMPT.md, fleet/tests/session-report-wire.test.sh
substrate: N/A
substrate-novel: |
  The FORMAT and the VALIDATOR already exist in-tree and are being REUSED unchanged
  (fleet/SESSION-REPORT-FORMAT.md defines SESSION REPORT v1; fleet/check-session-report.sh
  validates it fail-loud). Nothing here re-implements them. The novel slice is the DERIVATION:
  extracting ~11 report fields from fleet-droid.sh's OWN submit-path variables (claimed ticket,
  model chain, gate exit code, git diff, CHARON_RUN_RESULT). No established external tool owns
  "emit a structured outcome report from this launcher's internal state" — CI-native equivalents
  (GITHUB_STEP_SUMMARY, gh pr comment) are DELIVERY surfaces, not fact-derivation, and this runs
  outside CI. Adopting one would still leave the derivation entirely unbuilt.
serial_justified: |
  ONE change to ONE submit path. Splitting the derivation from the brief-side ask would ship a
  launcher writing fields the brief still redundantly requests, or a brief trimmed to 5 fields
  with nothing writing the other 11 — either half alone REGRESSES the report.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. Strong tier chain verified funded 2026-07-31
  (minimax-m3-free, deepseek-v4-flash, glm-5.2, gpt-5.4-mini — all HTTP 200, all present in
  opencode.json's charon model list).
source: |
  Operator, 2026-07-31: "I would like each tab to do a session end report ... there was no
  consistency on how/what was reported. Should be concise, token-lean recap/outcome/status."
  Reuse-check found the format ALREADY EXISTS and is INERT for droids.
note: |
  ## FACTS (verified 2026-07-31)
  - `fleet/SESSION-REPORT-FORMAT.md` defines SESSION REPORT v1 — 16 fields, ~16 lines.
  - `fleet/check-session-report.sh` validates it and FAILS LOUD naming every missing field.
  - **`fleet/JOIN-PROMPT.md` never mentions it.** JOIN-PROMPT is embedded in EVERY fleet-droid
    brief (`fleet-droid.sh:1036`), so no droid is ever ASKED for a report.
  - **`fleet-droid.sh` never calls the validator** (`grep check-session-report fleet-droid.sh` -> 0).
  - `grep -lc "SESSION REPORT v1" fleet/state/agent-logs/*.txt` -> **ZERO**. No droid log in the
    archive carries the block. This is NOT a new regression.
  - It IS referenced by ~7 hand-written `prompts/*.md`, so consistency has depended entirely on
    whoever wrote each per-ticket prompt remembering to paste it in.
  - CLASS: built-but-inert (corpus #1, ~18 incidents). The fix is a WIRE, not a build.

  ## SCOPE — "Option C: derive, don't demand" (operator-chosen over block/warn)
  Split the 16 fields by who actually knows the answer.

  **MECHANICAL (~11) — the LAUNCHER writes these from facts it already holds. Never ask the model.**
  TICKET · SESSION · STATUS · COMMIT · FILES · OWNS-OK · GATE · TESTS · BLOCKED-BY · BUDGET ·
  RED-PROOF exit codes.
  Sources already present in the submit path: the claimed ticket id, `$DROID` + the resolved model,
  the gate's real exit code, the `git diff` computed for the leak-guard, and `CHARON_RUN_RESULT`
  from charon-run.sh (SUCCESS / EXHAUSTED / rc=124).

  **JUDGMENT (~5) — ask the MODEL for these, and only these, via JOIN-PROMPT.md.**
  OBSERVABLE · RAN · READ · BRIEF-ERRORS · NEXT.
  A field the model omits is written by the launcher as `NOT-REPORTED` — explicit and greppable.
  Silence must never render as a blank line.

  **WHY THIS BEATS block-or-warn (record it; do not re-litigate):**
  - Cannot strand work — the report always exists because the launcher writes it, so a weak model
    fluffing the format costs 5 fields, not a landed ticket.
  - Not advisory — guaranteed present and machine-true, so it cannot decay the way a warning does.
  - **Upgrades self-report to evidence.** COMMIT/FILES/GATE today are the model's claims ABOUT
    ITSELF (self-report-lie class, ~12 corpus incidents, no gate). Derived from git and the gate's
    real exit code, a droid can no longer report `GATE: PASS` on a red gate.
  - Cheaper per session: 5 lines asked instead of 16, from often-weak models.

  **TWO REFINEMENTS (in scope):**
  1. Write the block to `fleet/state/reports/<droid>-<ticket>.md` AND append it to the PR body —
     not stdout only. The manager greps files instead of scrolling terminal buffers, and the
     report travels with the work instead of dying with the tab.
  2. If the model ALSO emits its own block and it CONTRADICTS the derived facts, keep BOTH and
     flag the conflict. Do not silently prefer one. `STATUS: DONE` over a derived `GATE: FAIL` is
     the highest-value signal this mechanism can produce — feed it to auto-log-model-lies.

  **OUT OF SCOPE:** changing SESSION REPORT v1's fields, or rewriting check-session-report.sh.
  Both are reused as-is. Adding a field is a separate ticket.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline, no live gateway. Each RED on the named revert, then GREEN:
    a. droid submits having emitted NO report -> a COMPLETE v1 block still exists
       (`check-session-report.sh` exits 0 on it) with the 5 judgment fields as `NOT-REPORTED`.
    b. derived COMMIT/FILES/GATE match git + the real gate exit code — revert the derivation and
       the test goes RED (proves the fields are derived, not echoed from the model).
    c. model emits `STATUS: DONE` while the gate exit code is non-zero -> BOTH recorded and the
       conflict flagged; a silent overwrite of either side is RED.
    d. report lands at `fleet/state/reports/<droid>-<ticket>.md` AND in the PR body.
    e. ANTI-OVER-BLOCK: a droid that DOES emit a full valid block keeps its judgment fields
       verbatim — the launcher must not clobber them.
  Then run it against a real claim and show the produced block.

D&S — Deps & Sequence:
  - Depends on: DROID-LIFECYCLE-REAP, LAUNCHER-CRASH-PARTIAL-DETECT — REAL sequencing prereqs,
    not paperwork. All three edit `fleet/fleet-droid.sh`; DROID-LIFECYCLE-REAP is already PR-OPEN
    and LAUNCHER-CRASH-PARTIAL-DETECT is blocked behind it. Wiring a report into a submit path
    those two are about to rewrite means one change silently eats the other. validate_board.sh
    flagged this as `owns-collision LIVE (no dep ordering)` at mint time.
  - CONSEQUENCE (surfaced deliberately): this ticket is therefore BLOCKED on landing
    DROID-LIFECYCLE-REAP (PR-OPEN ~374h). If the operator wants the report sooner, the lever is
    landing that PR — not dispatching this one in parallel.
  - Does NOT block the board. Sequence AFTER the remaining orphan-marker REDs clear.
