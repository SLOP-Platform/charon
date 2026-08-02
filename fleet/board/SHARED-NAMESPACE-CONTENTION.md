repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: fix/shared-namespace-contention
depends_on:
owns: fleet/claim-jedi-name.sh, fleet/tests/claim-jedi-name.test.sh, fleet/spawn-worker.sh, fleet/tests/scratch-namespace.test.sh
serial_justified: |
  ONE class with two instances that must be fixed together: a shared mutable namespace with no
  separation between QUERY and CLAIM, and no cleanup of orphaned claims. Fixing the name allocator
  while leaving lanes writing to bare /tmp (or vice versa) leaves the class live and guarantees a
  third instance. The operator explicitly asked for the GATE-level fix, not another instance patch.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
  Model note: opencode silently falls back to the DEAD gpt-5.4 pool for any model not in
  opencode.json's charon provider list (36 of 2567). Verified listed AND funded 2026-07-31:
  deepseek-v4-pro, gpt-oss-120b-groq, grok-build-0.1, minimax-m2.7, big-pickle.
source: |
  Operator 2026-07-31, after being bitten twice in one session: "if something bites us more than
  once shouldn't we fix it at the gate? Why have everything write into /tmp instead of
  /tmp/mytmpfile-date so there isn't a contention?" and "same with names being claimed already —
  seems collisions with name is an ongoing issue".
note: |
  ## THE CLASS
  A shared mutable namespace where (a) the READ operation mutates state, or (b) many writers share
  one flat location with no per-run isolation, and (c) nothing reaps orphaned entries.

  ## FACTS (verified 2026-07-31)

  ### Instance 1 — the name allocator is NOT IDEMPOTENT
  - `fleet/claim-jedi-name.sh:6` — it "atomically writes a claim marker" as part of PICKING a name.
    Asking IS claiming. There is no availability-check that does not mutate.
  - Observed live: running `claim-jedi-name.sh` standalone printed `rey-skywalker`. Passing that
    same name back as `SESSION=rey-skywalker bash fleet/handoff.sh` was REFUSED —
    `handoff.sh:74`: *"refused by claim-jedi-name.sh — that name is already in use (live file
    present)"*. The allocator rejected the name it had just issued, because it saw its own marker.
  - CONSEQUENCE: `rey-skywalker` is now marked claimed with NO `fleet/SESSION-HANDOFF-rey-skywalker.md`.
    A LEAKED name. This is why the pool keeps getting consumed — every abandoned or retried claim
    burns a name permanently.
  - Note the two components disagree on the definition of "in use": one counts markers, the other
    counts live handoff files + git history (`claim-jedi-name.sh:39-55`).

  ### Instance 2 — bare /tmp contention
  - Lane reports were written to bare `/tmp/research/`, `/tmp/triage/`, `/tmp/ksfaudit/`,
    `/tmp/letta/`, `/tmp/memlane2/`.
  - Another process cleaned `/tmp` TWICE mid-session, deleting files during active runs
    ("output file could not be read (ENOENT) ... another Claude Code process in the same project
    deleted it during startup cleanup").
  - 8 lane reports existed ONLY in `/tmp` and were rescued to `fleet/handoff-notes/` by luck of
    timing, not design. Losing them would have destroyed the best artifact of the session.
  - A session-isolated scratchpad ALREADY EXISTS and was used early in the session, then abandoned
    in favour of bare `/tmp`. The tool was available and the convention simply was not enforced.

  ## FRAMING (hypothesis — TEST IT, overturn loudly if wrong)
  The manager believes the right fix is: split QUERY from CLAIM in the allocator, make re-asserting
  your own claim a no-op, reap orphaned claims, and make namespaced scratch the ONLY path lanes can
  take. **Unverified**: it is possible the allocator's mutate-on-read is deliberate (a
  race-avoidance measure for concurrent sessions), in which case the correct fix is a
  `--check` / `--claim` split plus an idempotent re-claim, NOT removing the atomic write. Read the
  script's own rationale before changing its semantics.

  ## WHAT TO BUILD
  1. **Allocator**: separate `check` (pure, no mutation) from `claim` (mutates). Re-claiming a name
     you already hold is a SUCCESSFUL NO-OP, not a refusal. Reconcile the two "in use" definitions
     into one shared predicate used by both `claim-jedi-name.sh` and `handoff.sh`.
  2. **Orphan reaping**: a claim marker with no corresponding `SESSION-HANDOFF-<name>.md` after a
     threshold is released back to the pool. Report how many names are currently leaked —
     `rey-skywalker` is at least one.
  3. **Scratch namespacing**: `spawn-worker.sh` derives a per-run scratch dir
     (`<base>/<name>-<UTC-stamp>-<pid>` or the session scratchpad) and passes it to the lane.
     **Bare `/tmp` must not be reachable by default.** Deliverables land in-repo; scratch is scratch.

  ## GUARDS
  - Do NOT weaken concurrency safety to gain idempotence — two sessions must still never get the
    same name. Prove that with a test.
  - Do NOT auto-delete anything under a scratch dir that is not provably this run's.
  - `spawn-worker.sh` carries a verified focus-fix (the quoted standalone `';'` before `focus-tab`),
    a free-tier model refusal, a readiness gate and a start-verifier. Do NOT "simplify" any of them.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline. Each must go RED on the named revert, then GREEN:
    a. `check` twice in a row does NOT consume a name (mutate-on-read regression)
    b. `claim` then re-`claim` of the SAME name by the SAME holder = success, not refusal
    c. two concurrent claimers NEVER receive the same name (anti-over-fix)
    d. a claim marker with no handoff file past the threshold is reaped; one WITH a file is NOT
    e. `spawn-worker` writes scratch under a per-run namespaced path, never bare `/tmp`
    f. FAIL-CLOSED: unreadable pool/marker store refuses to issue a name rather than issuing a
       possibly-duplicate one
  Then run the real allocator and report the leaked-name count before/after.

## Dependencies & Sequence
  - Depends on: nothing.
  - Blocks: nothing, but every future session pays the tax until it lands.
  - Related: STOP-WORKER-GRACEFUL-EXIT (#283) also owns `fleet/spawn-worker.sh`'s sibling
    `stop-worker.sh` — disjoint files, but coordinate if both are in flight.
