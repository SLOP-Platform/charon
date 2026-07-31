# ORPHAN-CLAIM-FORENSICS — review notes (per-ticket fragment)

**Ticket:** ORPHAN-CLAIM-FORENSICS
**Branch:** fix/orphan-claim-forensics
**Date:** 2026-07-31
**Session model:** minimax-m3 (charon worker, Jedi-name ahsoka-tano)

## Result

`fleet/reconcile-stale-claims.sh` extended with a `--orphans` flag that classifies every
orphan marker (`state/claims/<id>`, `state/submitted/<id>`, `state/done/<id>` whose id
has no board ticket) into three buckets:

- **residue-safe-to-clear** — has merge-proof (done-marker `merged:*` or `override:*`)
  OR a branch tip ancestor of master in charon / charon-private / the worktree's own repo.
- **work-at-risk** — clean but unpushed worktree, OR no worktree path + branch exists but
  not yet ancestor of master. NEVER cleared.
- **unknown** — no worktree path, no matching branch, no merge-proof. NEVER cleared.

## LIVE FORENSICS — verified 2026-07-31

`bash fleet/validate_board.sh` reports **39 orphan-marker REDs** today. My classifier
breaks them down:

| Bucket | Count | Sub-bucket |
|--------|-------|------------|
| `residue-safe-to-clear` | 32 | 7 claims + 4 submitted + 21 done |
| `work-at-risk` | 7 | 4 caught by legacy worktree-guard (unpushed); 3 caught by new orphan classifier (clean + branch exists but not on master) |
| `unknown` | 0 | — |

Per-marker confirmation (live fleet, dry-run):

- **residue — claims** (7): DOGFOOD-GATE, INERT-STARTUP-CHECK, LAND-GATE-RIG-SUITE,
  REGISTRY-META-CATALOG, RIG-BRANCH-16-DEEPDIVE, SW-PHASE0-GRADE-READ,
  WORK-LEASE-WORKTREE-RESOLVE — each has a clean worktree whose HEAD is ancestor of
  master; branch was merged and the ticket file vanished (merge-drop mechanism).
- **residue — submitted** (4): BOUNCE-1, KS29-DISCOVERY-LEG, SG-ISSUE-CONTROL-PLANE,
  UNIFIED-PLANE-CANARY-FRAMEWORK — each has a ref in charon-private (or
  charon for UNIFIED) whose tip is ancestor of master; bare submitted timestamp;
  ticket was archived by merge-drop.
- **residue — done** (21): ALL 21 done-markers carry merge-proof. Sample:
  FLEET-DEMAND-BROKER -> `merged:#264`, BRIDGE-REPLACE-PHASE1 -> `merged:3b7d9a5`,
  CLAIM-INTEGRITY-TOOL-ADOPT -> `override:RED-LINE...`, BRIDGE-PROXY-HEARTBEAT ->
  manager-verified override for code living outside charon-private.
- **work-at-risk (legacy guard, unpushed)** (4): BRIDGE-MIGRATE-DROID-CLIENT,
  LITELLM-CAPABILITY-ADOPTION, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-OWNS-ARBITRATE —
  clean worktrees exist but `git -C "$wt" rev-list --count HEAD --not --remotes` is
  non-zero. The legacy worktree-guard (lines 333-353) holds these correctly; my
  orphan branch never sees them.
- **work-at-risk (orphan classifier, stranded branch)** (3): SECRET-HOTROTATE,
  SW-IDENTITY-FOLD, SW-STATIC-LEGS-RETIRE — clean + fully-pushed worktrees, but their
  HEAD is NOT ancestor of master in any configured repo. These are REAL abandoned
  work: branches exist with unlanded commits that the operator must decide to land
  or retire. NEVER auto-cleared.

## RED-then-GREEN proof

The new tests (j)–(r) fail when the orphan walker is disabled (19 fails out of 19
orphan tests). With the walker enabled: ALL 62 PASS. The script's `set -uo pipefail`
plus `bash -n` syntax-check both pass.

Test seam preservation: `RECONCILE_FLEET_DIR`, `RECONCILE_STALE_S`,
`VERIFY_MERGED_FIXTURE`, `DONE_MERGED_SRC`, `DONE_CHARON_REPO` are unchanged. Two new
seams were added because the orphan classifier NEEDS the repo roots (no other seam
exposes them): `RECONCILE_CHARON_REPO`, `RECONCILE_RIG_REPO` — both default to
`/home/stack/code/charon` and `/home/stack/charon-private` respectively, exactly
mirroring the env-var ROOT convention.

## LIVE board impact

Before: 39 orphan-marker REDs (`bash fleet/validate_board.sh`).
After `bash fleet/reconcile-stale-claims.sh --orphans --apply`: 7 orphan-marker REDs.

The remaining 7 are the work-at-risk set:
```
state/claims/PREFLIGHT-OWNS-ARBITRATE
state/claims/SW-STATIC-LEGS-RETIRE
state/claims/LITELLM-CAPABILITY-ADOPTION
state/claims/SW-IDENTITY-FOLD
state/claims/BRIDGE-MIGRATE-DROID-CLIENT
state/claims/SECRET-HOTROTATE
state/claims/PREFLIGHT-GATE-REGISTRY
```

These have LIVE BRANCHES with unlanded commits — they CANNOT be auto-cleared without
destroying real work. Each requires an operator decision (land the branch via PR; or
explicit `done.sh <id> --override "<reason>"` to retire the work; or remove the worktree
manually after inspection). This is the correct fail-closed posture.

## Discovered-but-out-of-scope — surface, don't fix

The forensics corroborated the prior session's finding: **the merge-drop mechanism
guarantees a 40th orphan until the merge path stops dropping board files.** This is
the same divergence-by-construction the handoff gate 5b root-caused. Suggested
follow-up ticket (separate from this one):

- `ticket: BOARD-FILE-MERGE-DROP-FIX` — gate `board-lock.sh commit` AND the merge
  path (origin-side `gh pr merge` or equivalent) such that ADDED board files on the
  local master survive a subsequent sync. Today the handoff `commit-and-push` model
  writes bare onto local master; the merge wrapper resolves to the side lacking the
  file. Until that path is fixed, ANY new ticket added via the lock is at risk of
  becoming the 40th orphan as soon as a sync happens.

Other untriaged RED surfaced in this work (separate ticket, also out-of-scope):
- `fleet/claim-jedi-name.sh` dies: `pool file not found: fleet/state/jedi-name-pool.txt`.
  File added in 5d42cd5; absent from working tree (same disappearance shape as the
  board tickets above).

## Self-checks

- `git status -s` — only 2 modified files, both inside the ticket's `owns:` line
  (`fleet/reconcile-stale-claims.sh`, `fleet/tests/reconcile-stale-claims.test.sh`).
  This fragment is `docs/review-log/ORPHAN-CLAIM-FORENSICS.md` (also explicitly
  ticket-local; never touches the shared `docs/REVIEW-LOG.md`).
- `bash -n fleet/reconcile-stale-claims.sh` -> exit 0.
- `bash fleet/tests/reconcile-stale-claims.test.sh` -> PASS=62 FAIL=0.
- Pre-existing pytest failures on master (test_capture_pipeline,
  test_tier_classify) are unchanged and unrelated to this ticket.
