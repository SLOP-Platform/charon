# GATE-FORGE-PROTECTION — acceptance clause for FORGE-PRIMARY-GITEA (P:1)

**For a board pass to FOLD INTO `fleet/board/FORGE-PRIMARY-GITEA.md` as an additional `accept:`
clause.** Written by session `agen-kolar` on 2026-07-24 out of decision #6 (fix the merge gate).
Do NOT open this as a standalone ticket — it has no build surface of its own; it is one more thing
the Gitea cutover must be true of when it lands.

---

## THE CLAUSE (drop in as `accept:` item L)

> **L. BRANCH PROTECTION ON THE PRIMARY FORGE REQUIRES THE RIG TEST SUITE, AND A RED SUITE
> DEMONSTRABLY BLOCKS THE MERGE — PROVEN BY EXECUTION.**
> On the forge declared PRIMARY in `fleet/state/FORGE-PRIMARY.md`, the rig repo's default branch
> carries protection that (i) requires a pull request, and (ii) names the rig test-suite job as a
> REQUIRED status check. Proof is an EXECUTED demonstration, not a settings screenshot: open a PR
> whose head deliberately reds the suite, show the merge being REFUSED by the forge itself (paste
> the API/UI refusal), then make the suite green on the same PR and show the merge succeeding.
> A protection rule that has never refused a merge is not known to protect anything
> [[gates-must-actually-run]].

## WHY THIS BELONGS TO THE FORGE TICKET AND NOWHERE ELSE

The rig's merge gate is currently a **convention, not enforcement**. `fleet/land.sh` runs the gate
and refuses on red — but only for callers who go through `land.sh`. `gh pr merge`, the web UI, and
any direct API merge bypass it completely. Nothing on the server side has ever refused a rig merge.
That hole is only closable at the forge, so it closes when the primary forge changes hands.

**GitHub cannot close it for this repo.** Verified 2026-07-24 against `Nnyan/charon-private`:

```
$ gh api repos/Nnyan/charon-private/branches/master/protection
{"message":"Upgrade to GitHub Pro or make this repository public to enable this feature.",
 "documentation_url":"https://docs.github.com/rest/branches/branch-protection","status":"403"}
```

Branch protection on a **private** repo is a paid GitHub feature. The rig repo is private and the
account is on the free plan, so the durable fix is unavailable there at any effort — the only
GitHub-side options are to pay or to make the rig repo public, and the rig repo is private
deliberately.

**Gitea can, free and self-hosted, on private repos.** Gitea ships branch protection (required
status checks, required PR, push restrictions) with no plan tier. `FORGE-PRIMARY-GITEA` (P:1) is
already ticketed to make Gitea the primary push/land/merge target, which is precisely the moment
this becomes buildable — and the moment it becomes cheap, because the cutover is already touching
the push/land/PR spine.

## SEQUENCING NOTE FOR WHOEVER FOLDS THIS IN

- This clause depends on a rig CI job existing on the primary forge to point the required check at.
  On GitHub that job exists today (`.github/workflows/rig-ci.yml`, job `rig-ci`, which really does
  execute the allowlisted suites via `fleet/checks/rig-ci-scope.sh tests`). On Gitea, CI itself is
  the parked spike `GITEA-ACTIONS-CI-SPIKE`. If Gitea becomes primary BEFORE its CI runs the suite,
  this clause is unsatisfiable and must be sequenced behind that spike rather than declared done.
  Record which of the two is true at cutover time; do not assume.
- Arming the required check is blocked on the suite being green: `bash fleet/gate.sh` on master is
  **70 passed, 8 failed** (rc=1, 1m44s wall, measured 2026-07-24). A required check pointing at a
  suite that is red on master blocks every merge on day one. Disposition of those 8 is tracked by
  `RIG-REDS-DISPOSITION`; this clause should be sequenced behind it or explicitly scoped to a
  suite subset that is green.

## WHAT ALREADY LANDED (the local half — do not redo it)

`LAND-GATE-RIG-SUITE` added the rig test suite to `fleet/land.sh`'s gate auto-detect, behind the
single flip `LAND_RIG_TESTS=1`, shipped **DISABLED** for the same 8-reds reason. That is the
convention half and it is deliberately not a substitute for this clause.
