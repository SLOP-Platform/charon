repo: charon-private
tier: economy
priority: 1
difficulty: 1
work_class: bugfix
branch: fix/brief-absolute-paths
depends_on: SESSION-REPORT-WIRE, LOOP-GUARD-REASON-WIRE
real-dep: SESSION-REPORT-WIRE introduced the judgment-file brief text in fleet/fleet-droid.sh; this fixes that text and must land after it
owns: fleet/fleet-droid.sh, fleet/tests/brief-absolute-paths.test.sh
serial_justified: |
  One brief-rendering change and its proof. Nothing to split.
source: |
  Measured 2026-08-01: droid `cal-kestis` wrote its judgment file to `state/judgment/` at REPO
  ROOT instead of `fleet/state/judgment/`. Recovered by hand. Operator: mechanize it so droids
  CANNOT resolve relative.
note: |
  ## THE DEFECT
  The brief embedded by `fleet-droid.sh` instructs the model:
      write a partial block to  $FLEET/state/judgment/$DROID-$id.md
  `$FLEET` and `$DROID` are SHELL VARIABLES of the launcher, not of the model's shell. When the
  model's shell lacks them they expand to empty and the path becomes RELATIVE — resolving against
  whatever the model's CWD happens to be.

  Observed 2026-08-01: 4 of 5 droids wrote to the correct `fleet/state/judgment/`; `cal-kestis`
  wrote to `<repo-root>/state/judgment/cal-kestis-AUTO-DONE-ON-MERGE-MISS.md`. **Intermittent, so
  it will not be caught by inspection** — the launcher then records the field as `NOT-REPORTED`
  because it looks in the right place and finds nothing, silently degrading the report.

  ## THE FIX — RENDER, DON'T DELEGATE
  The launcher already KNOWS both values at brief-render time. Interpolate the fully-resolved
  ABSOLUTE path into the brief text instead of emitting a variable the model must expand:
      write ... to  /home/stack/charon-private/fleet/state/judgment/strong-1234-TICKET-ID.md
  **Sweep the whole brief** for the same pattern — any `$VAR` a model is told to expand is the same
  bug. `$FLEET`, `$DROID`, `$REPO`, `<your-worktree>`, `<id>` placeholders: each is either
  rendered concretely at build time or is a latent instance of this defect. Report every one found.

  ## CLASS
  Instructing an agent to expand a variable that exists only in the CALLER's environment. Fails
  silently and intermittently, degrading to a plausible-looking `NOT-REPORTED`. Related to
  [[no-hardcoded-cross-boundary-paths]] — the inverse error: that rule bans absolute paths CROSSING
  a boundary; this one requires them INSIDE a rendered brief, because the model has no other way to
  resolve the location.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline:
    a. the rendered brief contains a fully-qualified absolute judgment path and NO unexpanded
       `$FLEET` / `$DROID`. Revert the interpolation -> RED.
    b. a judgment file written to the rendered path IS picked up and its 5 fields land in the
       report (not `NOT-REPORTED`).
    c. **simulate the failure**: run the brief's instruction from a DIFFERENT CWD with `$FLEET`
       unset and prove the file still lands in the right place. This is the case that actually
       broke; a test that does not reproduce it proves nothing.
    d. ANTI-OVER-BLOCK: an absent judgment file still yields `NOT-REPORTED` as designed.
  Report every `$VAR`-in-brief instance found by the sweep, fixed or ticketed.

D&S — Deps & Sequence:
  - `fleet/fleet-droid.sh` is contended (LOOP-GUARD-REASON-WIRE, LAUNCHER-CRASH-PARTIAL-DETECT).
    Coordinate: if LOOP-GUARD-REASON-WIRE is mid-flight, sequence after it.
