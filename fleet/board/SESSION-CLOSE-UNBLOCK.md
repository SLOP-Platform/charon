repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: fix
branch: fix/session-close-unblock
depends_on:
owns: fleet/state/SESSION-CLOSE-UNBLOCK.md, docs/review-log/SESSION-CLOSE-UNBLOCK.md
serial_justified: |
  A single conflicted branch reconciled against a moved base. There is one file set and one
  conflict; two tabs on it would collide on the same hunks.
substrate: N/A
substrate-novel: |
  No tool choice arises. This resolves a merge conflict on an existing branch whose fix is
  already written and proven; the novel slice is only the reconciliation against a base that
  moved underneath it today.
accept: |
  PR #359 carries the ALLOCATOR fix and is now CONFLICTED (auto update-branch refused).
  Why it matters: every session close runs end-session.sh, whose allocator refuses the caller's
  own 0-byte target file, so the one gate meant to prevent work loss aborts BEFORE its work-loss
  check on EVERY run. The fix is one line at fleet/claim-jedi-name.sh:47 (`[ -e ]` -> `[ -s ]`)
  plus a real integration test that drives the UNMODIFIED handoff.sh, plus --release/--gc for the
  name pool (was 48% burned; 32 names reclaimed).
  1. Resolve the conflict WITHOUT losing the integration test — the pre-existing suites all
     stubbed the allocator out via END_SESSION_HANDOFF_SH, which is why a 100%-broken gate showed
     green. That test is the whole point; if it does not survive, the reconciliation is wrong.
  2. Get CI green, land.
  3. PR #116 is also conflicted and has NO CI as a result. Triage it: land, or close with evidence.

## Dependencies & Sequence

SECOND in blast radius. Independent of UNBLOCK-REVIEW-INFRA (disjoint owns) so it runs
concurrently, but it gates every session close: until it lands, each session's work-loss check
aborts before running, which is the exact mechanism that let 96 commits accumulate unpushed.

Internal order: resolve #359's conflict and land it BEFORE triaging #116 — #116 is a stale
conflicted PR with no CI, and the reconciliation technique proven on #359 applies to it.
