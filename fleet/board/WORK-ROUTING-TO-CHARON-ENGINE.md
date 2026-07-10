tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: engine
branch: feat/work-routing-to-charon-engine
parked: true
depends_on:
real-dep: none functional; sequence AFTER the ADR below is ratified (design-first). Shares
  intent with charon-own-work-engine / pools-redesign capability engine — reuse that model
  pool + grades table, do NOT build a second one.
owns: (design-first — engine/work-router + a headless-run launcher; exact files TBD at ADR)
accept: |
  Given a unit of work, the engine decides Claude-vs-Charon and, when Charon, emits a
  ready-to-run brief + best-fit Charon model + a headless launch command WITHOUT the manager
  hand-deciding each time; a work unit that does NOT need Claude is never spawned as a Claude
  sub-agent (verifiable: dry-run classifier routes a labelled sample set correctly). The
  headless runner (a) runs non-Claude on the 4-LOM gateway, (b) fails over across models on
  session/rate-limit, (c) records exhaustion to the ledger, (d) requires the worker to emit a
  REVIEW PACKET the manager gates on. Reverting the router makes the routing test fail;
  reverting the failover makes the failover test fail.

scope: |
  MECHANIZE routing of manager/sub-session/droid work to the Charon Gateway instead of Claude,
  and make the manager a lean packet-reviewer. Operator has asked for this repeatedly; today
  the manager hand-decides per task. Make it a first-class work-engine capability.

  PROVEN THIS SESSION (2026-07-10) — build on these, they already work:
    * Headless Charon run: `opencode run --model charon/<model> "<brief>"` (cwd = worktree),
      fired via Bash background. The opencode `charon` provider baseURL is the 4-LOM gateway
      (http://10.0.1.60:8080/v1); models incl. deepseek-v4-pro / deepseek-v4-flash / glm-5.2.
      Smoke-tested green (PONG) and drove 3 real PR reviews/fixes end-to-end. ZERO Claude limit.
    * Cross-model failover launcher: scratchpad/charon-run.sh — tries model list in order,
      fails over on 429/quota/session-limit (distinct `limit-failover` vs `error-failover`),
      writes an exhaustion ledger (fleet/provider-exhaustion-ledger.tsv) so a thin pool is
      visible ("add more providers" signal).
    * REVIEW PACKET contract (memory charon-headless-review-loop): worker writes files+lines
      changed · root cause · a FAIL-ON-REVERT test · self-run full-gate result · risk · SHA;
      manager reads ONLY the packet + the critical diff, re-runs the gate, pushes/merges. Keeps
      both axes lean (no Claude-limit spend on the work; payload never enters manager context).

  BUILD (phased; classifier + picker are the ADR-gated parts):
    Phase 1 — PRODUCTIZE the launcher: promote charon-run.sh into the rig as the work ENGINE,
      replacing the `claude`-launching core of fleet-droid.sh (see how-it-relates below). Keep
      failover + ledger + packet-requirement. Non-Claude by default.
    Phase 2 — CLASSIFIER: given a work unit, decide Claude-vs-Charon (does it truly need Claude:
      hard multi-step design/debug, or Claude-specific tooling?) vs routine ticket → Charon.
      Dry-run over a labelled sample set is the acceptance harness.
    Phase 3 — MODEL PICKER: pick best-fit Charon model from the shared pool/grades table
      (reuse pools-redesign capability engine — do NOT fork it). Right-size: cheapest model
      that does the work well; escalate only genuinely hard units.
    Phase 4 — EMIT: produce brief + model + headless command (and, when Claude is truly needed,
      surface that to the operator for explicit OK, per route-work-to-charon-not-claude).

how-it-relates: This is the work ENGINE that plugs INTO the fleet rig, NOT a replacement for it.
  The rig keeps its orchestration (claim / loop-guard / board / D&S / collision-guard); this
  swaps the rig's Claude-launching core for the headless-Charon launcher + packet review. Best
  of both: rig orchestration + zero-Claude-limit leanness. Same engine can drive SLOP
  (mediastack) work once each ticket carries a SLOP-appropriate brief + its own green-gate.

note: |
  PARKED — design-first. ADR the classifier + model-picker + emit path (and the Claude-escalation
  handshake) before build; Phase 1 (launcher productization) is low-risk and could start once the
  ADR frames where it lives. Staged so no droid claims ahead of manager/operator gating.
  Refs: memory route-work-to-charon-not-claude, charon-headless-review-loop,
  subsession-model-and-token-policy, charon-own-work-engine, charon-pools-redesign.
  Artifacts to fold in: scratchpad/charon-run.sh, the 3 REVIEW-PACKET.md examples from PRs
  #90/#92/#93 this session.
