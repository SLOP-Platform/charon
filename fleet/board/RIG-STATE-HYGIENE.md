repo: charon-private
tier: economy
difficulty: 2
work_class: rig-meta
branch: chore/rig-state-hygiene
owns: .gitignore, fleet/state/CONFIG-SOURCES.tsv
depends_on:
note: |
  Three small rig-hygiene fixes flagged this session, consolidated (all touch .gitignore -> one writer):
  (1) fleet/reds.tsv is a TRACKED auto-gen file, perpetually dirty -> gitignore + git-rm --cached.
  (2) stray committed __pycache__/*.pyc (blocked PR #62) -> gitignore __pycache__/ + *.pyc, git-rm --cached tracked ones.
  (3) config-drift.sh is DEGRADED (missing fleet/state/CONFIG-SOURCES.tsv) -> create the registry (local ~/.charon vs
      4-LOM gateway /data config sources) + !-negate it in .gitignore (like RULE-REGISTRY.tsv). This is what let a stale
      local-silo view mislead the manager (providers looked MISSING locally but SET on the gateway).
accept: |
  - `git status` clean after a gate run rewrites reds.tsv; `git ls-files | grep -E '\.pyc$|__pycache__|fleet/reds.tsv'` empty.
  - fleet/state/CONFIG-SOURCES.tsv exists (rows for local + gateway sources), !-negated; `bash fleet/config-drift.sh` runs
    without "registry not found" and reports local-vs-gateway provider drift.
