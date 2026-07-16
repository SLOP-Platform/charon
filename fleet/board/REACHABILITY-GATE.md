tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/reachability-gate
repo: charon-private
priority: HIGH
depends_on:
owns: fleet/checks/no-unreachable-paths.sh, fleet/state/REACHABILITY-AUDIT.md
serial_justified: PART3's gate + allowlist can only be scoped once PART1's audit produces the
  REACHABILITY-AUDIT.md matrix of actual cross-boundary hits and PART2 fixes the contract — the
  ticket's own ds note states "gate build follows once the audit matrix + allowlist scope are
  known," a hard audit-then-gate ordering, not two independent surfaces.
accept: |
  AUDIT + ROOT-CAUSE + GATE for the RECURRING "hardcoded path that another user/process/deploy cannot
  reach" defect. This is the root cause of the MODEL-PREFLIGHT wall: grader-daemon.py + deploy-preflight-
  graders.sh hardcode /home/stack/... paths that the bench-grader user (uid 999, not in group stack)
  cannot traverse (/home/stack is drwxr-x--- stack:stack), so the OOB grader can neither deploy nor run.
  Operator (2026-07-13): "We seem to do this all the time." Same class = deploy-drift (source vs /data
  volume), product-vs-rig leaks, and fresh-install path assumptions.

  PART 1 — AUDIT (use the code map). Locate + USE the operator's "code map app" (the what-reads/writes-what
  dependency map — find it; do NOT hand-grep blindly if the map already answers it) PLUS grep, to
  enumerate EVERY hardcoded absolute path in product (src/charon) + rig (fleet/) that is read or written
  across a boundary: (a) a different unix user (bench-grader vs stack), (b) a container/volume boundary
  (source tree vs mounted /data), (c) a fresh-install / different-host boundary, (d) the product-vs-rig
  boundary (product must never read /home/stack or fleet). For each hit: path, who writes, who reads,
  which boundary it crosses, why it's unreachable/fragile today. Output a matrix in REACHABILITY-AUDIT.md.

  PART 2 — ROOT CAUSE (documented). Why this recurs: single-user /home/stack dev assumption; boundaries
  (bench-grader user, /data volume, fresh install, public product) added AFTER the paths were written;
  no portability contract; nothing gates it. State the CONTRACT going forward: cross-boundary paths come
  from config/env (CHARON_HOME, $KEYS, XDG, relative-to-script), never a hardcoded dev-box absolute.

  PART 3 — GATE (mechanized, fail-loud). fleet/checks/no-unreachable-paths.sh: FAIL when code introduces a
  hardcoded cross-boundary-unreachable absolute path — flag string literals matching /home/stack,
  /home/<non-self-user>, hardcoded /data (outside the config layer), or dev-box absolutes, UNLESS
  explicitly allowlisted with a documented reason. Wire into the fleet gate + product CI (register in the
  gate-registry). FAIL-ON-REVERT test: reintroduce a /home/stack literal in a boundary-crossing file ->
  gate RED. Keep the allowlist tiny + reasoned.

scope: |
  Cross-cutting hygiene/portability. Prevents the recurring reachability class (bench-grader, deploy-drift,
  product-leak, fresh-install) at the gate instead of discovering it live. [[product-vs-build-rig-boundary]]
  [[charon-deploy-drift-lessons]] [[charon-production-readiness-mindset]] [[gates-must-actually-run]]
ds: |
  depends_on: none (audit can start now). PART 3 gate should reuse the existing gate-registry + boundary-
  check patterns (tools/check_boundary.py, fleet checks). Audit is a background session; gate build follows
  once the audit matrix + allowlist scope are known. Adversarial review the gate (it must actually fire).
note: HIGH PRIORITY (operator 2026-07-13). Surfaced by the MODEL-PREFLIGHT bench-grader wall. Audit launched
  as a background session this session; gate build is the follow-up deliverable.
