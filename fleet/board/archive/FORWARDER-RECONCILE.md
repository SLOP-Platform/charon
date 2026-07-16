repo: charon
tier: strong
difficulty: 3
work_class: money-path
branch: feat/forwarder-reconcile
depends_on: FAIL-LOUD-CONTRACT
owns: src/charon/forwarder.py, tests/test_forwarder_fail_loud.py, tests/test_forwarder_tool_repair.py
note: |
  Retroactive board ticket for the untracked branch `feat/wire-tool-repair`
  (checked out at /home/stack/code/charon/.claude/worktrees/agent-a4294af67f9d41d80,
  commit af8d795, "feat(forwarder): wire tool_repair into the served-response path
  (CG-critical)" — had NO owns:/board-ticket, which is exactly how it collided
  undetected). Full verified diff/hunk-line evidence at
  fleet/state/TOOL-AUDIT-COLLISION.md RANK 1 — READ IT FIRST, do not re-derive the
  hunk analysis. Do NOT re-run the audit's diff comparison from scratch; the finding
  is: FAIL-LOUD-CONTRACT and feat/wire-tool-repair independently restructure the
  IDENTICAL base line ranges inside `forward_with_failover()` (hunks at base ~194,
  ~340, ~499, ~599), so whichever lands second guarantees a real conflict and
  autolanding would silently drop one side's edit. A third branch,
  feat/ordering-cost-primary (charon-wt/order-a, commit 16dbdc2), also touches
  forwarder.py but at a disjoint hunk (@@ -319,6 +319,12@@) — verified NOT
  overlapping, out of scope for this reconciliation, no action needed on it.
accept: |
  ## Task
  1. Confirm FAIL-LOUD-CONTRACT (branch feat/fail-loud-contract, worktree
     charon-fleet-FAIL-LOUD-CONTRACT, commit c472fee at audit time) has landed to
     master first — this ticket depends_on it. Its structured `providers_tried`
     terminal-error contract (ADR-0016 step #5) must already be in
     `forward_with_failover()` before this reconciliation starts.
  2. Rebase `feat/wire-tool-repair` (worktree
     /home/stack/code/charon/.claude/worktrees/agent-a4294af67f9d41d80, commit
     af8d795) onto the new master tip. Its OWN disjoint edits (gateway.py,
     proxy_server.py, tests/test_forwarder_tool_repair.py — none of which
     FAIL-LOUD-CONTRACT touches) should rebase cleanly; the real work is in
     `forward_with_failover()` itself, where BOTH branches restructured the same
     region. Manually re-apply the tool_repair wiring (the served-response
     tool_repair call) on top of FAIL-LOUD-CONTRACT's now-landed structured
     fail-loud contract — read both diffs in full before touching code (`git show
     c472fee -- src/charon/forwarder.py` and `git show af8d795 -- src/charon/forwarder.py`),
     do not autolally merge/autoresolve the hunks.
  3. Produce ONE merged `forward_with_failover()` that: (a) preserves the
     structured `providers_tried` terminal-error envelope + 4xx-relay distinction
     from FAIL-LOUD-CONTRACT unchanged, and (b) calls into `charon.tool_repair` on
     the served-response path per the wire-tool-repair commit's intent, with
     neither behavior silently dropped or shadowed by the other.
  4. Land as ONE commit/PR superseding the untracked feat/wire-tool-repair branch
     (this ticket's branch `feat/forwarder-reconcile` is the landing vehicle).

  ## Accept (all must pass)
  - `PYTHONPATH=src python3 -m pytest tests/test_forwarder_fail_loud.py
    tests/test_forwarder_tool_repair.py -q` → BOTH suites green against the ONE
    merged forwarder.py (not two divergent copies).
  - Manual/reviewer confirmation: diff the merged `forward_with_failover()` against
    each of the two source commits (c472fee, af8d795) and confirm every hunk from
    BOTH is represented — no silent drop. ADVERSARIAL REVIEW REQUIRED (money-path
    terminal-error + served-response surface, per FAIL-LOUD-CONTRACT's own
    "money-path" work_class and the north-star silent-downgrade-leak lens).
  - `PYTHONPATH=src python3 -m charon.cli gate` → GREEN.
  - The `feat/wire-tool-repair` worktree/branch is retired (its work is now
    represented in `feat/forwarder-reconcile`) — no dangling untracked branch left
    still editing forwarder.py.

  ## Dependencies & sequence
  depends_on: FAIL-LOUD-CONTRACT (owns overlap on forwarder.py — this ticket must
  run AFTER FAIL-LOUD-CONTRACT lands, per fix in TOOL-AUDIT-COLLISION.md RANK 1:
  "land FAIL-LOUD-CONTRACT first ... then rebase wire-tool-repair onto it"). Single
  wave; do not parallelize with any other forwarder.py-owning ticket.
