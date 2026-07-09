# Charon fleet — manager RUNBOOK (handoff)

> **ROLE (read first):** The MANAGER session watches + gates ONLY. It NEVER launches
> droids (no `fleet-droid.sh`/`claude --bg` from the manager). The OPERATOR opens droid
> tabs. See memory `manager-never-spawns-droids`. First acts of a fresh session: read
> `MEMORY.md` + `docs/DECISIONS.md`, run `status.sh` + `board.sh`, then resume gating.
>
> **PRE-WAVE GATE (added 2026-06-27 after the capacity.py double-claim + E10 missing-prompt):**
> run `bash validate_board.sh` BEFORE naming any tab to launch. RED = a missing prompt, a
> double-claimed path, a bogus dep, or a colliding branch — fix first. Ownership lives in ONE
> place (`board/<id>.md` `owns:`); prompts must NOT restate a wider file list. Root cause was
> dual, hand-authored, never-cross-checked ownership specs.

## State as of 2026-06-27
- Merged: N1,N2,T7,T8,N4,N5 + ADRs/Decision-Register + **E0** (boundary guard).
- **OPEN but CI-RED (do NOT merge as-is):**
  - **S1 (#22)** — fails `ruff` lint in `tests/test_config.py` (E402 + import sort). Code otherwise fine.
  - **E1 (#23)** — fails E0's boundary scan, but **E1's code is CORRECT** (standard relative imports `from .board`/`from ..ledger`). Root cause = a bug in E0's `check_boundary.py` (doesn't allow relative imports). Fix = ticket **FB1**.

## Recovery (do this first)
1. **FB1** (ready, sonnet) → fixes `check_boundary.py` to allow relative imports. Open 1 sonnet tab. Gate + merge + `done.sh FB1`.
2. **E1** → after FB1 merges, E1 needs the fix on its branch. Cleanest: close PR #23, `release.sh E1`, re-run E1 (1 opus tab) off updated master. (No-waste alt: merge master into `feat/engine-board-claim` to pull FB1, re-run CI, merge.)
3. **S1** → close PR #22, `release.sh S1`, re-run S1 (1 sonnet tab). (No-waste alt: push a `ruff --fix` commit to `feat/sandbox-policy`.)

## Launch sequence (one-line; "open N <tier> tab(s)" = operator action)
Each tab runs `bash /home/stack/charon-private/fleet/fleet-droid.sh <tier>`; the droid
auto-loads the ticket prompt via the board. A ticket unblocks only AFTER the manager
merges + `done.sh` its dependency (propose-default).

| After manager merges | Now eligible | Operator opens | Concurrency |
|----------------------|--------------|----------------|-------------|
| FB1 | E1 (re-run) | 1 opus | 1 |
| E1 | E2 | 1 opus | 1 |
| E2 | **E3**(sonnet) · **E4**(opus) · **E10**(opus) | 1 sonnet + 2 opus | **3 (peak)** |
| E4 | E6 | 1 opus | 1 |
| E6 | E8 | 1 opus | 1 |
| E8 | E9 | 1 opus | 1 |
| E9 | E7 | 1 sonnet | 1 |
| (anytime) | S1 (re-run) | 1 sonnet | parallel |

Peak useful parallelism = **3** (E3+E4+E10 after E2). Elsewhere 1 opus is the ceiling —
the critical path is sequential and dependents unblock only on the manager's merge.

## Two-opus / pre-staging note
`fleet-droid.sh` does NOT idle-wait: if no ticket is eligible for its tier it stands down
(exits) immediately. So a pre-launched 2nd opus tab won't "wait" for E2 — it exits. To get
"ready the instant it ungates," either (a) open the 2nd opus tab the moment E2 merges, or
(b) add a `--wait` poll mode to fleet-droid.sh (on empty claim: sleep+retry instead of
break; idle tab just sleeps, no claude session until it claims). (b) is a small rig tweak —
operator-approved before changing the harness.

## Deferred (NOT ticketed, by decision) — see docs/DECISIONS.md
D005 WorkerBackend port (until a non-ACP worker); D015 verified isolation (promote as the
safety pair for auto-land/Phase-2 per D016).

## Release + redeploy runbook (durable steps — salvaged 2026-07-08 from REDEPLOY-PLAN.md)
The version-specific REDEPLOY-PLAN snapshot (v0.3.3→v0.3.4) was archived; these are the
version-independent steps that recur every release.

**Config/secrets live ON the named `/data` volume, not in the image.** The remote
`docker-compose.yml` mounts `charon-config:/data` (external volume `charon_charon-config`);
`/data/pools.json` + `/data/secrets.json` persist across image swaps. A normal `compose up -d`
never touches `/data` content — never bake config/secrets into the image (see memory
`charon-deploy-drift-lessons`).

**Release path:** bump `pyproject.toml` `version` on `master` → commit → push → `git tag vX.Y.Z`
on the bump commit → `git push origin vX.Y.Z` (tag push alone triggers `release.yml`; no GitHub
Release object needed). CI runs `gate` (lint/type/tests/boundary/version-consistency) →
`image-smoke` (build+smoke) → `publish` (`ghcr.io/slop-platform/charon:vX.Y.Z` + attestation).
The `derive version` step HARD-FAILS if the pushed tag ≠ `pyproject` version, so the bump and
the tag must be the same commit's state. Confirm all three jobs green before touching the box.

**Deploy:** only after CI is green, `bash /home/stack/charon-private/fleet/deploy.sh vX.Y.Z` on
4-LOM. `deploy.sh` verifies preflight (pool count, keys present, deepseek-v4-pro provider), then
`backup_data()` tars the `/data` volume to `.charon-deploy-backups/` (chmod 600) BEFORE arming
`trap rollback ERR`, pulls the tag, `compose up -d gateway`, and `verify_all` (wait_healthy via
the image's built-in HEALTHCHECK + pool-count-unchanged + keys-present + deepseek provider
unchanged). On ANY post-arm error it auto-rolls back: pull previous tag, wipe+restore `/data`
from the backup, bring up the old tag, re-verify, re-raise. Named-volume mount means the
backup/restore machinery only fires on the rollback path.

**Zero-delta dry run (optional confidence):** `bash deploy.sh vX.Y.Z` against the *currently
running* tag exercises the full backup/verify/rollback mechanics with zero version change before
the real jump. Note `verify_deepseek_provider` makes one real billed nanogpt call per invocation.
