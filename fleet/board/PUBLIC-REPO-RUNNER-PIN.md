repo: charon
tier: economy
priority: 0
difficulty: 1
work_class: ci-infra
branch: fix/public-repo-runner-pin
owns: .github/workflows/ci.yml, .github/workflows/heavy.yml, .github/workflows/release.yml
depends_on:
dep-kind: |
  NOTE FOR PARALLEL WORK: DIFF-COVER-MUTMUT-ADOPT, GITEA-ACTIONS-CI-SPIKE and
  INERT-WIRING-ENFORCEMENT-DURABLE also own .github/workflows/ci.yml. This ticket is a
  comment/one-line-per-job security pin only — it adds no steps and changes no job behaviour, so it
  is trivially rebasable. Land it FIRST because it removes a live instruction to create a breach;
  the others rebase over it.
serial_justified: |
  One security invariant applied identically to three files. There is nothing to parallelise — the
  same eight job definitions get the same pin and the same warning. Splitting it would leave some
  jobs still carrying the instruction that causes the breach, which is the whole defect.
work_class_note: ci-infra — a runner-selection security pin on the PUBLIC repo. Zero new tools,
  zero new steps, no behaviour change when the variable is unset (which it is).
note: |
  OPERATOR-APPROVED 2026-08-04 ("go ahead and delete"), after an adversarial review of the scanner
  relocation surfaced it OUTSIDE the diff under review.

  ## THE DEFECT IS THE INSTRUCTION, NOT THE STATE
  Eight job definitions across ci.yml (2), heavy.yml (3) and release.yml (3) resolved their runner
  as `runs-on: ${{ fromJSON(vars.CI_RUNNER || '"ubuntu-latest"') }}` on `pull_request`, each
  preceded by a comment reading:
      "Maintainer sets CI_RUNNER=["self-hosted","4-lom"]; forks don't inherit it and
       fall back to GitHub-hosted ubuntu-latest, so forked PRs get working CI."
  That comment instructs a future maintainer or session to create the exact breach D-016 forbids.

  VERIFIED SAFE AT THE TIME OF THE FIX (2026-08-04): `gh api repos/SLOP-Platform/charon/actions/variables`
  AND `gh api orgs/SLOP-Platform/actions/variables` both return total_count 0, so CI_RUNNER is unset
  at repo AND org level and nothing was exposed. The exposure was one settings change away — and
  documented as a recommendation.

  ## WHY THE COMMENT'S REASONING IS WRONG
  It is true that a FORK does not inherit repo variables. It is NOT true that this makes the setup
  safe: `pull_request` runs in the BASE repo's context, so with CI_RUNNER set to a self-hosted
  label, an APPROVED fork PR executes on our hardware — and those runners live on 4-LOM and BB-8,
  which also run the gateway and the fleet. D-016 states it plainly: "self-hosted runners on a
  PUBLIC repo let a fork's pull request execute arbitrary code on your hardware."

  ## THE FIX
  Hard-pin `runs-on: ubuntu-latest` in all 8 jobs and replace the comment with a warning that says
  why it must not be reintroduced. This repo is PUBLIC, so GitHub-hosted CI is free and unlimited —
  there is nothing to gain from self-hosted here. Self-hosted runners are for the PRIVATE rig repo
  only (D-016, operator-approved option (a)).

  NO BEHAVIOUR CHANGE: with CI_RUNNER unset the previous expression already evaluated to
  ubuntu-latest, so every job runs exactly where it ran before. This removes a foot-gun, it does
  not move CI.

  ACCEPTANCE: (a) zero `vars.CI_RUNNER` lookups remain in any product workflow; (b) all 8 jobs read
  `runs-on: ubuntu-latest` literally; (c) actionlint clean; (d) the four required checks
  (gate, bandit, gitleaks, semgrep) pass on the PR.
