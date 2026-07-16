repo: charon-private
tier: economy
difficulty: 1
work_class: rig-meta
branch: chore/reds-tsv-hygiene
owns: fleet/reds.tsv, .gitignore
depends_on:
note: fleet/reds.tsv is a TRACKED auto-generated file that is perpetually dirty (regenerated every gate run) — churn + dirty-tree noise blocking clean pushes. Gitignore it (derived state), git-rm --cached the tracked copy.
accept: |
  - fleet/reds.tsv is gitignored; `git status` clean after a gate run that rewrites it.
  - git ls-files shows fleet/reds.tsv untracked; no functionality depends on it being tracked (grep confirms).
