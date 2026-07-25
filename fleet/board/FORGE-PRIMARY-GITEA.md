repo: charon-private
tier: strong
difficulty: 4
priority: 1
work_class: ci-infra
branch: feat/forge-primary-gitea
owns: fleet/forge.sh, fleet/land-push.sh, fleet/submit.sh, fleet/land-needs-push.sh, fleet/reconcile-merged.sh, fleet/state/FORGE-PRIMARY.md, fleet/tests/forge-failover.test.sh
depends_on:
dep-kind:
source: OPERATOR DECISION 2026-07-24 — "Gitea is PRIMARY." Standing concern
  [[git-hosting-gitea-primary]]: a GitHub outage must never block landing again. GitHub's API threw
  transient `Something went wrong` failures on `gh pr create` in a prior session and stalled the
  land queue outright.
priority_justification: P:1 (PRIORITY-LADDER "attached CG work") — operator-escalated this session,
  but weighed honestly against the eleven live P:0s it would otherwise sit beside: nothing is broken
  on the land path TODAY (GitHub is up), this mitigates a recurring outage CLASS rather than a live
  breakage, and it is a multi-file cutover rather than a fast unblock. It ranks above every P:2+
  because the land path is the rig's single throughput chokepoint and has already been stalled once
  by a forge the rig does not own.
work_class_note: ci-infra — the push/land/PR spine. A defect here does not spend money, it strands
  finished work, which is the failure mode this ticket exists to remove.
note: |
  DIRECTION OF AUTHORITY (the decision this ticket implements): Gitea on `c1-10p` is the PRIMARY
  push/land target; GitHub becomes an ASYNC MIRROR. Both checkouts already carry BOTH remotes
  (`origin` = GitHub, `gitea` = the rig's Gitea host), and several branches — e.g.
  `feat/sg-issue-control-plane` — are already pushed to BOTH. So this is NOT a greenfield migration:
  partial mirroring already exists with NO declared authority, which is the actual defect. The
  ticket's first job is to make the direction EXPLICIT and mechanized, not to invent a mirror.

  BLAST RADIUS — every one of these assumes GitHub is authoritative today:
    - fleet/land.sh, fleet/land-push.sh  — the sanctioned push paths [[sanctioned-push-paths]]
    - fleet/submit.sh, fleet/land-needs-push.sh — PR creation / needs-push drain
    - every `gh pr create|ready|merge|view` call site (land.sh, land-push.sh, submit.sh,
      land-needs-push.sh, fleet-droid.sh, preflight.sh)
    - fleet/gh-cache.sh — the gh seam GITHUB-LIMITS-HARDENING is currently rebuilding
    - the verify-merged / reconcile-merged legs (fleet/done.sh, fleet/reconcile-merged.sh) and the
      AUTO-DONE-MARK path that writes fleet/state/done/<id> off a merged-PR verdict
    - CI runner wiring (.github/workflows/*, the self-hosted 4-LOM runner, rig-ci-scope.sh)
  This ticket converts ONLY the unowned subset (see owns:) and hands the CONTENDED subset to a
  declared follow-on — see ds:. It must not silently widen into a seven-way multi-writer edit of
  the files six other live tickets are already rewriting.

  KNOWN CONSTRAINT — RECORD IT, DO NOT RE-DIAGNOSE IT: the Gitea rig repo `stack/charon-private` is
  PRIVATE. An anonymous `curl` against it returns 404. That is EXPECTED, not a fault; it has been
  misdiagnosed as a broken mirror before. Any health probe this ticket adds must authenticate and
  must distinguish 404-because-private from 404-because-absent, or it will manufacture false reds.

  KNOWN CONSTRAINT — the `gh` CLI is already partially broken here: with Projects-classic enabled,
  `gh pr view` / `gh pr edit` fail and the rig uses the REST API instead
  [[gh-projects-classic-breaks-subcommands]]. Making Gitea primary re-opens that whole surface —
  Gitea's API is NOT gh-compatible, so every call site must go through the seam below rather than
  growing a second set of bespoke curl invocations. [[no-stiff-single-provider-tools]]
  ANTI-ACCRETION: ONE seam (fleet/forge.sh), not a per-call-site if/else. [[fix-root-cause-never-workaround]]
accept: |
  A. ONE FORGE SEAM, NOT N BRANCHES. `fleet/forge.sh` exposes a forge-agnostic verb set that every
     converted call site uses — at minimum `push`, `pr_create`, `pr_ready`, `pr_merge`, `pr_state`,
     `merged_for_branch`. It resolves the PRIMARY forge from ONE recorded source
     (fleet/state/FORGE-PRIMARY.md + an env seam, e.g. `FLEET_FORGE_PRIMARY`), defaulting to gitea.
     No call site may branch on forge identity itself. REUSE the existing `gitea`/`origin` git
     remotes; do NOT hard-code URLs at call sites. Run `bash fleet/reuse-check.sh fleet/forge.sh`
     before creating the file and record the result.
  B. AUTHORITY RECORDED, NOT IMPLIED. `fleet/state/FORGE-PRIMARY.md` states which forge is
     authoritative for (i) branch pushes, (ii) PR/merge, (iii) the merged-verdict that the
     auto-done-mark path trusts — and states that GitHub is a MIRROR whose state is never
     authoritative for closing a ticket. Existing dual-pushed branches (e.g.
     `feat/sg-issue-control-plane`) are reconciled to that statement, not left ambiguous.
  C. CONVERTED PATHS. fleet/land-push.sh, fleet/submit.sh, fleet/land-needs-push.sh and
     fleet/reconcile-merged.sh route ALL forge operations through `fleet/forge.sh`. Zero direct
     `gh ` invocations remain in those four files — the acceptance is "zero remaining", measured on
     the branch, not "most converted".
  D. ASYNC MIRROR, FAIL-LOUD-BUT-NON-BLOCKING. After a successful primary push/merge, the GitHub
     mirror push is attempted; a mirror FAILURE must be recorded LOUDLY to state (a red row or a
     mirror-lag file) and must NOT block the land. A mirror that silently stops mirroring is the
     same class as a gate that silently stops gating [[gates-must-actually-run]]. Symmetrically, a
     PRIMARY failure must BLOCK — it is not downgraded to advisory.
  E. FAILOVER PROVEN BY EXECUTION, NOT ASSERTED (the core of this ticket). With GitHub made
     unreachable — no network path to api.github.com, injected in the fixture, NOT by deleting the
     remote — a full land completes end to end via Gitea: branch pushed, PR created, PR merged,
     merged-verdict read back, done-marker written with real proof. Paste the run. A mirror that has
     never been failed over to is not a mirror.
  F. THE REVERSE CASE, ALSO PROVEN. With GITEA unreachable and GitHub up, the land BLOCKS with a
     clear error naming the primary forge — it must NOT silently fall back to the mirror and land
     work on the non-authoritative forge. Silent forge-swap is a split-brain generator.
  G. THE PRIVATE-REPO PROBE IS NOT A RED. An authenticated probe of `stack/charon-private` succeeds;
     an ANONYMOUS probe returning 404 is classified `private-expected`, never a fault. Assert both.
  H. FAIL-ON-REVERT (fleet/tests/forge-failover.test.sh — hermetic, mktemp -d fixture with stubbed
     forge endpoints; NEVER pushes to a real remote and never re-points the live remotes):
     1. GitHub-unreachable fixture => land completes via Gitea, rc 0, PR + merge verdict recorded.
        Revert the seam (restore direct `gh` calls) => this case goes RED.
     2. Gitea-unreachable fixture => land BLOCKS, rc non-zero, error names the primary. Revert the
        block => RED.
     3. Mirror-push failure with primary healthy => land SUCCEEDS and a mirror-failure record
        exists. Remove the record write => RED (a silent mirror failure must be impossible).
     4. Anonymous 404 on the private repo => classified `private-expected`, rc 0. A probe that reds
        on it => RED.
     5. NON-VACUOUS: a fixture in which ZERO forge operations were executed must RED
        (`0 forge ops`), never report a clean land. Zero work done is never a green land.
     6. BOUNDED: every case carries a finite timeout — a hung forge call must fail fast, since
        "the land queue stalled" is the exact symptom being fixed [[latency-is-a-failure-class]].
  I. `bash fleet/tests/forge-failover.test.sh` exits 0 AND is executed by a real runner — it is
     named `*.test.sh` so `fleet/gate.sh`'s glob picks it up; paste the runner line. A proof no
     runner executes is not evidence.
  J. `bash fleet/validate_board.sh` rc 0 modulo pre-existing reds. Run the named suite only — do NOT
     run the full fleet/tests sweep (the benchmark grader suites block for hours).
  K. ADVERSARIAL REVIEW REQUIRED (reviewer != builder): this rewrites the sanctioned push path. The
     reviewer must confirm E and F BY EXECUTION in the fixture, not by reading the diff, and must
     confirm that no converted file retains a direct `gh ` call.
scope: |
  Rig-only [[product-vs-build-rig-boundary]]. PHASE 1: the forge seam, the recorded authority, the
  four UNOWNED push/land/PR files, and the failover proof. EXPLICITLY OUT OF SCOPE — the CONTENDED
  surfaces, which convert in a declared follow-on so this ticket does not become a seven-way
  multi-writer edit: fleet/land.sh (HANDOFF-GATE-NONBYPASSABLE, RECONCILE-WIRING),
  fleet/gh-cache.sh (GITHUB-LIMITS-HARDENING, PREFLIGHT-VERIFY-MERGED-GHCACHE), fleet/done.sh
  (GITHUB-LIMITS-HARDENING, MARKER-PROOF-MECHANIZE, RECONCILE-BOARD-PR-DONE), fleet/preflight.sh
  (seven owners), fleet/fleet-droid.sh (four owners), and the CI runner wiring
  (.github/workflows/*, rig-ci-scope.sh — GITEA-ACTIONS-CI-SPIKE is the parked spike that decides
  whether CI itself moves). Those files keep working through GitHub until the follow-on converts
  them; the seam is designed so that conversion is mechanical.
serial_justified: |
  The seam, the recorded authority and the failover proof are ONE contract. A seam with no recorded
  primary is a config-less abstraction; a recorded primary with no seam is a comment; and either
  without the executed failover is exactly the never-failed-over mirror the operator is calling out.
  The four converted files are the minimum set that makes ONE land path end-to-end forge-agnostic —
  converting fewer leaves a land that still dies when GitHub does, which fails acceptance E.
ds: |
  ## Dependencies & sequence
  depends_on: (none) — CLAIMABLE NOW. Its owned surface (fleet/forge.sh, fleet/land-push.sh,
  fleet/submit.sh, fleet/land-needs-push.sh, fleet/reconcile-merged.sh,
  fleet/state/FORGE-PRIMARY.md, fleet/tests/forge-failover.test.sh) collides with NO live board
  ticket — verified 2026-07-24 against every `owns:` line on the board; the four existing files are
  currently UNOWNED and the three others are new.
  DELIBERATELY NOT DEPENDED ON: GITHUB-LIMITS-HARDENING owns fleet/gh-cache.sh and fleet/done.sh —
  both are OUT of this ticket's owns by design, so no edge is needed and none is declared. Adding
  one would block a claimable ticket behind an unlanded branch for no build reason.
  FOLLOW-ON (open it when this lands, do NOT fold it in here): convert the CONTENDED surfaces named
  in scope: — fleet/land.sh, fleet/gh-cache.sh, fleet/done.sh + the auto-done-mark verdict,
  fleet/preflight.sh and fleet/fleet-droid.sh — each sequenced behind its current owners. CI cutover
  stays with GITEA-ACTIONS-CI-SPIKE (parked, product repo).
  RELATED, NOT BLOCKING: GITEA-ACTIONS-CI-SPIKE (parked) decides whether CI moves to Gitea Actions;
  this ticket decides where CODE and MERGES live. Landing this does not require that spike.
  CONCURRENCY-SAFETY: never re-point the live `origin`/`gitea` remotes mid-session — all failover
  testing is hermetic in a mktemp fixture. Branch feat/forge-primary-gitea is unused.
