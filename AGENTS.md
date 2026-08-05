# Session protocol — read this first, every session.

1. Run `make status`. Work the single issue labeled `next`. Nothing else.
2. One unit per session. Open a PR and land it green, or push it to a `wip/<name>`
   branch and close the PR — NEVER delete unlanded work (an ephemeral container has no
   reflog to recover it). If it will not land this session: push wip/, close the PR,
   split the issue, label the next `next`, note why.
3. Commit early and often. Context exhaustion arrives without warning; unsaved reasoning
   is lost, WIP commits are not.
4. Done is the issue's acceptance command exiting zero. Not your judgement. And "done"
   for a change to CG itself is the three-state lifecycle: green → landed & clean →
   confirmed by a real run (docs/CG_PLAN_v2.md §4).
5. Anything discovered that is not the next action becomes an issue. File it; do not fix it.
6. Before stopping: label the next issue, confirm no stray branches/worktrees, and that
   `make status` reflects reality.

The full plan is docs/CG_PLAN_v2.md. The capability map (what exists / what to wire / what
to build) is §6 — consult it before deciding anything is missing; most gaps are unwired,
not absent.
