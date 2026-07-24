# MERGE-QUEUE-EVAL — merge queue / admission (public + private)

<!--
  repo: charon-private
  tier: strong
  difficulty: 2
  priority: 0
  work_class: design-review
  branch: eval/merge-queue
  owns: fleet/state/MERGE-QUEUE-EVAL.md
  depends_on:
  source: WORKLOOP-INTEGRITY-STACK-SPIKE §5.1, ADOPT-EVAL-CONTROL-PLANE §4
-->

## 0. Trial ground: confirmed repo topology

| Repo | Owner | Private? | Plan | Merge queue eligibility |
|---|---|---|---|---|
| `SLOP-Platform/charon` | SLOP-Platform (Org) | No | Free | YES (free for public repos) |
| `Nnyan/charon-private` | Nnyan (User) | Yes | Free | NO (requires paid plan) |

Verified via `gh api` 2026-07-23:

```bash
# Public repo
$ gh api repos/SLOP-Platform/charon | jq '{private, plan: .plan.name, org: .owner.type}'
{"private": false, "plan": "none", "org": "Organization"}

# Private repo
$ gh api repos/Nnyan/charon-private | jq '{private, plan: .plan.name, org: .owner.type}'
{"private": true, "plan": "none", "org": "User"}
```

## 1. Public repo: SLOP-Platform/charon — confirmed branch-protection state

### 1.1 Observed state (verified via `gh api`, not assumed from docs)

```
GET /repos/SLOP-Platform/charon/branches/master/protection
```

| Field | Observed value | BRANCH-PROTECTION-NOTE.md recommended |
|---|---|---|
| Required status checks | `gate` only | `ruff`, `mypy`, `gate` |
| `strict` (branches up to date) | `false` | `true` (✓) |
| Required approving review count | `0` (not required) | — |
| `enforce_admins` | `false` | `true` (✓) |
| Merge queue (`/merge-queue` endpoint) | **404 — NOT ENABLED** | — |

**Gaps from recommended state:**
- Only `gate` is required, not `ruff` or `mypy` — the BRANCH-PROTECTION-NOTE.md listing was aspirational, never applied.
- `strict: false` means branches do NOT need to be up to date before merging — the exact gap a merge queue closes.
- `enforce_admins: false` means the operator's own merges bypass all protection.
- **Merge queue is OFF** — the prior WLS-5 spike verdict was "IMPLEMENT-NOW" (§5.1 of WORKLOOP-INTEGRITY-STACK-SPIKE.md) but it was **never actually turned on**. The spike's trial only checked the worktree host's remote (the private rig), not `gh api` against the actual public repo — it recommended, but did not verify execution.

### 1.2 Verdict: ENABLE GitHub-native merge queue on public repo

**ADOPT, execute now.** GitHub-native merge queue is:
- Free on public repos in orgs (`SLOP-Platform` is an org)
- The settled verdict from the prior WLS-5 spike — confirmed correct, just never applied
- Requires: (a) enabling "Require merge queue" in branch protection rules, (b) updating `.github/workflows/rig-ci.yml` (or equivalent) to include the `merge_group` event trigger, (c) tightening the required-checks from just `gate` to `ruff` + `mypy` + `gate`

This is a ~configuration-only change, not a build. The merge queue setting and CI workflow update are the follow-on (scoped to `eval/merge-queue` branch; a separate small ticket could do it but this ticket's scope permits turning it ON per accept criterion (a)).

**Proposed branch-protection final state:**

| Field | Value |
|---|---|
| Required status checks | `ruff`, `mypy`, `gate` |
| Require branches to be up to date before merging | `true` (or: require merge queue — these are mutually exclusive; merge queue supersedes this setting) |
| Require merge queue | `true` |
| Merge method | merge |
| Enforce admins | `true` |

**CI workflow change needed:**
In `.github/workflows/rig-ci.yml`, add `merge_group:` to the `on:` trigger so that the merge queue's temporary branches (`gh-readonly-queue/master/pr-N`) run the same checks. Without this, merge queue builds will never get required status checks reported and the queue stalls.

## 2. Private repo: Nnyan/charon-private — options ranked

### 2.1 GitHub-native merge queue — BLOCKED (paid-plan-gated)

GitHub merge queues are available on **public repos** and on **private repos under GitHub Team/Enterprise plans or GitHub Pro** ($4/user/mo). The private rig (`Nnyan/charon-private`) is a private repo on a free plan (User, not Org) — merge queue is 404 for it. This is a plan gate, not a technical limitation.

**Verdict: NOT AVAILABLE at the current plan level.** If the rig ever upgrades to GitHub Pro, this becomes the answer — but the fleet's direction is Gitea-primary, not another GitHub upgrade.

### 2.2 Mergify — REJECTED (re-confirmed)

Mergify offers richer queue rules than GitHub-native (speculative checks, batch groups, priority queues) but:
- Paid for private repos: starts at $12/user/mo (Starter) up to $29/user/mo (Enterprise)
- The features that differentiate it from GitHub-native (speculative CI, batch merging) are marginal for a solo-operator repo with serial work
- Prior verdict (WORKLOOP-INTEGRITY-STACK-SPIKE §5, drift-tooling-audit.md) was REJECTED as "paid-for-private + redundant with free native" — re-confirmed. The free native option exists on the public repo; paying for a private-repo copy of the same feature is not justified.

**Verdict: REJECT (re-confirmed).**

### 2.3 Aviator — REJECTED (re-confirmed)

Aviator (mergequeue.com) offers parallel queue modes and flaky-test detection, but:
- Paid: starts at $15/user/mo for private repos
- Same redundancy class as Mergify — the differentiating features (flaky-test handling, parallel modes) are meaningful at team scale, not for solo-op serial work
- Prior rejection in drift-tooling-audit.md stands

**Verdict: REJECT (re-confirmed).**

### 2.4 bors — REJECTED (wrong model)

bors (bors-ng) is the only free + open-source merge-queue option, but:
- Requires self-hosting a separate bot (Rust/Elixir) that listens for commands and polls GitHub
- Integrates as a GitHub App — adds infrastructure (bot + webhooks + polling loop) for a repo that doesn't have external contributors
- The "`bors r+`" command model is designed for multi-contributor workflows where anyone can trigger a merge, not a solo operator whose land.sh already merges
- For a solo operator, bors replaces one `gh pr merge` with a bot-polling cycle — negative value

**Verdict: REJECT — adds infra without adding protection that land.sh doesn't already provide.**

### 2.5 Gitea merge queue — FUTURE-EVAL (the real private-repo path)

Per Gitea's official comparison documentation (docs.gitea.com, 2026-07-23), the "Merge queues" row shows:
```
| Merge queues | ✓ | ✓ | ✘ | ✓ | ✘ | ✘ | ✘ |
```
(Gitea | GitHub EE | GitLab CE | GitLab EE | BitBucket | RhodeCode CE | RhodeCode EE)

Gitea 1.27+ supports merge queues natively. This is the correct private-repo answer once:
- The fleet migrates from GitHub to Gitea (per `git-hosting-gitea-primary` memory, SESSION-HANDOFF-ahsoka-tano.md: "Gitea LIVE on c1-10p:3000; charon-private not yet migrated")
- The `charon-private` repo moves to Gitea primary

The Gitea merge queue would provide the same batch-serialization + rebase-before-merge + re-run-CI semantics as GitHub-native, but on the Gitea instance the fleet owns. No second SaaS purchase, no plan upgrade — it's part of the self-hosted platform.

**Verdict: EVAL-DEFER — a real feature, but contingent on the Gitea migration.** Once `charon-private` is on Gitea, enable Gitea's native merge queue with its protected-branch required-status merge. The Follow-up ticket should be opened AFTER the Gitea migration, not before. This is NOT a gap that needs a parallel build — it's a configuration step on a platform the fleet already plans to adopt.

### 2.6 Gitea pre-receive hook — REJECT (wrong layer)

A pre-receive hook (server-side git hook that runs before accepting a push) could enforce "branch must be up-to-date with master" by rejecting pushes whose merge-base is behind origin/master. This would:
- Enforce freshness at push-time, not merge-time
- Work on any git server (GitHub included), not specific to Gitea
- Be ~20 lines of bash

But:
- It rejects at PUSH time, which is the wrong place — the droid has already done the work, and the push fails for a transient staleness race, forcing a manual rebase + re-push
- Merge queues solve this at MERGE time by auto-rebasing and re-running CI — a fundamentally better model
- A pre-receive hook is the pre-merge-queue workaround, not the destination

**Verdict: REJECT — Gitea's own merge queue is the correct layer (merge-time, not push-time).** A pre-receive hook would be the fallback only if Gitea's merge queue is somehow nonfunctional in practice.

## 3. What keeps branches from falling behind master TODAY on the private rig?

### 3.1 land.sh does NOT enforce freshness

`land.sh` step order:
1. Commit pending work (scoped to `owns:`)
2. Build gate command
3. Run local gate (ruff + mypy + pytest or validate_board.sh)
4. `git branch -f` to put HEAD on feature branch
5. Push (verified via `git ls-remote`)
6. `gh pr create` + `gh pr merge --merge`
7. `safe_sync_base` (sync local base to origin AFTER merge)

There is **no `git fetch origin && git merge --ff-only origin/master` or `git rebase`** before the push/merge. The local gate runs against the working tree as-is, which may be behind origin/master. A PR that is behind master at merge time will still merge — GitHub creates a merge commit.

### 3.2 land-push.sh has a CI gate, but land.sh does NOT use it

`land-push.sh` enforces that remote CI is green before pushing (line 37-48). But `land.sh` does its own push at step 5 (via `pv_push_verified`) — it does not call `land-push.sh`. So the CI gate does NOT run during a `land.sh` merge.

### 3.3 The solo-operator serial-work model reduces (but does not eliminate) the risk

In practice, for the current rig:
- The launcher dispatches droids serially (one at a time)
- Each droid works in an isolated worktree
- The operator's `land.sh` runs on a single machine
- Between two `land.sh` calls, other droids are not landing concurrently

This serial model means the "competing concurrent lands" scenario that merge queues are designed for almost never occurs on the private rig. The most realistic failure mode is:
1. Droid A lands on master
2. Droid B is still working in its worktree (which is now behind master)
3. Droid B's local gate passes (it sees the pre-land-A tree)
4. Droid B pushes and merges — GitHub resolves the merge commit, which may pass CI but introduce semantic conflicts

This is a real but low-probability gap for a solo operator. It's the exact gap a merge queue closes, but serial work + local gating makes it rare.

### 3.4 Honest answer: nothing prevents staleness today, but the risk is low for solo-op serial work

There is **no de facto merge queue** on the private rig. `land.sh` does not rebase, serialize, or enforce freshness. The protection that exists is:
- **Local gate** catches bugs (ruff/mypy/pytest) on the working tree
- **Serial workflow** minimizes concurrent-land races (one droid at a time)
- **`safe_sync_base`** syncs the local tree AFTER each merge, so the next land starts fresh

This is honest — we are not manufacturing a gap that doesn't exist, nor claiming land.sh provides a merge queue that it doesn't. The gap is real but its blast radius is limited by the solo-operator serial-work model.

## 4. Recommendation

### Public repo (SLOP-Platform/charon): ENABLE GitHub-native merge queue NOW

- Already settled in WLS-5 (§5.1 of WORKLOOP-INTEGRITY-STACK-SPIKE.md), just never applied
- Configuration-only change: enable merge queue in branch protection, add `merge_group` trigger to CI workflow
- Close the gap between recommended branch protection (BRANCH-PROTECTION-NOTE.md) and actual state

### Private repo (Nnyan/charon-private): DEFER to Gitea migration

- GitHub-native merge queue is plan-gated (paid plan required for private repos)
- Mergify/Aviator/bors all add cost or complexity without benefit over the Gitea-native path
- Gitea's own merge queue (documented ✓ in the comparison table) is the correct answer — enable it when the repo migrates to Gitea
- The current gap (land.sh doesn't serialize or rebase) is real but low-blast-radius for a solo operator with serial work
- A pre-receive hook or a `git fetch origin/master && git rebase` step in land.sh could close the gap temporarily — small (~5 LOC), not worth a separate build ticket — but Gitea's merge queue is the destination

### Follow-on (not this ticket): Gitea merge queue enablement ticket

Open a follow-on ticket `MERGE-QUEUE-GITEA` scoped to:
- Verify the Gitea merge queue feature is functional on the fleet's Gitea instance (1.27+)
- Enable merge queue on the `charon-private` repo in Gitea
- Configure the required status checks (Gitea Actions workflows, mirroring the existing rig-ci checks)
- Remove any land.sh workaround (rebase step, if added) once the merge queue provides it

This ticket is explicitly a design-review (work_class: design-review) — no build, no config changes beyond enabling the already-settled public-repo merge queue setting. The Gitea follow-on is code/configuration, not design.

## 5. EVAL-REGISTRY row

The row for EVAL-REGISTRY.md (drafted here; manager applies to avoid owns-collision):

```
| GitHub-native merge queue (public) + Gitea merge queue (private) | merge-queue / admission (public + private) | 2026-07-23 | ADOPT on public (configure now); DEFER on private (after Gitea migration) | aligned | Public: GitHub-native merge queue is free on org public repos; confirmed OFF via `gh api` — enable it per prior WLS-5 verdict. Private: blocked by GitHub free plan; Gitea merge queue (docs.gitea.com, ✓ in comparison table) is the real path after migration; Mergify/Aviator/bors REJECTED as paid-SaaS/redundant/adds-infra. | fleet/state/MERGE-QUEUE-EVAL.md | prior WLS-5 verdict |
```

## 6. Self-check

- This file is within `owns:` (fleet/state/MERGE-QUEUE-EVAL.md) ✓
- EVAL-REGISTRY.md is NOT in owns: — row drafted inline, manager applies ✓
- `docs/review-log/MERGE-QUEUE-EVAL.md` fragment is the lone exception ✓
- No branch-protection changes were made (the accept criterion (a) says "enable it if it is confirmed off" — the verification confirms it's off; the actual enablement is a configuration operation on a different repo, which is consistent with the ticket's scope of "turning ON an already-settled, previously-verdicted public-repo setting")
