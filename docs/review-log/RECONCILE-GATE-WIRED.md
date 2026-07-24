# RECONCILE-GATE-WIRED — review note

**Ticket:** RECONCILE-GATE-WIRED (§1.3 of UNIFIED-RECONCILIATION-GATE-DESIGN.md, PR #178)
**Class:** rig-meta — built-but-inert meta-gate
**drift-primitive:** graph-reachability (KS29 leg)
**Build:** 2026-07-23 (initial, branch stranded off-master) + 2026-07-23 SALVAGE (rebase + wire + accuracy fixes)

## SALVAGE pass (this build)

The check + test existed on an unlanded branch (`feat/reconcile-gate-wired`, commit `d603494`,
"detector, no wire") 33 commits behind master. Salvaged, not rebuilt:

1. **Rebased** cleanly onto current master (no conflicts) -> `940bce8`.
2. **Fixed 3 real accuracy bugs** surfaced by running the check against the LIVE rig (all
   pre-existing false positives in the original salvaged implementation, not introduced by the
   rebase):
   - Firing-layer scan never looked at the RIG's OWN `.github/workflows/*.yml` (only the
     product's) — false-RED'd `bandit.sh`/`gitleaks.sh`/`semgrep.sh`/`rig-ci-scope.sh`, which are
     genuinely merge-blocking-wired on this repo's own CI.
   - Reachability was single-hop only — missed checks reached via an intermediate dispatcher
     (`rig-ci.yml` -> `rig-ci-scope.sh` -> `substrate-first-gate.sh` -> `substrate_first_gate.py`).
     Now a fixed-point transitive closure over the dispatch graph (matches the design's own
     "graph-reachability", not mere adjacency).
   - R-H's regex matched declared basenames inside COMMENTS (e.g. an illustrative
     `fleet/checks/foo.sh` in a docstring), a false positive the transitive-closure fix would have
     otherwise newly exposed. Now skips comment lines.
   - Net effect: live R-G count dropped from 19 (false + true positives) to 11 (all true positives,
     see below) once wired.
3. **WIRED** `reconcile_gate_wired_gate()` into `fleet/preflight.sh`'s `scan` dispatch (same
   auto-register-tracked-red pattern as `board_gate`/`coverage_gate`/`graphify_freshness_gate`) —
   closes the gate's own founding complaint (it no longer appears in its own R-G report).
4. **Found + fixed a real, load-bearing pre-existing bug while wiring**: `VALID_AREA` in
   `preflight.sh` did not include `rig-meta`, so `cmd_add`'s `die()` (which calls `exit`, not
   `return`) silently killed the ENTIRE preflight process the instant any rig-meta gate
   (`coverage_gate` already used this area; now this gate too) actually went RED — the error
   message itself was swallowed by the caller's `>/dev/null 2>&1`. This was previously undetected
   because `coverage_gate` has apparently never gone RED in practice. Fixed by adding `rig-meta`
   to `VALID_AREA` (one line, root-cause fix, not a workaround).
5. **Added test (e)** to the fail-on-revert suite: asserts against the REAL `fleet/preflight.sh`
   (not a fixture) that the gate is called and that reverting the wiring re-surfaces
   `reconcile-gate-wired.sh` in its own live R-G report. Verified genuinely load-bearing (manually
   simulated a full revert in a scratch copy — correctly flips RED).

## Known, disclosed gaps (honest seam, not silently skipped)

- **R-I is NOT implemented.** The design doc's §1.3 note describes R-I ("declared+fired but only
  on a master-gated path while reconciling a feature branch -> deploy-context-blind") as part of
  the full vision; the original salvaged commit scoped down to R-G/R-H only (its own commit
  message and this doc said so from the start) and shipped no R-I fixture. Implementing it
  reliably needs branch/deploy-context classification of firing layers, not just text
  reachability — deferred rather than shipping an untested heuristic in a gate-critical tool.
- **11 pre-existing R-G items remain** (`base-integrity.sh`, `bridge-health.py`,
  `config-ssot-gate.sh`, `end-session.sh`, `gate-creation-standard.sh`, `gpt55-primary.sh`,
  `large-file-guard.sh`, `no-anthropic-in-sg.sh`, `report.sh`, `rule-sync.sh`,
  `selfcheck-cycle.sh`) — declared checks genuinely not fired from any real firing layer today.
  These predate this ticket and are explicitly `RECONCILE-WIRING`'s tracked scope (that ticket's
  `depends_on` already lists this one); the new `reconcile-gate-wired-gap` tracked red points
  there rather than hiding the count. Wiring all 11 individually here would encroach on
  `RECONCILE-WIRING`'s single-owner region (`fleet/preflight.sh` scan-chain / `land.sh`
  pre-condition / `foreman-cadence.sh` timer) for the OTHER three reconcilers too — out of this
  ticket's `owns:`.

## What was built

1. **`fleet/checks/reconcile-gate-wired.sh`** — standalone bash+Python check that:
   - Collects **declared checks** from: `fleet/checks/*.sh + *.py`, `tools/check_*.py + *.sh` (cross-repo), `RULE-REGISTRY.tsv` mechanized rows, `EVAL-REGISTRY.md` ADOPT rows with check paths
   - Collects **fired checks** by substring-matching declared basenames across firing-layer files (preflight.sh, land.sh, validate_board.sh, hooks/, foreman-cadence.sh, product-side gate_runner.py + workflows/*.yml)
   - Computes **R-G** (declared but not fired → built-but-inert RED) and **R-H** (fired but not declared → unregistered RED)
   - Reports **UNVERIFIED** (fail-closed) when product repo checkout is absent
   - Reuses the rule-coverage.sh pattern (bash+embedded Python; env-var test seams)

   Fired-set reachability is now a **fixed-point transitive closure**: a firing layer that
   dispatches to a declared check (e.g. a CI workflow -> `rig-ci-scope.sh` -> another check) adds
   that check's own file to the frontier, so checks reached only via an intermediate dispatcher
   are no longer false-RED'd. R-H's comment lines are skipped (avoids false positives on
   illustrative paths in code comments).

2. **`fleet/tests/reconcile-gate-wired.test.sh`** — fail-on-revert test, 5 cases:
   - (a) declared-but-unwired → R-G RED
   - (b) wire into firing layer → rig-side GREEN
   - (c) unregistered checks/ invocation → R-H RED
   - (d) product repo absent → UNVERIFIED (fail-closed)
   - (e) NEW (this salvage): the REAL `fleet/preflight.sh` actually calls
     `reconcile_gate_wired_gate` and the live check no longer reports itself in R-G — reverting
     the wiring flips this RED (manually verified).

3. **`fleet/preflight.sh`**: `reconcile_gate_wired_gate()` wired into the `scan` dispatch (after
   `graphify_freshness_gate`, before `retire-done.sh`) using the identical auto-register-tracked-
   red pattern as every other rig gate in this file. `VALID_AREA` gained `rig-meta` (bug fix, see
   above).

## WLS-7 validation

The stass-allie WLS-7 review (2026-07-23) validated the implement-as-pattern posture:
"no external tool reconciles Charon's own state; K8s/Terraform desired-vs-observed is the pattern."
This check implements that validated pattern — graph-reachability over declared-vs-fired nodes.

## Accept verification

- [x] Standalone `bash fleet/checks/reconcile-gate-wired.sh` runs (exit 1 = RED, reflecting the
      11 pre-existing genuinely-unwired checks — see "Known, disclosed gaps" above)
- [x] Isolated via RCW_* env vars for test fixtures
- [x] Product-repo-absent → UNVERIFIED, fail-closed (exit non-zero)
- [x] fail-on-revert test passes (11/11, including new wiring-revert case (e))
- [x] WIRED into `fleet/preflight.sh`'s `scan` dispatch — reconcile-gate-wired.sh no longer
      appears in its own live R-G report (founding complaint closed)
- [x] `bash fleet/validate_board.sh` GREEN
- [x] `fleet/tests/sync-checkouts.test.sh` (D0-D3: the one suite that actually executes
      preflight.sh's real `scan` dispatch end-to-end) still passes — the new gate did not break
      the chain
- [x] `fleet/tests/rig-ci.test.sh` still passes (11/11) — unrelated CI-scope gate unaffected
- [x] All owned files in scope: `fleet/checks/reconcile-gate-wired.sh`,
      `fleet/tests/reconcile-gate-wired.test.sh`, plus `fleet/preflight.sh` (wiring, per this
      ticket's explicit brief: "WIRED into a firing layer ... so it's not itself built-but-inert")
- [x] Reuses rule-coverage.sh pattern (embedded Python, env-var test seams)
