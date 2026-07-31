# CLAIM-RECONCILE-TRIAGE — Phase 1 Root-Cause Report

Date: 2026-07-27
Session: qui-gon-jinn

## ROOT-CAUSE VERDICT: (a) — Inert (never invoked)

**Primary:** The reconciler `fleet/reconcile-stale-claims.sh` was built, tested, merged to
master (three-dot diff `master...feat/stale-claim-reconcile` = EMPTY), and marked DONE
— but it is **never called by anything**. Zero references outside its own file and its
test (`fleet/tests/reconcile-stale-claims.test.sh`). Not wired into preflight, not
wired into the SessionStart hook, not wired into any gate, cadence, cron, or trigger.

Evidence: `grep -rn "reconcile-stale-claims" fleet/ --include="*.sh" | grep -v "reconcile-stale-claims\.sh" | grep -v "reconcile-stale-claims\.test\.sh" | grep -v handoff-notes` returns zero matches.

The only live reference is in `fleet/handoff-notes/salvage-reap-2026-07-26/rig-ISSUE-BOARD-DEMO.issue-board.sh`
which is an **archived issue-board demo** — not a production trigger. The `DESIGN-SG-ISSUE-CONTROL-PLANE.md`
lists it as "BUILT [V]" but that's a design doc, not an invocation site.

**Secondary (format drift):** Even if invoked, the reconciler parses claims in the old
`<droid-id> <timestamp>` format (`reconcile-stale-claims.sh:79`). All 15 current claim
files use the **session-bridge key-value format** (`ticket:`, `session:`, `worktree:`,
`heartbeat:`, `claimed:`). Every claim would be SKIPPED with "format drift"
(`reconcile-stale-claims.sh:80-83`). So (a) AND (c) are both true — the reconciler is
inert AND would fail if called.

The related `fleet/stale-check.sh` is also inert — its own comment at line 91 says:
"standalone check — preflight.sh should call this; not wired in here". Both scripts
landed without wiring.

## CLASSIFICATION TABLE — 15 Stale Claims

| # | Ticket | Repo | Branch | 3-dot Diff | Done Mkr | Worktree | Origin | Class |
|---|--------|------|--------|-----------|----------|----------|--------|-------|
| 1 | BRIDGE-REPLACE-PHASE1 | c-p | feat/bridge-replace-phase1 | EMPTY | NO | clean, on-branch | none | DONE-RELEASE |
| 2 | D24-SESSION-CTL-SPIKE | c-p | spike/session-ctl | EMPTY | NO | clean, on-branch | none | DONE-RELEASE |
| 3 | DOGFOOD-GATE | charon | feat/dogfood-gate | EMPTY | NO | clean | none | DONE-RELEASE |
| 4 | INERT-STARTUP-CHECK | charon | feat/inert-startup-check | EMPTY | NO | clean | none | DONE-RELEASE |
| 5 | LAND-GATE-RIG-SUITE | c-p | fix/land-gate-rig-suite | EMPTY | NO | clean, on-branch | 0 unpushed | DONE-RELEASE |
| 6 | PREFLIGHT-OWNS-ARBITRATE | c-p | fix/preflight-owns-arbitrate | EMPTY | NO | MAIN checkout, dirty(unrel) | none | DONE-RELEASE |
| 7 | REGISTRY-META-CATALOG | c-p | feat/registry-meta-catalog | EMPTY | NO | clean, on-branch | 0 unpushed | DONE-RELEASE |
| 8 | RIG-BRANCH-16-DEEPDIVE | c-p | fix/rig-branch-16-deepdive | EMPTY | NO | clean, on-branch | none | DONE-RELEASE |
| 9 | SW-PHASE0-GRADE-READ | c-p | fix/sw-phase0-grade-read | EMPTY | NO | clean, on-branch | none | DONE-RELEASE |
| 10 | WORK-LEASE-WORKTREE-RESOLVE | c-p | fix/work-lease-worktree-resolve | EMPTY | NO | clean, on-branch | 0 unpushed | DONE-RELEASE |
| 11 | LITELLM-COST-FIELD-FIX | charon | fix/litellm-cost-field-test | NON-EMPTY* | YES | clean | 0 unpushed | DONE-RELEASE |
| 12 | SECRET-HOTROTATE | charon | fix/secret-hot-rotation | NON-EMPTY* | NO | clean | 0 unpushed | DONE-RELEASE |
| 13 | SW-IDENTITY-FOLD | charon | fix/sw-identity-fold | NON-EMPTY* | NO | clean | 0 unpushed | DONE-RELEASE |
| 14 | SW-STATIC-LEGS-RETIRE | charon | feat/sw-static-legs-retire | NON-EMPTY* | NO | clean | 0 unpushed | DONE-RELEASE |
| 15 | GW-CUTOVER-LIVE-WIRE | charon | feat/gw-cutover-live-wire | NON-EMPTY | NO | clean, on-branch | 0 unpushed | **LIVE-WORK-PRESERVE** |

*Tickets 11-14: three-dot diff is non-empty, but ALL files are byte-identical between
branch and master (verified via two-dot `git diff master <branch> -- <file>` returning
empty for every owned file). Content landed via re-derivation with different commit SHAs.

### Per-row evidence

**DONE-RELEASE (14 tickets):** Branch is ancestor of master (three-dot empty) OR all files
byte-identical. Worktrees are clean with no uncommitted changes. Origin refs either absent
(all content already in master) or 0 commits ahead. Claim files are pure residue.

**DOGFOOD-GATE (d6267c3) + INERT-STARTUP-CHECK (6ab6035):** Confirmed landed in master
today. Both have no done-marker — the done-marker write path is ALSO missing. A separate
sub-finding but same root cause: no automation runs `done.sh` on merge.

**LITELLM-COST-FIELD-FIX diagnostic:** Has a done-marker (2026-07-24 22:26 UTC) AND a
claim file (mtime 2026-07-26 17:25 UTC — AFTER the marker). `done.sh:148` does
`rm -f "$S/claims/$id"`, so the claim was either removed then re-written, or the session-
bridge MCP claim mechanism wrote a new claim on top of the old one. Either way: a
done-marker does NOT guarantee the claim is gone. The session-bridge claim store and the
file-system claim store operate independently.

**PREFLIGHT-OWNS-ARBITRATE:** Claim's worktree field is `/home/stack/charon-private` —
the MAIN checkout, not a dedicated worktree. This is an anti-pattern: the main checkout
is never "done" with a single ticket, so the claim appears permanently stale.

**LIVE-WORK-PRESERVE (1 ticket):**
- **GW-CUTOVER-LIVE-WIRE:** Commit `064d197` contains a 317-line guard-test file
  (`tests/test_gw_cutover_live_wire.py`) that does NOT exist in master. This is an
  intentional STOP — the commit message says "do NOT cut over — land the guards, not the
  wire-in". The guard tests document why the cutover cannot proceed and may be needed
  when the cutover is retried. Releasing this claim would orphan unlanded work.

## CLASS FIX PROPOSAL

The reconciler must be wired to actually run. Two independent defects to fix:

1. **Wire `reconcile-stale-claims.sh` into preflight's `scan` chain** (`preflight.sh:958`).
   This ensures every `fleet-droid.sh` preflight run and every manager `preflight.sh scan`
   reconciles stale claims. The reconciler's default is DRY-RUN — it will preview but never
   mutate, making it safe to add to a live path.

2. **Teach the reconciler to read the session-bridge claim format.** The `work-lease.sh`
   `claim_epoch()` function (`work-lease.sh:126-130`) already reads BOTH formats. Adopt
   the same dual-format strategy in the reconciler so it can parse the current claim files.

3. **Reuse the bridge's existing staleness signal** (requirement from brief). The
   session-bridge daemon already computes `stalled`/`stall_seconds` per session (daemon.py:296-301).
   If we can query the daemon, we have liveness ground truth without a second PID-check.
   Alternative: the existing `kp` (key-present) check for the worktree's claim file relies
   on the heartbeat field, which work-lease.sh already reads.

### Wiring location

`preflight.sh:958` — add `bash "$HERE/reconcile-stale-claims.sh"` (dry-run default)
in the scan chain, before `retire-done.sh`. This is the correct position because:
- It runs AFTER `reconcile-merged.sh` (tickets that just merged get their done markers)
- It runs BEFORE `retire-done.sh` (which archives DONE tickets and removes worktrees)
- A stale claim with a done marker will be cleaned up before the retire sweep

### What NOT to touch

- `fleet/status.sh` — owned by no single ticket but too many consumers
- `fleet/validate_board.sh` — owned by 5+ tickets (CREATION-GATE-DECOMPOSE-WIRE,
  PROJECT-MEMBERSHIP-GATE, REPO-FIELD-REQUIRED, REPO-MAP-CONVERGE, TIER-BALANCE)
- `fleet/claim.sh` — owned by CREATION-GATE-DECOMPOSE-WIRE
- `fleet/checks/rig-ci-scope.sh` — owned by HANDOFF-GATE-NONBYPASSABLE, TIER-BALANCE

All four are contended by tickets in various states. The fix stays within
`fleet/reconcile-stale-claims.sh` (already owned by STALE-CLAIM-RECONCILE) and adds
one line to `fleet/preflight.sh` (checking owns: PREFLIGHT-OWNS-ARBITRATE, DONE,
lands fix/preflight-owns-arbitrate which is ancestor of master — uncontended).

## RELATED: stale-check.sh is ALSO inert

`fleet/stale-check.sh` detects stalled sessions via claim-marker mtime and quarantined
tickets via loop-guard markers. Its own comment at line 91 notes it should be wired
into preflight but isn't. This is a SEPARATE issue (noted for manager attention)
because it touches claim/loop-guard files owned by other tickets. The fix for
`reconcile-stale-claims.sh` does not depend on `stale-check.sh`.

## PROPOSED RELEASE LIST (sign-off required)

14 tickets classified DONE-RELEASE — safe for claim release under `--apply`. Ordered
by age:

| Ticket | Age | Notes |
|--------|-----|-------|
| REGISTRY-META-CATALOG | 59h | Landed, clean worktree |
| GW-CUTOVER-LIVE-WIRE | — | LIVE-WORK-PRESERVE — do NOT release |
| LAND-GATE-RIG-SUITE | 49h | Landed, clean worktree |
| WORK-LEASE-WORKTREE-RESOLVE | 54h | Landed, clean worktree |
| PREFLIGHT-OWNS-ARBITRATE | 15h | Landed, main-checkout anti-pattern |
| SW-IDENTITY-FOLD | 15h | Landed, byte-identical files |
| SECRET-HOTROTATE | 12h | Landed, byte-identical files |
| SW-STATIC-LEGS-RETIRE | 12h | Landed, byte-identical files |
| LITELLM-COST-FIELD-FIX | 6h | Done-marker + claim desync |
| SW-PHASE0-GRADE-READ | 6h | Landed, clean worktree |
| RIG-BRANCH-16-DEEPDIVE | 6h | Landed, clean worktree |
| D24-SESSION-CTL-SPIKE | 6h | Landed, clean worktree |
| DOGFOOD-GATE | 4h | Landed d6267c3, no done-marker |
| INERT-STARTUP-CHECK | 4h | Landed 6ab6035, no done-marker |
| BRIDGE-REPLACE-PHASE1 | 3h | Landed, clean worktree |
