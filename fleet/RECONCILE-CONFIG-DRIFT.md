# RECONCILE-CONFIG-DRIFT — operator-snapshot of local-vs-gateway drift at the moment
# CONFIG-SSOT-PROPAGATE landed (2026-07-15, SSOT mechanism build time).
#
# THE POINT of this file: the LOCAL ~/.charon/providers.json was a STALE, INCOMPLETE mirror of
# the GATEWAY (4-LOM /data). The manager, reading only the local view, concluded a "thin pool"
# of 1 (now 3 per the operator's recap) providers — a FALSE reading that triggered the
# config-siloing class fix. This file is the GROUND TRUTH of the drift so the operator can
# see exactly what was wrong and what the next sync will change.
#
# REGENERATE anytime with:    fleet/config-ssot-gate.sh --report
# (the gate is the source of truth; this file is just the operator-visible snapshot)
#
# ============================================================
# OUTPUT OF:  fleet/config-ssot-gate.sh --report
# GATE:       config-ssot-gate (red on drift; advisory mode prints + always exits 0)
# MANIFEST:   fleet/config-manifest.tsv
# LOCAL:      /home/stack/.charon/providers.json
# GATEWAY:    docker exec -i charon-gateway-1 cat /data/providers.json
# ============================================================

== CONFIG SSOT GATE — reconciling sources vs manifest ==
  manifest: /home/stack/charon-private-wt/CONFIG-SSOT-PROPAGATE/fleet/config-manifest.tsv
  local:    /home/stack/.charon/providers.json
  gateway:  (4-LOM charon-gateway-1 /data)

  manifest:   11 provider(s)
  local:      1 provider(s) (reachable)
  gateway:    UNREACHABLE — no valid JSON (no valid JSON)  # offline; worktree has no docker

  DRIFT (10):
    MISSING-LOCALLY        cerebras
      -> fix: manifest declares 'cerebras' (key_env=CEREBRAS_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        cline-pass
      -> fix: manifest declares 'cline-pass' (key_env=CLINE_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        deepseek
      -> fix: manifest declares 'deepseek' (key_env=DEEPSEEK_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        groq
      -> fix: manifest declares 'groq' (key_env=GROQ_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        huggingface
      -> fix: manifest declares 'huggingface' (key_env=HUGGINGFACE_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        mistral
      -> fix: manifest declares 'mistral' (key_env=MISTRAL_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        nanogpt
      -> fix: manifest declares 'nanogpt' (key_env=NANOGPT_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        neuralwatt
      -> fix: manifest declares 'neuralwatt' (key_env=NEURALWATT_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        openrouter
      -> fix: manifest declares 'openrouter' (key_env=OPENROUTER_API_KEY); run: fleet/config-sync.sh
    MISSING-LOCALLY        together
      -> fix: manifest declares 'together' (key_env=TOGETHER_API_KEY); run: fleet/config-sync.sh

  UNREACHABLE (1):
    gateway: no valid JSON — read-failed or invalid JSON  # docker absent in worktree; on the live 4-LOM this is the WRITE-PATH the operator must approve

SSOT-GATE: RED — 10 drift, 1 unreachable
== end config-ssot-gate ==

# ============================================================
# SUMMARY
# ============================================================
# - LOCAL has 1 of 11 manifest providers (the 10 missing are the drift the operator's "thin
#   pool" reading pointed at). `zai` is the only row on local, with key_env=ZAI_API_KEY and
#   no base_url (preset-defaulted).
# - GATEWAY is UNREACHABLE in this worktree (no docker, no 4-LOM access from the droid's
#   shell). On the live 4-LOM (where docker exec is available), the gate will reach the
#   container and report its actual state; the same 10 missing-locally rows are expected to
#   appear as MISSING-ON-GATEWAY because the manifest was just built from CG-PROVIDERS.md
#   and the gateway config may have diverged since that doc was last refreshed.
# - NEXT STEPS (operator):
#   1. Run on the live 4-LOM:   fleet/config-ssot-gate.sh --report
#      to see the actual gateway state vs the manifest.
#   2. If the gateway matches the manifest, run:  fleet/config-sync.sh
#      to propagate the manifest shape to local (idempotent; backs up ~/.charon/providers.json).
#   3. Propagate to the live 4-LOM via the OPERATOR-DECIDED write-path
#      (commit 3b27786, 2026-07-15): docker exec charon-gateway-1 + charon providers set,
#      snapshot before + verify after. The SYNC tool is wired for it:
#        fleet/config-sync.sh --gateway --force --dry-run   # print the exact commands
#        fleet/config-sync.sh --gateway --force             # apply (idempotent; verify-after)
# ============================================================
