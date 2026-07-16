repo: charon-private
tier: strong
difficulty: 4
work_class: rig-meta
branch: feat/config-ssot-propagate
owns: fleet/config-manifest.tsv, fleet/config-sync.sh, fleet/checks/config-ssot-gate.sh, fleet/tests/config-ssot.test.sh
depends_on:
serial_justified: One cohesive SSOT mechanism (manifest + sync + gate + test) around a single config source-of-truth; splitting fragments the contract.
note: |
  CLASS FIX for config-siloing (operator directive): the LOCAL ~/.charon config is an incomplete mirror
  of the GATEWAY (4-LOM /data) — 11 providers keyed on the gateway, only 3 locally — which MISLED the
  manager into a false "thin pool" reading. Today only config-drift.sh (Phase-1 DETECT) exists, and it's
  degraded (needs CONFIG-SOURCES.tsv, see RIG-STATE-HYGIENE). Build the full class fix: a git-tracked
  MANIFEST = SSOT, a SYNC that propagates git->all sources, a GATE that REDs on drift, and a one-time
  RECONCILE of existing drift. Per [[config-ssot-git-manifest]].
  WRITE-PATH DECIDED (operator 2026-07-15): propagate to the live 4-LOM deploy via `docker exec` a
  config write INTO container charon-gateway-1's /data (CHARON_HOME=/data). Reach 4-LOM with
  `ssh -i ~/.ssh/4lom stack@10.0.1.60` then `docker exec charon-gateway-1 sh -lc 'CHARON_HOME=/data charon providers add/set ...'`
  (see [[4lom-host-access]]). Idempotent, backup-before-write, verify-after. NO redeploy needed.
accept: |
  - fleet/config-manifest.tsv (git SSOT: provider|key_env|base_url|tiers) committed to the PRIVATE rig (do not publish the operator's active-provider set to a public repo).
  - config-ssot-gate.sh: REDs when any source (local ~/.charon, gateway /data) diverges from the manifest; names the drift + the fix command. Wired into validate_board advisory first.
  - config-sync.sh: propagates manifest -> BOTH local ~/.charon AND the 4-LOM gateway via
    `docker exec charon-gateway-1` writing /data (idempotent; snapshot /data config before write; verify providers list after). A --dry-run prints the exact docker-exec commands without applying.
  - A reconcile REPORT of current local-vs-gateway drift (the 8 providers keyed on gateway but absent locally).
  - fleet/tests/config-ssot.test.sh: seeded-drift -> gate RED; in-sync -> GREEN (fail-on-revert).
