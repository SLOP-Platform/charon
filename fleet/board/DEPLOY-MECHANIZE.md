repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: feat/deploy-mechanize
owns: fleet/checks/deploy-drift.sh, fleet/tests/deploy-drift.test.sh
depends_on:
dep-kind:
serial_justified: |
  A drift detector and its red-proof are one unit. A detector with no proof that it can go RED is
  precisely the unproven-gate class this project keeps shipping — and this one would be reporting
  on the MONEY path, so a false green is worse than no detector.
work_class_note: ci-infra — closes the deploy-drift class. Not a feature; it is the mechanism that
  makes every future money-path fix actually reach production.
note: |
  ⛔ OPERATOR, 2026-08-04, verbatim: "should we automate/mechanize the deploy? this is constantly
  lagging." YES. This ticket exists because the answer is yes and because the lag is measurable.

  ## THE MEASURED FAILURE
  2026-08-04: the gateway ran `ghcr.io/slop-platform/charon:v0.6.1` while master was **14 commits
  ahead**, and one of those commits was D-012 — the fix that stops a fully-parked pool from serving
  a silent, billed 200. **The money leak stayed live in production for the entire time the fix sat
  merged on master.** Nobody was told. Nothing surfaced it. It was found only because a session went
  looking at the deployment host by hand.
  This is the documented deploy-drift class: DEPLOYED IMAGE != SOURCE. It has now bitten twice.

  ## WHY IT KEEPS HAPPENING — name the root cause, do not fix the symptom
  There is NO signal anywhere that connects "merged to master" with "running in production".
    - The deployment host has NO charon git checkout at all — it pulls immutable :vX.Y.Z images, so
      no ordinary git-based staleness check can ever see it.
    - Cutting a release is a MANUAL multi-step ritual (bump pyproject version -> PR -> merge -> push
      a v* tag via the refs API -> wait for release.yml -> update compose on the host -> pull -> up).
      Every manual step is a place it stops, and it stops at a different one each time.
    - STATUS-BOARD-V1 renders gates, tickets and PRs — but has NO deployed-version tile, so the one
      surface built to make state legible to the operator is blind to exactly this.

  ## ⛔ SECOND, WORSE DRIFT FOUND 2026-08-04 — THE COMPOSE FILE WOULD ROLL PRODUCTION BACK ⛔
  On the deployment host, `/home/stack/charon/docker-compose.yml` pins:
      image: ghcr.io/slop-platform/charon:v0.3.3
  ...while the RUNNING container is **v0.6.1**. Someone deployed v0.6.1 by hand and never updated
  compose. Consequence: **any `docker compose up` on that host silently DOWNGRADES the live gateway
  by three minor versions**, reverting every money-path fix since v0.3.3 — including D-012 the
  moment it ships. A routine "restart the service" would do it, with no error and no warning.
  ⇒ The drift check MUST compare THREE things, not two: the running image, the pinned image in
  compose, and the latest published release. Two of those three disagreeing is the normal state here.

  ## SCOPE — DETECT FIRST, AUTOMATE SECOND. Do not invert this.
  1. **`fleet/checks/deploy-drift.sh`** — compare the RUNNING image tag on the deployment host
     against the latest published tag and against `origin/master`. Report three numbers: deployed
     version, latest released version, commits on master not in the deployed version. RED when the
     deployed version is behind a published release, or when master is ahead by more than N commits.
     It must name WHICH commits, so "D-012 is not deployed" is legible without reading git.
  2. **Wire it into the existing 20-min cron AND add a STATUS-BOARD-V1 tile.** The board is the
     operator-facing surface and it currently cannot show this. A number the operator can see is
     worth more than a perfect deploy pipeline nobody triggers.
  3. **THEN mechanize the release path** — a single command (or a workflow_dispatch) that does
     bump -> PR -> tag -> publish, so cutting a release is one action, not seven.
  4. **Auto-deploy is LAST and is a separate decision.** An automatic pull+restart of the live money
     path is a bigger blast radius than the drift it fixes. Detection + one-command release removes
     most of the pain at a fraction of the risk. Do not skip to step 4 because it sounds better.

  ⚠️ D-008: this must NOT be bash if it grows state or long-running behaviour. Step 1 is a short
  script that calls other programs and exits, which bash is still allowed to do. If step 3 becomes a
  supervisor, it is Go.

  ACCEPTANCE: (a) the check reports the real deployed version, proven by running it against the live
  host; (b) it goes RED on a seeded drift and GREEN when aligned — both OBSERVED, not asserted;
  (c) it names the undeployed commits; (d) it appears on the status board; (e) it is in the
  CI_SUITES allowlist in fleet/checks/rig-ci-scope.sh or it will never execute; (f) a red-proof
  exists for each assertion.
