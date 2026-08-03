# DIVERGED-BRANCH-TRIAGE — measurement + per-branch merge decisions

**Ticket:** DIVERGED-BRANCH-TRIAGE
**Date measured:** 2026-08-02 (session close)
**Repo scope:** charon-private + charon
**Method:** every claim below was MEASURED by running git/gh against the live rig on the date
above (commit counts, reachability, patch-ids, PR state). Nothing is assumed.

---

## 1 — The headline measurement

**7 branches report at-risk on EVERY stranded-work cycle and always will.** All 7 are DIVERGED
(local and remote each hold commits the other lacks), so they can never fast-forward. Their
content IS SAFE: in every case the local tip is parked on a `rescue/*` ref on the remote
(`origin/rescue/<branch>` == local tip), so nothing exists on one disk only.

| # | branch | repo | local | remote | rescue | ahead-of-upstream | local-absent-from-master | remote-absent-from-master |
|---|---|---|---|---|---|---|---|---|
| 1 | `eval/workflow-e2e-audit` | charon-private | `2c83973` | `9d33059` | `2c83973` | 23 | 2 | 1 |
| 2 | `feat/ft-limits-groq-reconcile` | charon-private | `06b4e5a` | `d2722ed` | `06b4e5a` | **706** | **0** | 2 |
| 3 | `feat/reconcile-gate-wired` | charon-private | `6d4d6db` | `d603494` | `6d4d6db` | 35 | **0** | 1 |
| 4 | `feat/semgrep-ci-required-check` | charon-private | `2a50f55` | `f42fadc` | `2a50f55` | 3 | 3 | 2 |
| 5 | `fix/sandbox-containment` | charon-private | `0512077` | `2f9e2db` | `0512077` | 1 | 2 | 2 |
| 6 | `docs/work-converge-review` | charon | `2fccd83` | `cdcae4c` | `2fccd83` | 1 | 2 | 2 |
| 7 | `feat/ft-catalog-seed` | charon | `ae42255` | `e647748` | `ae42255` | 104 | **4** | 1 |

The counts drift slightly cycle to cycle (branches are live); the SET is stable. The ticket's
original at-risk counts (23 / 706 / 35 / 3 / 1 / 1 / 4) match this measurement.

**Why they can never fast-forward:** every one of the 7 is BOTH ahead of AND behind its upstream
(ahead > 0 AND behind > 0 — verified for all 7). A fast-forward is impossible; any resolution is a
merge (or a deliberate delete), never a `--force`.

---

## 2 — The 706 anomaly: CONFIRMED broken upstream ref, not 706 pieces of work

`feat/ft-limits-groq-reconcile` reports **706** local-only commits (ahead of its upstream). The
count is an artifact, and this is measurable, not a hunch:

- `git rev-list --count origin/master..feat/ft-limits-groq-reconcile` → **0**. The local branch
  carries ZERO commits absent from master. Its tip `06b4e5a` is an ancestor of `origin/master`
  (CONTAINED). Every one of the "706" commits is already reachable from master — the branch's
  upstream tracking ref is simply years of history stale.
- The local tip `06b4e5a` == `origin/rescue/feat/ft-limits-groq-reconcile`. The rescue ref parks
  content that is ALREADY on master, so it protects nothing that would otherwise be lost.
- The REAL unlanded work is on the REMOTE side: `origin/feat/ft-limits-groq-reconcile` = `d2722ed`
  carries **2 commits absent from master** (`93d0d32` force-track + reconcile; `d2722ed` mechanized
  test), and there is an **OPEN PR #116** with head `d2722ed` (+450 lines).

**Verdict: the 706 is a stale/broken upstream ref. The local side is superseded (all content on
master); the remote side (PR #116) is the real, still-wanted work.** Do NOT count 706 as a backlog.

---

## 3 — Per-branch triage decisions (with evidence)

### STILL WANTED — merge by hand

**1. `eval/workflow-e2e-audit`** (charon-private)
- Local-absent (2): `ee02f81` audit execute + report, `2c83973` refresh against 08-02 board state.
- Remote-absent (1): `9d33059` the pre-refresh audit report.
- The 3 delivered files — `docs/review-log/WORKFLOW-E2E-AUDIT.md`,
  `fleet/state/WORKFLOW-E2E-AUDIT.md`, `fleet/tests/workflow-e2e.test.sh` — are **NOT on master**
  (checked individually). Patch-id test: NOT-LANDED. This is real, unlanded audit content.
- No PR exists.
- **Decision: still wanted.** Land the local side (it contains the newer refresh) via a PR to
  master; the remote side is the same report one commit older. Merge by hand, do not force.

**7. `feat/ft-catalog-seed`** (charon)
- Local-absent (4): `d34d09e` add hosted presets (github_models/featherless/ollama_cloud),
  `9cc588f` catalog seed + FAIL-ON-REVERT tests, `5601f99` contract + URL fixtures,
  `ae42255` review-log fragment. All genuinely absent from master.
- **OPEN PR #135** (+489/-0) titled "launcher auto-commit — droid exited without committing
  (review for completeness)". The content is real feature work, not a stray marker.
- A follow-up branch `sub/ft-catalog-seed-fix-v2` exists with a forward-compat PRESETS fix
  (`75063d5`) that should be folded into the merge.
- **Decision: still wanted.** Merge PR #135 by hand (after review), folding in the fix-v2
  forward-compat assertion. Do not force-push: remote `e647748` is 1 commit local lacks.

### SUPERSEDED — content already landed on master; drop branch + rescue ref

**2. `feat/ft-limits-groq-reconcile`** — LOCAL side superseded (0 absent from master, see §2).
Delete the local branch + `origin/rescue/feat/ft-limits-groq-reconcile`; the remote side +
PR #116 is the surviving work to merge (§2).

**3. `feat/reconcile-gate-wired`** (charon-private)
- Local-absent = **0** (CONTAINED). Master already carries `6d4d6db` "fix(reconcile-gate-wired):
  salvage + WIRE the built-but-inert meta-gate" — the local tip IS a master commit.
- Remote-absent (1) `d603494` "built-but-inert meta-gate (detector, no wire)" — the PRE-wire
  version, superseded by the salvage+wire that landed on master.
- PR #211 CLOSED (merged=never) — closed precisely because the wired version went in directly.
- **Decision: dead/superseded.** Both sides carry content that is on master. Delete both refs +
  `origin/rescue/feat/reconcile-gate-wired`.

**4. `feat/semgrep-ci-required-check`** (charon-private)
- Local-absent (3) but the CONTENT landed: master's `fleet/checks/semgrep.sh` is
  byte-IDENTICAL to the branch's (md5 match), `semgrep.yml` diff = 0 lines. Master has `fa062b9`
  "SEMGREP-CI-REQUIRED-CHECK — adopt Semgrep (version-deterministic) (#143)".
- The 3 "absent" commits are the branch's own originals (adopt, landing note, version-pin);
  master re-landed the same content as PR #143 (version-pinned engine + wrapper-owned vacuous
  guard, byte-identical).
- PR #141 CLOSED (merged=never).
- **Decision: superseded.** Content is on master. Delete both refs + rescue ref.

**5. `fix/sandbox-containment`** (charon-private)
- The local fix `0512077` has **patch-id == patch-id of merged commit `2119d77`** (#393).
  Master carries "fix(SANDBOX-CONTAINMENT): contain test sandboxes, fail closed, stop the
  gate-killer (#393)" — identical content, landed.
- **Decision: superseded.** Both sides carry landed content. Delete both refs + rescue ref.

**6. `docs/work-converge-review`** (charon)
- Patch-id test: **LANDED**. Master has `a1652f6` "docs(review-log): WORK-CONVERGE-REVIEW
  (sanitized, no private paths)" merged via PR #108 (the `-v2` branch). PR #101 CLOSED.
- **Decision: superseded.** Content landed via #108. Delete both refs + rescue ref.

---

## 4 — Resolution rules that must not be weakened

1. **NEVER force-push to resolve a divergence.** In every one of the 7 cases the remote side holds
   commits the local lacks (`behind > 0`). A force destroys them. Every resolution is a merge
   (PR #116, PR #135, new PR for workflow-e2e-audit) or a deliberate delete of a SUPERSEDED pair.
2. **A SUPERSEDED verdict requires positive landing proof** — reachability (ancestor of master),
   byte-identical file, or matching patch-id — never "looks old". Branches 3/4/5/6 each carry that
   proof; that is why they are deletable. Branch 2's local side carries it via 0-absent-from-master.
3. **Rescue refs are never deleted until the pair is decided.** `rescue/<branch>` holds the only
   copy of the LOCAL side; dropping it before the merge deletes the local-only content. All 7
   rescue refs stay until the corresponding decision above is executed.

---

## 5 — Half (A): the `diverged-parked` classification (plan/ADR note for the stranded-work.sh-owning ticket)

This ticket owns only documentation, so the CLASSIFICATION RULE is specified here for the ticket
that owns `fleet/checks/stranded-work.sh`. This is the "plan/ADR note before code" contract; the
implementer must keep the gate GREEN and satisfy the fail-on-revert assertions below.

### The distinction (the novel slice)

"Unprotected" and "protected-but-unresolved" are different classes with different urgency:

- **Unprotected** = a branch whose local side is NOT on any remote ref, NOT on master, and NOT
  parked on `rescue/*`. A disk failure loses it permanently. This is the RED alarm.
- **Protected-but-unresolved (diverged-parked)** = the local side IS parked on a `rescue/*` ref
  (recoverable by name) but the branch still diverged and can never fast-forward. Nothing is lost;
  what remains is a human merge decision. This is noise on the loss alarm but NOT zero — silence is
  how the class returns.

### The rule

In `stranded-work.sh`, when the shapes-1/6 scan finds a branch with commits on no remote ref (or
ahead of its upstream), FIRST test whether `refs/heads/rescue/<branch>` (local or `origin/`) holds
the branch tip. If yes, report a DISTINCT shape:

```
STRANDED[diverged-parked] <repo>: branch '<b>' is diverged but its local side is parked on rescue/<b> — merge by hand, do not force (remote has commits local lacks)
```

- Counted in its OWN shape bucket (`diverged-parked`), surfaced in the per-shape summary SEPARATELY
  from `unpushed-branch` / `ahead-of-remote` / `pushed-no-pr`.
- It is still a finding (exit 1, still printed with SW_LIMIT semantics) — it is NEVER suppressed.
- The rescue ref itself (`rescue/<branch>`) must not also be reported as `pushed-no-pr` (it is a
  parking ref, not stranded work). Skip `rescue/*` short-names in the pushed-no-pr walk.

### Fail-on-revert assertions (the implementer's tests)

1. A diverged-parked branch (local tip == `rescue/<branch>` ref) MUST NOT be counted as
   `unpushed-branch` or `ahead-of-remote`. → add a fixture branch with a parked rescue ref; assert
   shape is `diverged-parked` and the unpushed/ahead counts do NOT include it.
2. An UNPROTECTED branch (commits on no remote, no rescue ref) MUST still RED as
   `unpushed-branch`. → existing fail-on-revert test B must still pass unchanged.
3. `rescue/<branch>` refs must not appear as `pushed-no-pr`. → extend the pushed-no-pr fixture.
4. The `diverged-parked` shape must still appear in the summary + findings count (not suppressed).

### Why NOT simply suppress

The 7 branches are permanent noise only because they are unresolved. The moment an operator merges
PR #116 / #135 / the workflow-e2e-audit PR, the class shrinks. A suppressed class would also hide
the NEXT genuinely-new diverged branch. `diverged-parked` keeps the count visible and shrinking.

---

## 6 — What the operator should do next

1. Merge **PR #116** (feat/ft-limits-groq-reconcile remote side — the 2 real commits).
2. Review + merge **PR #135** (feat/ft-catalog-seed), folding in `sub/ft-catalog-seed-fix-v2`.
3. Open + merge a PR for **eval/workflow-e2e-audit** (3 files, local side).
4. Delete the 4 SUPERSEDED pairs (+ their rescue refs): `feat/reconcile-gate-wired`,
   `feat/semgrep-ci-required-check`, `fix/sandbox-containment`, `docs/work-converge-review`,
   and the LOCAL side of `feat/ft-limits-groq-reconcile`.
5. Hand the §5 classification rule to the stranded-work.sh-owning ticket.
