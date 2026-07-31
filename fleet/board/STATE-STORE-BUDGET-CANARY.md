repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 1
branch: feat/state-store-budget-canary
depends_on:
owns: fleet/checks/state-store-budget.sh, fleet/tests/state-store-budget.test.sh, fleet/state/STORE-BUDGETS.tsv
serial_justified: |
  ONE budget contract: the declared budget table, the check that enforces it, and the suite that
  proves it fires are a single guarantee. A budget file nothing reads, or a check with no declared
  budgets, is inert by construction.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
source: |
  Operator question 2026-07-31 on the 6.5 GB opencode.db: "why was it allowed to get this big, are
  others like this, how can we mechanize a class fix?" Rec accepted as P1.
note: |
  ## THE MEASURED FACTS (2026-07-31, verified — do not re-derive, do confirm)
  `~/.local/share/opencode/opencode.db` = 6.5 GB (+18 MB WAL). Contents: `event` table 775,810 rows,
  `message` 41,764 rows. It is an append-only event log with NO retention policy and no owner.

  Blast radius, measured:
  - DISK: LOW. 906 G free, 6% used. Disk is NOT the pressure.
  - OUTLIER: yes, ~10x. `~/.claude/projects` 632 MB, `~/.charon/session-bridge.db` 24 KB.
  - REAL COST: this is the store every worker reads. It is GLOBAL across ports and PAGINATED at 50,
    which is precisely why `spawn-worker.sh`'s old count-delta start-check could never work
    (fixed in PR #272). Size already degraded a verification path.

  ## WHY IT GOT THIS BIG
  Nothing ever measured it, so nothing ever flagged it. There was no owner and no budget.

  ## WHAT TO BUILD — CLASS FIX, NOT A CLEANUP
  Declare known state stores with size budgets in a TSV; a check compares actual to budget and goes
  RED on breach, wired into the existing preflight (same shape as reconcile-stale-claims, PR #273).
  The value is catching the NEXT unbounded store, not this one.

  Deleting or truncating opencode.db is OUT OF SCOPE and REPORT-ONLY — it is opencode's own store
  and holds live session history. Propose a retention approach; do not execute one.

D&S — Deps & Sequence:
  - Depends on: nothing.
  - Blocks: nothing. P1 because disk is not the pressure — the missing-guard precedent is.
  - Sequence: independent of all current in-flight work.
