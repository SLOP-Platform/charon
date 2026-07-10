# FRAGILITY-TICKETS review note

Filed the five fleet board tickets called for by the fragility sweep
(HANDOFF-2026-07-04-v2 §"Sub-session outputs" #1), each with a matching
brief under `fleet/board/briefs/`:

- PROVIDER-PROBE-FIX (strong) — finding #4, `/charon provider-add` probe
  rejects valid keys on `POST /chat/completions {"model": "."}`.
- ACTION-PIN-POLICY (economy) — finding #3 / decision #7, major-tag policy
  for first-party `actions/*`, strict SHA pins kept for third-party.
- DOCKER-SMOKE-CLEANUP (economy) — finding #6, trap-based cleanup +
  dynamic container name/port for `heavy.yml` smoke job.
- CI-WORKFLOW-POLICY-GATE (strong) — finding #8, `tools/check_workflows.py`
  gate enforcing action-ref policy, Windows smoke pattern rejection, and
  packaging path triggers; red-proof required per Structural Rule 3.
- PROVIDER-URL-HELPER (strong) — finding #9, dedup provider URL/path
  construction into one stdlib helper.

On inspection, all five ticket files (and their briefs) were already
present in the worktree from a prior run of this same ticket — content
matches the work-spec scope, `fleet/validate_board.sh` reports no RED
issues attributable to any of the five (the six pre-existing RED
orphan-marker lines are unrelated `state/done/*` entries outside this
ticket's scope), so this pass is a verify-and-commit rather than an
author-from-scratch pass.

Left `fleet/board/BENCH-OOB-GRADING.md` (modified) and
`fleet/board/CLINE-UNWRAP-SHIM.md.parked` (deleted) uncommitted — both
predate this ticket's claim and belong to other in-flight work, not the
fragility-sweep ticket set.
