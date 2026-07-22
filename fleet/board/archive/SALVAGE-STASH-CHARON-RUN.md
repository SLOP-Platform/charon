repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: feat/salvage-charon-run-timeout
owns: fleet/charon-run.sh
depends_on:
note: |
  A stashed fork of charon-run.sh (backup: fleet/session-notes/STASH-BACKUP-96d38b0.patch) contains 2
  GOOD unique features master LACKS, but the fork is OLDER and would REVERT master's landed
  is_infra_fault/FLAW-2/latency-gate work if applied wholesale. SALVAGE the 2 features ONTO current
  master by hand (do NOT git-apply the stash): (1) RUN_TIMEOUT_S="${CHARON_RUN_TIMEOUT_S:-1800}" —
  configurable per-attempt wall-clock budget (MODEL-PREFLIGHT sets a tighter one); (2) OPENCODE_LOG —
  read-only signal from opencode's log to distinguish "model genuinely slow" vs "gateway pool exhausted,
  opencode silently retried" on a timeout (rc=124). Preserve ALL of master's existing latency/infra-fault logic.
accept: |
  - Both features present on charon-run.sh on top of current master; master's is_infra_fault/latency-gate INTACT (diff shows additive only).
  - A test asserts CHARON_RUN_TIMEOUT_S overrides the default budget; the OPENCODE_LOG exhaustion-vs-slow branch is exercised.
  - bash -n fleet/charon-run.sh. (preflight.sh salvage is a SEPARATE assessment — note it, don't touch here.)
