tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/reviewer-dogfood-reds
repo: charon-private
priority: MEDIUM
depends_on:
owns: fleet/benchmark/reviewer-dogfood.sh, fleet/state/REDS-CORPUS.md
note: |
  SEQUENCING (human gate, deliberately NOT a depends_on). Do NOT implement this until
  worker-tier ranking (Path C) is proven — the reviewer is the LAST tier to hand off and
  the highest-stakes, so it must not be built ahead of the worker tiers it backstops.
  This intent cannot live in 'depends_on:' because the only candidate targets (DOGFOOD,
  COST-RANK-AUTO) are PARKED: claim.sh's deps_done checks fleet/state/done/, which a parked
  ticket never reaches, so a dep on either would deadlock this ticket live-but-unclaimable
  forever. Read this before claiming; confirm Path C is proven, then proceed.
accept: |
  Build the REVIEWER-DOGFOOD eval — how we decide (and eventually get) the REVIEWER job
  (currently done by Claude Code, our single biggest Claude-cost lever) off Claude, SAFELY.
  The reviewer is the LAST tier to hand off and the highest-stakes: a bad reviewer silently
  passes broken money-path code. Its quality CANNOT be graded by charon.cli gate (that grades
  WORKER output). You grade a reviewer by whether it CATCHES known real bugs — reds-replay.
  This is the same real-work-is-the-trust-test discipline, NOT a synthetic battery. [[real-work-is-the-trust-test]]

  PART 1 — CORPUS (reds-replay of REAL caught-bugs). Assemble fleet/state/REDS-CORPUS.md: each case
  = a diff/commit that introduced a REAL defect we caught + the ground-truth finding (file:line +
  defect class) held OUT of the candidate's reach (OOB, like the preflight keys). Seed cases from
  THIS session's real catches: auto-park _save_parked() concurrency race (PR #124 pre-fix b8e62d0
  vs the racy version), classify() list-body blindness (#116 / 4b5df92), preflight fd-sharing
  stdin-drain (#39), SHA-pin unpinning regression (#119). Grow the corpus every time the reviewer
  catches a new real bug.

  PART 2 — HARNESS (fleet/benchmark/reviewer-dogfood.sh). For each candidate reviewer model: feed
  it the buggy diff via the gateway (charon/<model>) with the standard adversarial-review prompt;
  grade OUT-OF-BAND (bench-grader, corpus ground-truth 0700) whether it CAUGHT the seeded bug
  (recall) + its false-positive rate on clean/known-good diffs (precision) + latency. Reuse the
  dogfood-eval.sh monitoring + attribution + latency-budget machinery; never merge on a model's say-so.

  PART 3 — VERDICT + PROMOTION. A model earns the reviewer tier ONLY on reliable catches (recall
  threshold) with acceptable precision. Favor a multi-model voting PANEL over a single reviewer;
  keep Claude as the escalation for high-blast-radius / money-path review. Auto-assign passers into
  the reviewer tier pool + log to the real-outcomes ledger.

scope: |
  Sequenced LAST among the tiers (worker tiers first via Path C), because the reviewer is the
  safety backstop. This is the mechanism that lets the reviewer job move off Claude without
  regressing quality. [[real-work-is-the-trust-test]] [[benchmark-not-a-valid-ranker]]
  [[route-work-to-charon-not-claude]] [[charon-headless-review-loop]]
  [[adversarial-review-default-for-droid-prs]] [[document-model-self-report-lies]]
