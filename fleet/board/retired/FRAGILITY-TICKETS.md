tier: economy
difficulty: 1  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: docs
branch: feat/fragility-tickets
depends_on: DIFFICULTY-SCHEMA
real-dep: DIFFICULTY-SCHEMA (shared fleet/board/ writes — sequence to avoid concurrent board mutations)
owns: /home/stack/charon-private/fleet/board/
accept: ls /home/stack/charon-private/fleet/board/PROVIDER-PROBE-FIX.md /home/stack/charon-private/fleet/board/ACTION-PIN-POLICY.md /home/stack/charon-private/fleet/board/DOCKER-SMOKE-CLEANUP.md /home/stack/charon-private/fleet/board/CI-WORKFLOW-POLICY-GATE.md
prompt: /home/stack/charon-private/prompts/fragility-tickets.md
scope: Turn the fragility sweep findings (HANDOFF-2026-07-04-v2 §"Sub-session outputs" #1)
  into individual fleet board tickets. Five tickets to create:
  (1) PROVIDER-PROBE-FIX — the /charon provider-add probe mangles URLs and blocks valid
  providers (fragility finding #4). Files: src/charon/gateway.py, src/charon/config.py,
  src/charon/providers.py. tier strong.
  (2) ACTION-PIN-POLICY — adopt the operator-approved major-tag policy for first-party
  actions/* + keep strict pins for third-party (fragility finding #3, decision #7). Files:
  .github/workflows/*.yml. tier economy.
  (3) DOCKER-SMOKE-CLEANUP — add trap-based cleanup to release.yml, dynamic container
  name/port to heavy.yml (fragility finding #6). Files: .github/workflows/release.yml,
  .github/workflows/heavy.yml. tier economy.
  (4) CI-WORKFLOW-POLICY-GATE — one tools/check_workflows.py gate enforcing action-ref
  policy, rejecting fragile Windows smoke patterns, requiring path triggers for
  packaging-sensitive workflows (fragility finding #8). Files: tools/check_workflows.py,
  tools/gates.json. tier strong.
  (5) PROVIDER-URL-HELPER — deduplicate provider URL/path construction across providers.py,
  config.py, discover.py, cli.py (fragility finding #9). Files: src/charon/providers.py,
  src/charon/config.py, src/charon/discover.py. tier strong.
  This is a documentation/ticket-creation task, not a build task. Suggested agent: this
  session (manager) or glm-5.2 (economy) — mechanical ticket writing.

## Fragility-wave-A mechanizations landed (2026-07-10)
- MECH-1 Worktree-leak guard — launcher pre-creates the worktree off origin/master + post-session
  leak detector (`fleet/leak-guard.sh`: leak_worktree_setup/leak_detect/leak_capture/safe_worktree_remove,
  wired into `fleet/fleet-droid.sh`). Test: `fleet/tests/worktree-leak-guard.test.sh`.
- MECH-2 Auto-`done` on merge — `fleet/reconcile-merged.sh` maps merged PR branches to tickets and
  runs done.sh for any not-yet-done; wired into `fleet/preflight.sh` scan path (safety-net).
  Test: `fleet/tests/reconcile-merged.test.sh`.
- MECH-3 Surface+protect needs-push — `detect_needs_push` in `fleet/preflight.sh` auto-registers a
  reds.tsv red per stranded marker (blocks preflight until landed); `safe_worktree_remove`
  (leak-guard.sh) refuses to remove a worktree with a live needs-push marker, used by
  `fleet/retire-done.sh`. Test: `fleet/tests/needs-push-gate.test.sh`.
