# BENCH-OOB-GRADING (#26) — reconciliation audit (READ-ONLY, no changes)

Date 2026-07-21. Repo /home/stack/charon-private (fleet RIG). Verified against code/perms/git, not the ticket text.

## VERDICT for #26: VERIFY-ONLY
Minimal path to done: bring the daemon live (`sudo bench-grader-setup.sh`), run the 3 acceptance checks, human sign-off → close #26. The build landed; the defect the ticket cites is already fixed on master; both stale deps have landed.

---

## Claim 1 — Is the OOB grader deployed + live? MOSTLY YES (code+substrate live; daemon process not currently running)

- `fleet/benchmark/grader-daemon.py` — EXISTS, 36 KB, fully wired (drop-spool two-phase capture protocol, sole ledger writer, versioned scorecard append at :599). Not a stub.
- `fleet/benchmark/bench-grader-setup.sh` — EXISTS. Idempotent root provisioner: installs pytest/hypothesis for bench-grader, sets ACL traverse/rwx, deploys graders to `/home/bench-grader/keys/preflight` (0700), starts the daemon under bench-grader via setsid/nohup, fail-loud verify.
- Dedicated unix user — CONFIRMED: `getent passwd bench-grader` → `bench-grader:x:999:989::/home/bench-grader:/usr/sbin/nologin` (isolated, nologin).
- Answer-key tree perms — CONFIRMED ISOLATED: `/home/bench-grader` is `drwxr-x---` bench-grader:bench-grader; `/home/bench-grader/keys` + `keys/preflight` return **Permission denied** to the `stack` (graded-agent) user. Setup script deploys keys 0700.
- Grader count "13" — CONFIRMED as the 13 preflight-check graders in `fleet/benchmark/graders/preflight_checks/` (14 .py files minus `_pf_common.py` = 13 check scripts: add-provider-config, align-caps-consistency, config-parity-check, cost-class-normalizer, dedupe-provider-list, deprecate-legacy-timeout, fix-backoff-clamp, header-redaction-test, migrate-provider-keys, reconcile-rank-order, rename-cost-field, retry-budget-wire, usage-audit). Plus scenario graders s0–s6/real/preflight in `graders/`.
- Daemon RUNNING right now? NO proc visible (`pgrep -laf grader-daemon` → none). Runtime state only (WSL box likely rebooted); re-provision restarts it. Not a code gap.

## Claim 2 — 3 integrity invariants
- (a) keys unreadable from graded-agent user — **HOLDS** (verified perms above; `cat` as stack → Permission denied).
- (b) fabricated agent-pasted score does NOT change ledger — **ENFORCED in master code**. Daemon is sole ledger writer; `_handle_capture` (grader-daemon.py:501) does FLAW-3 enum validation (:527-532, rejects bad verdict/gate) and, for an UNPAIRED FINAL (the forged-direct-spool shape), requires `state/model-used/<ref>` provenance match (:571-573) else REJECT. Agent's pasted score is advisory; daemon computes/appends.
- (c) deterministic re-grade — plausible (pure graders over a read-only snapshot) but not machine-proven here; this is the one item that still needs an actual run for sign-off.
- **CITED DEFECT IS FIXED**: the ticket's "known defect" (grader-daemon.py:410 hardcodes "active"; :452 never reads req["stage"]) was resolved by STAGE-DEMUX. Master now has `_resolve_trust_stage(req)` (:413, reads canonical `trust_stage` then legacy `stage`) and `_append_capture_row(..., trust_stage=trust_stage)` (:589-596). Col-16 trust axis is now expressible end-to-end. (Fail-closed default flip is a separate STAGE-FAILCLOSED follow-up, not #26.)

## Claim 3 — Supersession vs merged EVAL-* : #26 intent DELIVERED (via multiple landed tickets), not "never built"
EVAL-* pipeline is landed on master: EVAL-PIPELINE-CONSOLIDATE (PR #73, one item-bank + adaptive runner), EVAL-GRADER-PROVISION (38af193), EVAL-TAXONOMY-ALIGN (f83810b, #63), EVAL-TIER-CANON (#70), EVAL-DERIVED-BUDGETS (#66), EVAL-LATENCY-GATE (#59), EVAL-PROMOTION-GATE (9f644a1, #85 — discrimination gate on both write paths), LEG-PREFLIGHT-CANARY (#60) — all have `fleet/state/done/` markers.
#26's specific contribution (OOB isolation + trust axis + forged-score rejection + versioned scorecard) is delivered by: landed OOB Wave-1 (f5fc2be) + STAGE-DEMUX + FLAW-3/EVAL-GRADER-PROVISION + EVAL-PROMOTION-GATE. So the OOB grader IS built and live inside the merged pipeline. #26 is not superseded-and-discarded — its scope shipped; only human verify remains.

## Claim 4 — Dependency staleness (both stale, both NOW satisfied)
- `depends_on: STAGE-DEMUX` — STAGE-DEMUX **LANDED on master**: PR #115 (merge af31903, feat commit 3238f7c), board-retired 68cf433, done-marker present. The archived location is post-merge cleanup, not evidence it didn't land.
- `build-after: BENCH-PROVISIONAL-SCORING (#20)` — **LANDED on master**: PR #107 (merge 3714307), commits 9c5714a/facfc23/8422ce6. Ticket text ("#20 is still PARKED") is STALE/WRONG. Branch `feat/bench-provisional-scoring` merged.

---

## Bonus — status of the two companion tickets
- **MODEL-PREFLIGHT — SUPERSEDED (self-declared).** Its own frontmatter: `superseded_by: EVAL-PIPELINE-CONSOLIDATE, EVAL-GRADER-PROVISION, EVAL-DERIVED-BUDGETS`; reduced to CANDIDATE-SLATE + design-of-record (owns only `fleet/state/PREFLIGHT-CANDIDATES.md`). Code surfaces already moved to the merged EVAL-*. → retire/keep as slate only.
- **GRADER-SECFIX-RECONCILE — NOT superseded; REAL remaining work.** The security hardening (F1 sandbox-confine, F2 kill shell-injection, F5 false-green guard + 3 security tests) still lives ONLY on branch `feat/bench-oob-grading` (2 commits ahead of master: e879957, f5fc2be) and never landed. Evidence it is unmerged: master daemon has no `_confine`/`SandboxError`; `graders/real.py:54` still runs `subprocess(..., shell=True)` — the exact F2 injection surface; `graders/reds_replay.py` does not exist on master. This is genuine un-landed security-merge work (weave hardening into canonical daemon, retire the side branch), independent of the EVAL-* pipeline.
