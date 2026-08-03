# LAUNCHER-LEAKGUARD-NONFATAL — Review Log

## Ticket
Treat leak-guard refusal as a per-ticket non-fatal outcome. PR #366 (FRONTIER-TAB-DEATH)
landed the push-before-cleanup half; this documents the non-fatal half and the
structural fix needed.

## Symptoms (measured 2026-08-02, five frontier tabs)

1. A droid session commits work, the tab then reaches cleanup, and `safe_worktree_remove`
   REFUSES (correctly — the worktree has commits not on any remote).
2. Log shape: `leak-guard: REFUSING to remove … Nothing removed` →
   `cleanup: worktree KEPT` → tab exits.
3. The `--wait` / `--retries` budget is never consumed — the tab dies mid-cycle
   rather than releasing one claim and claiming the next ticket.

The refusal is CORRECT and must NEVER be weakened — it is the last thing standing
between a real commit and an `rm -rf`. The defect is the launcher's *reaction*:
it treats a per-ticket cleanup refusal as a terminal event for the entire
self-feeding tab.

## Root cause — structural, not line-level

After PR #366, the gate no longer unwinds the tab under `set -e` (see
`fleet/tests/launcher-gate-sete-kill.test.sh`), and `preserve-unpushed.sh` publishes
committed-but-unpushed work *before* `safe_worktree_remove` is consulted. This closes
the common case: the publish empties the "not on any remote" condition, and the guard
allows removal.

The remaining defect is in the *placement* of worktree cleanup:

- The ONLY worktree-removal path is the EXIT trap `cleanup()` at
  `fleet/fleet-droid.sh:888-957`.
- In the happy path, `current=""` is set by the submit/release block
  (lines 1486, 1491, 1494), so the EXIT trap's `[ -n "${current:-}" ]` guard at
  line 905 is **always false at normal stand-down**. Worktree cleanup is skipped
  entirely for successfully-submitted tickets; worktrees accumulate on disk
  indefinitely.
- The cleanup block (lines 905–956) only fires when the tab dies *mid-ticket*
  with `current` still set (signal, `set -e` unwind, terminal close). That is
  the case the EXIT trap was designed for, and in that case `safe_worktree_remove`
  *correctly* refuses — the worktree has work that was never published.

Because there is no per-ticket cleanup in the main loop (the `while true; do …
done` at lines 1119–1514), every worktree is deferred to the EXIT trap, and the
EXIT trap skips them. When the tab *does* fire the EXIT trap mid-ticket (for
any reason), the refusal is fatal *because the tab was already exiting* — the
trap cannot "continue" the loop.

## Design

### 1. Add per-ticket worktree cleanup to the main loop

After each ticket's submit/release block, insert a call to `safe_worktree_remove`
for the *just-completed* ticket. This runs while the loop is still alive, so a
refusal is genuinely non-fatal: it logs, flags the manager, releases the claim
if safe, and the loop continues to the next ticket.

**Location A** — after successful submit (lines 1485–1492), before `current=""`:

```bash
# Clean up the just-submitted ticket's worktree (non-fatal).
if safe_worktree_remove "$REPO" "$wt" "$id" "$FLEET/state/needs-push"; then
  git -C "$REPO" worktree prune 2>/dev/null || true
else
  echo "[$DROID] $id: worktree KEPT (refusal above) — flagged for manager. Claim stays submitted; worktree will be reclaimed by reaper."
fi
```

When the push + submit succeeded, the branch is on the remote and the needs-push
marker was cleared by `submit.sh`. `safe_worktree_remove` will allow removal
(exit 0) — this is the routine cleanup that the EXIT trap currently never
performs.

**Location B** — after `submit.sh` failure (lines 1487–1492), before
`current=""`:

The needs-push marker is live. `safe_worktree_remove` will REFUSE (exit 2).
The refusal is logged, the claim is preserved via the needs-push marker, and
the loop continues. The worktree stays on disk, which is correct: the work is
committed but unlanded, and the marker already tells the manager exactly what
to do (`fleet/land-needs-push.sh`).

**Location C** — after the droid failure path (lines 1493–1513), before
`current=""`:

The claim is released at line 1494. Run `safe_worktree_remove`; if the droid
left no changes, removal succeeds. If it left stray changes, the refusal
preserves the worktree. The ticket is already released and re-claimable;
the leftover worktree is inspected by `fleet/checks/stranded-work.sh`
(landed PR #361).

### 2. The EXIT trap remains as a last-resort safety net

The EXIT trap `cleanup()` at lines 888–957 remains unchanged. It is the
safety net for a tab that is genuinely killed (SIGKILL, terminal close,
OOM, `set -e` unwind in a path we haven't yet hardened). In that case the
refusal is still CORRECT — the worktree must not be destroyed — and the
manager recovers via the needs-push marker.

The difference: because the main loop now cleans up after itself on every
ticket, the EXIT trap is almost never the *primary* cleanup path, and a
refusal there is the exception, not the routine outcome.

### 3. Flagging for the manager

Every refusal path in the main loop writes a durable record to
`$FLEET/state/leak-guard-refusals/$id` with the reason, the worktree path,
and the branch. This is additional to the needs-push marker: a refusal that
is NOT work-related (e.g. the target fails `_lg_wt_catastrophic`) would not
already have a needs-push marker, so the refusal record ensures the manager
can see *why* a worktree was kept even when the reason is not "unlanded
commits."

The reaper (`fleet/reap-orphans.sh`) already knows how to distinguish
"needs landing" from "needs inspection" and can fold this new refusal marker
into its sweep without modification.

## What this does NOT do

- Does NOT weaken leak-guard. Every call to `safe_worktree_remove` is
  unmodified; the guard's refusal logic and the `_lg_wt_catastrophic`,
  `_lg_wt_target_ok`, and needs-push checks are untouched.
- Does NOT change the claim lifecycle. The claim is released by the existing
  submit/release paths exactly as today. The worktree cleanup is a separate
  concern that runs *after* the claim decision.
- Does NOT change what the EXIT trap does. The trap's cleanup code is
  preserved verbatim.

## Fail-on-revert check

The new per-ticket cleanup path should be fail-on-revert tested by extracting
the loop body (as `preserve-unpushed.test.sh` does for the EXIT trap) and
running it against a fixture that leaves a live needs-push marker. The
assertions:
1. `safe_worktree_remove` returns 2 (REFUSED) — the worktree survives.
2. The refusal message is written to the refusal-marker file.
3. The loop shell does NOT exit (the tested function returns 0).
4. A fixture with a published branch (no unpushed commits) is removed cleanly.
