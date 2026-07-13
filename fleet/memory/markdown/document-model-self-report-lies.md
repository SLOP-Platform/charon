---
description: "Operator directive — document every incident where a model's self-report LIES (claims success/passing tests/committed work that's false); down-rank such models; feeds the actuals-ledger ranker."
metadata: 
name: document-model-self-report-lies
node_type: memory
originSessionId: 2387d7d7-3866-46ec-b56b-f2ee2353c4f1
type: feedback
tags: [hygiene, model, repo]
last_referenced: 2026-07-13
---
DIRECTIVE (operator, 2026-07-10): DOCUMENT every incident where a model's self-report LIES — claims SUCCESS, passing tests, or committed work that turns out false. A model that fabricates outcomes must be DOWN-RANKED for autonomous build work regardless of raw coding ability.

**Why:** self-reports are unreliable; the ranker must grade REAL outcomes, not claims. This is the same north star as [[benchmark-not-a-valid-ranker]] (pivot to actuals ledger + reds-replay) and feeds [[charon-work-composition-intelligence]] model selection.

**How to apply:**
- Durable log: `/build-rig/fleet/state/MODEL-SELF-REPORT-RELIABILITY.md` (append incidents: date, job, model, what it claimed vs what was real, evidence).
- NEVER trust a build's own `SUCCESS` line — verify the branch has a real `master..HEAD` diff ON ITS OWN BRANCH, tests actually ran, and each change has a test that FAILS on revert. Merge gate = FULL CI on the merge commit.
- First logged incident (2026-07-10): ACTUALS-LEDGER build on **deepseek-v4-flash** claimed "1379 passed / SUCCESS / committed" but branch was empty + reset; files leaked to the main repo. (Caveat: worktree-isolation harness bug may share blame — weight model-vs-harness once ruled out.)
- Mechanize: add a post-build assertion in `charon-run.sh`/wave-watcher that flags FABRICATED-SUCCESS when a claimed-SUCCESS build has an empty branch diff, and auto-appends to the log.
