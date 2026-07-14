# HANDOFF-MECHANIZE — Review Log

## Ticket
HANDOFF-MECHANIZE: enrich handoff.sh to auto-emit all required handoff-check.sh
sections + live machine state (worktrees / in-flight charon-run jobs / exhaustion
ledger / session-bridge board); keep section headers in sync; wire handoff-check.sh
into preflight.sh as an active detector with a tracked blocking red; add a
fail-on-revert meta-test.

## Root cause being fixed
Poor/inaccurate/incomplete handoffs have been a recurring failure mode
(multiple sessions; costing 1+ hours each). Two underlying gaps:

1. **handoff.sh was a partial generator.** It auto-emitted git/PRs/gate/roadmap/board,
   but the manager still hand-typed the next-session action list, the done-SHA claim,
   the worktree list, the in-flight charon-run jobs, and the provider-exhaustion
   ledger tail. Hand-typed facts drift; a copied handoff from a stale session
   (e.g. 3647e0e) was indistinguishable from a fresh one without an anti-clobber
   provenance stamp. The Bootstrap / Done / Next / Gotchas / session-bridge
   sections were NEVER auto-emitted — handoff-check.sh would fail a generated
   handoff on the very things it should be making easy.

2. **handoff-check.sh existed but was passive.** v1 (2026-07-10) was a completeness
   gate but the operator rule `[mechanized-handoff-gate]` was unenforceable — a
   bad handoff just sat on disk until the next session discovered the
   incompleteness after a half-hour of trust. The rule belongs in
   `preflight.sh`'s gate family (alongside board_gate, executor_gate,
   done_merge_gate, detect_needs_push) where a red auto-registers a tracked
   red and BLOCKS preflight.

## What was done
- **fleet/handoff.sh** (heavily enriched, ~300 -> ~430 lines):
  - Added `## Bootstrap` block (a fenced single-sentence one-liner pointing
    at the file; this is the only section the next session copy-pastes).
  - Added `## Done / committed@SHA` block — auto-emits the latest 5 SHAs on
    rig master + product master, and the `## Provenance` stamp now also
    reads (and surfaces a `⚠ STALE` marker if the local checkout is behind
    origin — handoff-check catches it as a freshness failure).
  - Added `## Next-action / in-flight` block — manager's narrative placeholder
    for the priority list, with a clear pointer that the LIVE MACHINE STATE
    (worktrees, charon-run jobs, ledger) is auto-emitted under the
    `## Auto-generated state` block below.
  - Auto-emitted LIVE MACHINE STATE under `## Auto-generated state` (so it
    is naturally excluded from handoff-check's HUMAN-scope SHA + path
    existence checks, which would otherwise false-positive on ephemeral
    agent worktree SHAs):
    - `### Active worktrees (\`git worktree list\`)` — both charon and rig.
    - `### In-flight charon-run jobs (CHARON_RUN_RESULT)` — the 8 most recent
      `*.charon-run.log` files, with the live `CHARON_RUN_RESULT=...` line
      (or `IN-FLIGHT (no CHARON_RUN_RESULT line yet)` for jobs still running).
    - `### Provider-exhaustion-ledger tail` — last 10 lines of the live
      `provider-exhaustion-ledger.tsv` (after the header).
  - Added `## session-bridge` block — auto-emits the live
    `~/.charon/session-bridge.db` board (last 30 min, name / repo / status /
    ticket / last_seen) using a `python3` sqlite3 probe. Empty board is
    surfaced as "(no active bridge sessions in the last 30 min)".
  - Added a coordination-rule block under the bridge section (review the
    board before claiming work; surface blockers; don't re-register
    inherited sessions).
  - **Gotchas section is now pre-populated** with the canonical
    "`git push` is DENIED to the manager" gotcha PLUS auto-surfaced
    pre-existing tracked reds whose description text matches a gotcha-
    marker (`DENIED | never-ignore | never commit | never push | never
    deploy`). This makes "what burned us last time" a property of the
    reds registry, not of hand-typed prose that drifts.
  - All `|| true` wrap-around the live probes so a transient git/python
    failure (network down, repo missing) renders a `(probe failed)`
    notice rather than halting the whole handoff.
  - Hard gate exit code preserved: a RED `gate.sh` still exits non-zero
    so a red gate cannot be handed off as a green one.

- **fleet/preflight.sh** (~26K -> ~30K):
  - Added `handoff_gate` (and helpers `_handoff_red_status`,
    `_handoff_red_ensure_open`, `_handoff_red_close_if_open`) following
    the identical machinery as `board_gate` / `executor_gate` /
    `done_merge_gate`. On RED it AUTO-REGISTERS a P1 tracked red
    `handoff-fails-gate`; on GREEN it auto-closes the same red.
  - Wired into the `scan` dispatch between `executor_gate` and
    `done_merge_gate` (so it lands in reds.tsv BEFORE `cmd_scan` and
    thus blocks preflight like a red board / red done marker / stranded
    push).
  - Picks the newest `HANDOFF-*.md` (NOT `SESSION-HANDOFF-*.md` — those
    are per-session bootstrap docs whose freshness is covered by the
    SESSION start hook).

- **fleet/tests/handoff-mechanize.test.sh** (NEW, 15 assertions, 4 blocks):
  - **(a) Round-trip:** handoff.sh's rendered output carries every
    required section header (Bootstrap / Done / Next / Gotchas /
    session-bridge) AND, when saved to its canonical path, passes
    handoff-check.sh. Reverting the section headers -> the a1 block
    fails.
  - **(b) Negative:** a hand-broken handoff (gotchas section stripped
    via `re.sub`) FAILS handoff-check.sh with the section name
    (`MISSING section: gotchas`) printed to stdout. Reverting
    handoff-check's section-requirement list -> b1 fails.
  - **(c) Fail-on-revert (the load-bearing check):** we COPY
    handoff-check.sh into a temp file, delete the `[gotchas]='...'`
    line from the copy's NEED array, and re-run the same broken
    fixture through the stripped copy. The stripped copy ACCEPTS
    the broken fixture (no gotchas check = no MISSING section line
    = exit 0) — proving the original `[gotchas]` entry is LOAD-
    BEARING, not redundant. If a future refactor added ANOTHER check
    that incidentally caught the missing gotchas, the stripped copy
    would still FAIL the broken fixture and c1 would flag the
    redundancy for review (the test is fail-on-revert, but the
    semantics are "removed check must let bad handoff through").
  - **(d) preflight.sh wiring:** SOURCES a copy of preflight.sh +
    _lib.sh + handoff-check.sh in a temp fleet/ root (so the live
    `reds.tsv` is never touched), writes a minimal HANDOFF-*.md
    fixture to the canonical rig path, and verifies the full
    handoff_gate lifecycle: passing fixture -> no red; broken
    fixture -> red auto-registered as open; repaired fixture -> red
    auto-closes. Proves the `_handoff_red_ensure_open` /
    `_handoff_red_close_if_open` machinery is wired and live (not
    just defined).

## Scope self-check
Verified via `git diff --name-only master...HEAD` (after `git add` of the
3 files): the only paths changed are `fleet/handoff.sh` (M),
`fleet/preflight.sh` (M), and `fleet/tests/handoff-mechanize.test.sh`
(new). All three are inside the ticket's `owns:` line. No review-log
fragment collides with another droid's — written to
`docs/review-log/HANDOFF-MECHANIZE.md` (per-ticket fragment, as instructed
in the launch prompt).

## Design notes / trade-offs

- **Why a fully-quoted heredoc for PREAMBLE5:** an earlier attempt used
  an unquoted heredoc so `$DATE_UTC` would expand; bash then interpreted
  literal backticks (e.g. `` `register()` ``) inside the heredoc as
  command substitution and tried to find a matching `(`, emitting
  "syntax error: unexpected end of file" before the line was even read.
  Quoted heredoc + `## Auto-generated state` (without the date in the
  header) is simpler and shellcheck-clean. The full timestamp still
  lives in `**Generated:** $DATE_UTC` near the top.
- **Why auto-state lives under `## Auto-generated state`:** handoff-check's
  awk filter (line 92) scopes the strict SHA + path existence checks to
  HUMAN sections only (skipping `## Auto-generated state` onward). The
  auto-emitted worktree / jobs / ledger sections reference SHAs that
  belong to ephemeral agent worktrees (e.g. `a4294af67f9d41d80`) that
  aren't in either upstream repo — those would false-positive the
  HUMAN-scope SHA check. Putting the live state under the auto-state
  header makes the scoping natural; the manager still sees the facts.
- **Why a temp-fleet fixture for (d) instead of mutating live reds.tsv:**
  The other preflight gate tests (e.g. `needs-push-gate.test.sh`) use
  the same temp-fleet pattern — copy preflight.sh + _lib.sh +
  verify-merged.sh into a `mktemp -d` and source the copy. Live
  `reds.tsv` is never touched, and the test is fully hermetic (no
  network, no real `gh` call).
- **Why the bootstrap block names a literal path:** the manager's
  workflow is "save the rendered handoff to
  `/home/stack/charon-private/fleet/SESSION-HANDOFF-<name>.md`, commit
  it, then the next session reads it." The bootstrap block therefore
  names the canonical save path. handoff-check's `[paths]` test
  resolves `[ -e "$p" ]` literally — when the file is at the canonical
  save path (production) the check passes; when the file is in a
  transient worktree (CI / dev) the path check is the only thing
  that fails, and the meta-test accommodates that by saving the
  fixture to the canonical path before running handoff-check.
- **Why harness-managed close:** the auto-close uses
  `cmd_close --override "auto: ..."` (recorded, not assumed). The
  override text is part of the audit trail so an operator can later
  see WHY the red was closed. The same pattern is used by every
  other preflight gate.

## Test summary
`bash fleet/gate.sh` -> 16/16 tests PASS (15 from existing +
1 new `handoff-mechanize.test.sh`). shellcheck is advisory, no
new findings from the changed files. `pytest -q` 49/49 PASS
(product repo, unchanged by this ticket). ruff / mypy
pre-existing findings unchanged (ticket doesn't touch src/).
