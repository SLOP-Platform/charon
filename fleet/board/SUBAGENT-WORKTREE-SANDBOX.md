repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
branch: feat/subagent-worktree-sandbox
depends_on:
owns: fleet/state/SUBAGENT-WORKTREE-SANDBOX-DESIGN.md
priority: P2
accept: |
  A design doc (fleet/state/SUBAGENT-WORKTREE-SANDBOX-DESIGN.md) that:
  (1) Documents the observed escape: a build sub explicitly instructed "do NOT touch the product repo"
      wrote into /home/stack/code/charon/pyproject.toml (truncating it) via a cwd-reset + heredoc
      absolute-path write — self-caught and restored (2026-07-22, the vulture-investigate sub). Root
      CLASS: subagents/droids can write OUTSIDE their assigned worktree via absolute paths / cwd resets;
      a natural-language instruction is NOT a filesystem boundary. [[one-checkout-one-agent]]
  (2) EVALUATES adopt-first sandbox mechanisms to CONFINE a sub's writes to its own worktree, recording
      the verdict as an EVAL-REGISTRY row: bubblewrap/bwrap (bind-mount the worktree rw, everything else
      ro), Linux landlock, firejail — vs a PreToolUse path-guard hook (reject any Write/Edit/Bash write
      whose realpath escapes the assigned worktree root). Adopt a maintained sandbox if one fits; hand-roll
      only the novel glue. [[adopt-substrate-build-only-novel-slice]]
  (3) Spawns a scoped BUILD follow-up ticket for the chosen mechanism, carrying a fail-on-revert canary:
      a sub attempting an out-of-worktree write is BLOCKED; neuter the guard -> the escape succeeds ->
      canary FAILS. [[gates-must-actually-run]]
scope: |
  Design-first (adopt-vs-hand-roll eval) for confining subagent/droid filesystem writes to their assigned
  worktree, closing the instruction-is-not-a-boundary escape observed 2026-07-22. P2 (queued behind the
  RANK-0 lane). [[one-checkout-one-agent]] [[security-is-a-ratchet-gate]]
ds: |
  ## Dependencies & sequence
  - depends_on: (none). Design/eval only — owns a single design doc, no code, so no build-order dep.
  - relationship: SIBLING to LEG-SANDBOX-HARDEN (SECURITY project, canary-exec cred-exfil) — same
    confine-untrusted-exec family, different surface (sub filesystem writes). A single adopted sandbox
    (e.g. bwrap) may cover both; coordinate the mechanism choice across the two tickets.
  - priority: P2 (operator-set 2026-07-22) — below the RANK-0 lane, above general backlog.
