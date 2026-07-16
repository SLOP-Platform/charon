# STARTUP-FRICTION-LOG — durable cross-session boot-problem memory

**Purpose:** stop rediscovering the same startup problems. Each session APPENDS (token-lean, ~6 lines)
the frictions it hit at boot + whether they're now mechanized or still open. A NEW session's FIRST
actions: (1) read this file, (2) run the listed boot checks, (3) FIX/improve any recurring item,
(4) append its own entry at session end. Append-only; newest on top. Keep entries terse.

## BOOT CHECKLIST (do these first, every session — derived from repeated frictions below)
1. `SESSION=<name> bash fleet/handoff.sh` reads latest `SESSION-HANDOFF-*.md` (all of them).
2. `git -C /home/stack/charon-private pull --ff-only` AND same for `/home/stack/code/charon` (local masters DRIFT). Use the BARE form (no `origin master`) — passing an explicit refspec after a prior `git fetch origin master` leaves multiple for-merge entries in FETCH_HEAD and trips `fatal: Cannot fast-forward to multiple branches`. Bare uses the upstream tracking ref and never trips it.
3. `charon providers list` runs (CLI shim can silently die). Provider truth is the GATEWAY (4-LOM), not local `~/.charon`.
4. **`bash fleet/foreman.sh`** — the #1 fix: it surfaces tier starvation + WHY (quarantine/parked/unmarked-dep/collision/undecomposed) LOUDLY. Run it before assuming the board is healthy.
5. `bash fleet/foreman.sh --fix` clears provably-safe stale blocks (quarantines that pass the decomp gate; merged-unmarked deps). Never auto-unparks.
6. Money/important/routing PRs get a FOCUSED ADVERSARIAL REVIEW before land — not just gate-green.
7. **Process-health / runaway check (NEW):** `ls /proc | grep -cE '^[0-9]+$'` (abnormally high ⇒ runaway) and `ps -o cmd= -C bash | grep -cE 'fleet/(handoff|gate|tests/handoff-mechanize)'` (>0 ⇒ orphaned self-check FORK-BOMB left by a crashed session). If found: `pkill -STOP` the loop first (uncatchable ⇒ it can't fork), then `-KILL`; if it self-multiplies faster than kills land, stub the cycle-edge scripts (they're git-committed) to `exit 0`, kill, then `git checkout` to restore. See fleet-selfcheck-forkbomb-class.

---

## post-crash restart / "recover-session" (2026-07-16)
- **#1 — a Claude-Code crash orphaned a FORK-BOMB runaway that SessionStart did NOT detect.** `handoff.sh`→`gate.sh`→(runs the test suite)→`handoff-mechanize.test.sh`→`handoff.sh` is a concurrent, exponential cycle; orphaned by the crash it reached ~18,900 procs (load >2000, `fork: retry: Resource temporarily unavailable`). Boot was fork-starved before I noticed. → FIXED: reentrancy guard (`gate.sh` exports `CHARON_GATE_ACTIVE`; `handoff.sh` skips its embedded gate when set — commit 9dfc85a; adversarially reviewed). The SAME recursion also blew the GitHub GraphQL cap. Boot-checklist #7 added to catch it next time.
- **Stale root HANDOFF.md misled recovery:** the top-level `HANDOFF.md` was months stale (GitLab/mvp-routing); real state was in `fleet/state/` + `SESSION-HANDOFF-*`. Don't trust the root file. (OPEN: archive/date it.)
- **Crash-orphaned claims/worktrees:** 9 dead-PID claims blocked tickets; in-flight SG-tab work had to be reconstructed from `state/claims|submitted|done` (no single in-flight snapshot). reap-orphans (DROID-LIFECYCLE-REAP) + SessionStart wiring both in-flight; until then, at boot scan `state/claims/*` for dead owner PIDs (`kill -0`).
- **foreman low-water still not auto-firing:** the loud STARVE/LOW warning (`foreman.sh`) exists but its SessionStart/after-land/cadence wiring is FOREMAN-MULTI-TRIGGER (in-flight) — starvation was found manually again. Run `bash fleet/foreman.sh` at boot until it auto-fires.
- **Operator-action host confusion:** a grader `sudo` command was first run on 4-lom (gateway box) instead of the LOCAL WSL box (Tardis). Operator-action commands MUST name the host; bench-grader is LOCAL-WSL only.
- **done.sh false-close + wrong-repo:** reconciling `submitted/`, done.sh false-closed an open-PR ticket (owns-files heuristic) and defaulted a rig ticket to the product repo (empty `repo:` field). Ticketed DONE-SH-INTEGRITY-FIX.
- **Decomposer dead-ended on 429 with ~20 providers idle:** static GLM-family slate, no switchboard routing. Ticketed DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD; architecture recorded in ADR-0011 (the Switchboard: no pools/lists).

---

## (next session — post-cere-junda, 2026-07-16)
- **multi-FETCH_HEAD FF error (operator-flagged, FIXED):** `git pull --ff-only origin master` after a separate
  `git fetch origin master` trips `fatal: Cannot fast-forward to multiple branches` (FETCH_HEAD holds multiple
  for-merge entries) even when the repo IS current. Harmless (repo was at origin/master) but noisy. → Boot-checklist
  line 2 now uses the BARE `git pull --ff-only` (upstream-tracking, single ref). Verified clean (EXIT 0).
- **GraphQL exhausted at boot (0/5000, REST core fine at 4999/5000):** `gh pr list --json` uses GraphQL and hard-fails;
  route PR listing through REST (`gh api repos/OWNER/REPO/pulls`) or `fleet/gh-cache.sh`. Check `gh api rate_limit --jq .resources` first.

## cere-junda (2026-07-16)
- **#1 recurring: silent tier-starvation.** Tabs starved for a long time before I found the cause: a
  15-ticket loop-guard quarantine wave + parked-stale tickets + merged-but-unmarked deps + splittable-
  unjustified tickets re-quarantining (incl. the P0 DELETE-STATIC-RANK). Manual diagnosis was slow.
  → MECHANIZED this session: `fleet/foreman.sh` (tested 8/8, wired into `preflight.sh` scan). RUN IT FIRST.
- **Board rot:** many merged PRs never done-marked → dependents falsely blocked; 21 done tickets still on
  board. → `land.sh` now auto-done-marks on verified merge; `done.sh` is repo-aware + O(1); RECONCILE-HELD-MARKERS + retire-done clear the rest.
- **Config-siloing:** `charon providers list` (local) showed only 3 providers → I wrongly called the pool "thin";
  the GATEWAY has 11 keyed. Always check the gateway, not local. (CONFIG-SSOT-PROPAGATE ticket open.)
- **GitHub limits:** burst lands tripped the SECONDARY content-creation limit (not the hourly one). → `fleet/gh-cache.sh`
  batches merged-PR lookups (O(repos) not O(tickets)); `land.sh` now paces merges. `gh api rate_limit` gives exact reset (free call). GITHUB-LIMITS-HARDENING ticket open (search-API 30/min, large-file guard).
- **handoff.sh is fragile:** timed out / errored generating the handoff this session — the generator itself needs hardening (a repeated "incomplete handoff" complaint). OPEN.
- **Adversarial-review gap:** in a fast-land batch I leaned on gate-green and skipped focused review of money-path
  code (DELETE-STATIC-RANK). Instituted the rule (boot-checklist #6) + ran a post-land adversarial review.
