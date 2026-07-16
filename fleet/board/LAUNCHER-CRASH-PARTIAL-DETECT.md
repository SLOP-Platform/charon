repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: feat/launcher-crash-partial-detect
serial_justified: One cohesive exit-handling change in the launcher's droid-stand-down path; the detection + labeling + PR-status are a single decision point.
owns: fleet/fleet-droid.sh, fleet/tests/test_launcher_crash_partial.sh
depends_on: DROID-LIFECYCLE-REAP
dep-kind: build
real-dep: both edit fleet/fleet-droid.sh stand-down/cleanup path; must sequence onto DROID-LIFECYCLE-REAP's landed version.
work_class_note: lifecycle-safety; a crash-partial PR mistaken for complete work ships half-done code.
note: |
  OPERATOR INSIGHT (2026-07-16): the recurring PR title "launcher auto-commit — droid exited
  without committing" (seen on #102, #135, #149, #93) is NOT a lazy droid — it is the OPENCODE
  CLIENT CRASHING MID-SESSION (same crash class as the Claude-Code crash that orphaned the
  fork-bomb this session). The launcher's droid-exit handler auto-commits whatever partial work
  survived and opens a PR that LOOKS like a normal deliverable. Consequences: crash-partial work
  (some real: #102; some near-empty: #149/#93) is indistinguishable from clean completion, so it
  can be merged half-done, and the ticket looks "submitted" when it actually needs redo.
accept: |
  - fleet-droid.sh distinguishes a CLEAN droid completion (worker exited 0 after its final
    commit/STOP) from a CRASH/abnormal mid-session exit (non-zero, signal, or truncated session).
  - On a crash/abnormal exit with a non-empty auto-commit: the PR/title/body is LABELED distinctly
    (e.g. "CRASH-PARTIAL — REVIEW/REDO, not a clean completion") AND the ticket is NOT marked
    cleanly submitted — it is flagged needs-review/redo so it re-enters the queue rather than
    masquerading as done. An EMPTY auto-commit opens no PR (release the claim for re-claim).
  - Preserve any real committed work (never discard — pairs with DROID-LIFECYCLE-REAP's
    preserve-committed-work guard).
  - fail-on-revert test fleet/tests/test_launcher_crash_partial.sh: simulate (a) clean exit →
    normal submit; (b) crash exit w/ partial commit → CRASH-PARTIAL label + needs-review, not
    clean submit; (c) crash exit w/ no commit → no PR, claim released.
  - rig gate GREEN.
scope: |
  Root-cause hardening for crash-partial PRs. Blast radius: every droid's stand-down + how its
  work is presented for merge — adversarial review before land (a wrong label could hide real
  work or ship partial work). Build-rig only.
ds: After DROID-LIFECYCLE-REAP (both edit fleet-droid.sh stand-down path). High value — stops
crash-partial work being mistaken for complete.
