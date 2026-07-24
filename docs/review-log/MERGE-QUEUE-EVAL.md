# MERGE-QUEUE-EVAL review notes

## Verdict
- **Public repo (SLOP-Platform/charon):** ADOPT GitHub-native merge queue. Confirmed OFF via `gh api` — prior WLS-5 verdict was correct but never applied. Configuration-only: enable merge queue in branch protection + add `merge_group` trigger to CI workflow.
- **Private repo (Nnyan/charon-private):** DEFER. GitHub-native is plan-gated (paid plan required). Mergify/Aviator/bors all add cost/complexity without benefit over the Gitea-native path. Gitea's own merge queue (✓ in comparison docs) is the correct answer after Gitea migration.

## Verified state (gh api)
- `SLOP-Platform/charon`: public, org, free plan, branch protection has only `gate` required, `strict: false`, merge queue 404 (never enabled)
- `Nnyan/charon-private`: private, user, free plan — merge queue unavailable

## land.sh analysis
- No rebase/merge-queue discipline. Local gate only. Serial workflow minimizes concurrent-land risk but does not eliminate staleness-at-merge gap.
- Honest: nothing prevents staleness today; the gap is real but low-blast-radius for solo-op serial work.

## Registry row
Drafted in fleet/state/MERGE-QUEUE-EVAL.md §5 — manager applies to EVAL-REGISTRY.md (avoids owns-collision).
