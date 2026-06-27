Make Charon's CI runnable by forking contributors without removing the maintainer's self-hosted
runner. Today every job pins `runs-on: [self-hosted, 4-lom]`, so a stranger who forks Charon gets
ZERO CI (no `4-lom` runner). Fix = the "A-Clean" repo-variable pattern. Canonical tier: **med**
(fleet `sonnet`). Small, mechanical config + docs change — do not touch product code.

THE PATTERN (apply to every job currently pinned to `[self-hosted, 4-lom]`):
```yaml
# Runner is chosen by the CI_RUNNER repo variable (Settings → Variables).
# Maintainer sets CI_RUNNER=["self-hosted","4-lom"]; forks don't inherit it and
# fall back to GitHub-hosted ubuntu-latest, so forked PRs get working CI.
runs-on: ${{ fromJSON(vars.CI_RUNNER || '"ubuntu-latest"') }}
```

FILES + WHAT TO DO (own ONLY these):
1. `.github/workflows/ci.yml` — replace `runs-on: [self-hosted, 4-lom]` on BOTH jobs (`gate` and
   `wheel-smoke`) with the pattern above, including the 3-line comment.
2. `.github/workflows/heavy.yml` — same replacement on every job pinned to `[self-hosted, 4-lom]`.
3. `.github/workflows/release.yml` — same replacement on every job pinned to `[self-hosted, 4-lom]`.
   (Do NOT touch `.github/workflows/windows-exe.yml` — it already uses hosted `windows-latest` and
   works on forks.)
4. `docs/DECISIONS.md` — append ONE register row above the sentinel comment:
   `| D020 | CI runner is chosen by the **`CI_RUNNER` repo variable** (`runs-on: ${{ fromJSON(vars.CI_RUNNER \|\| '"ubuntu-latest"') }}`); maintainer sets `["self-hosted","4-lom"]`, forks fall back to hosted so forked PRs get CI. | OP | Settled | first-run audit 2026-06-27 |`
   (Keep it ONE line. Source is plain text — do NOT cite an ADR-/REVIEW-LOG token, to keep
   check_decisions green.)
5. `CONTRIBUTING.md` (create if absent, else add a short "## CI" section): explain that CI runs on
   GitHub-hosted runners for forks automatically; maintainers set the `CI_RUNNER` repo variable to
   use the self-hosted runner; and note that if `CI_RUNNER` is unset, even the upstream repo falls
   back to hosted (no error).

CONSTRAINTS: own ONLY the 5 files above. No product/src changes. Gate green every commit
(check_decisions must stay green — verify with `python3 tools/check_decisions.py --check` after
editing DECISIONS.md; you may need to run `python3 tools/render_review_log.py` first since
REVIEW-LOG.md is generated/gitignored). Conventional commits. Write your review note as
`docs/review-log/CI1.md`, and IN IT record the OPERATOR ACTION required: "set repo variable
CI_RUNNER=[\"self-hosted\",\"4-lom\"] in Settings → Variables — until set, upstream CI runs on
hosted." Commit ALL work on your branch and STOP — do NOT push / open a PR / run submit.sh; the
launcher publishes after you exit. If a fix needs a file outside the owns list, STOP and run
release.sh with a one-line reason.
