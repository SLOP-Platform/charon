repo: charon
priority: 0
released: |
  RELEASED + RAISED TO P0 2026-07-26 by operator. Two reasons:
  (1) SECURITY-OPERATIONAL. Key rotation that requires a container restart is a rotation you will not
  perform under pressure. `secrets.apply_to_env()` uses `os.environ.setdefault`, a structural no-op for
  any key already resident in the process env, so a rotated key on disk is INERT until restart. That is
  the failure mode that matters precisely when a key is believed compromised
  [[security-is-a-ratchet-gate]].
  (2) THE WORK ALMOST EVAPORATED. This ticket never landed, and its 11 dogfood-eval implementations
  became the ONLY copies in existence — living in untracked worktrees that were one reap away from
  deletion. They were salvaged and committed on 2026-07-26 (a0d9000) to
  `fleet/handoff-notes/salvage-reap-2026-07-26/dogfood-SECRET-HOTROTATE-*.diff` (11 diffs + briefs).
  READ THOSE FIRST — 11 models already attempted this; do not start from scratch. Treat them as prior
  art to compare against, NOT as authority: they were never reviewed or landed, and 5 of the 27
  dogfood runs in that batch produced empty diffs. Any diff you adopt must be re-derived and proven
  here.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Graded sample: record into fleet/model-scorecard.tsv. One checkout, one agent — its OWN worktree.
extra-accept: |
  Beyond the pytest line below, the done-contract is OBSERVABLE on the live gateway:
  - rotate a provider key on disk, then prove the NEW key is used WITHOUT a container restart —
    show the before/after and name which provider you rotated.
  - RED-PROOF: revert to setdefault semantics -> the new test goes RED naming the stale-key case.
    Report BOTH exit codes.
  - Do NOT print or commit any real key value at any point.
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: fix/secret-hot-rotation
depends_on:
owns: src/charon/secrets.py, tests/test_secrets.py
accept: PYTHONPATH=src python3 -m pytest tests/test_secrets.py -v -q  # rotating a key already resident in process env takes effect via force-refresh WITHOUT a container restart
prompt: /home/stack/charon-private/prompts/secret-hotrotate.md
scope: #33 (P1). Secret hot-rotation force-refresh. secrets.apply_to_env() uses os.environ.setdefault
  — a structural no-op for any key already resident in process env, so rotating HF_TOKEN (etc.) on disk
  does NOT take effect live; only a container restart picks it up (root-caused this session,
  scratch/hf-token-reload-verify.md, not fixed). Add a force-refresh mode that overwrites already-resident
  keys so provider-key rotation is hot. Coordinate with the /data/rotate-hf.py helper on the gateway host
  (writes new token to secrets.json; today still needs the restart this ticket removes).
  ** PRODUCT-BOUNDARY FLAG: this BUILD touches the Charon PRODUCT (src/charon/secrets.py), NOT rig code.
  The ticket file is a rig planning artifact; the build itself must keep the product STANDALONE — no
  fleet/SLOP/rig dependency may leak into src/charon. ** RIG (this file) plans it; PRODUCT ships it.
  D&S: depends_on EMPTY (board-unblocked). Independent of the bench pivot cluster.
note: LIVE as of 2026-07-26 (operator raised to P0). Previously staged so no droid claimed it ahead of manager gating; that gate has now been given. Build touches product code (see flag).
