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
  OPERATOR DECISION NEEDED (write-path to the live 4-LOM deploy): docker exec a config write into
  container charon-gateway-1's /data, vs write-volume-then-redeploy. Build the SAFE parts first
  (manifest + detect-gate + reconcile-REPORT); gate the live-WRITE propagation on that decision.
accept: |
  - fleet/config-manifest.tsv (git SSOT: provider|key_env|base_url|tiers) committed to the PRIVATE rig (do not publish the operator's active-provider set to a public repo).
  - config-ssot-gate.sh: REDs when any source (local ~/.charon, gateway /data) diverges from the manifest; names the drift + the fix command. Wired into validate_board advisory first.
  - config-sync.sh: propagates manifest->local ~/.charon (idempotent); the 4-LOM write-path is STUBBED behind the operator decision with both options documented.
  - A reconcile REPORT of current local-vs-gateway drift (the 8 providers keyed on gateway but absent locally).
  - fleet/tests/config-ssot.test.sh: seeded-drift -> gate RED; in-sync -> GREEN (fail-on-revert).
