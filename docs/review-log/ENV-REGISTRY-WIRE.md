# ENV-REGISTRY-WIRE — Review Log

## Ticket
ENV-REGISTRY-WIRE: Kill env-fact spelunking by surfacing a COMPACT live env-registry
to primary sessions (SessionStart) and to sub-agents (SESSION-CTX-PROPAGATE preamble).

## What was done
- **fleet/env-registry.sh** (~200 lines): the COMPACT live env-registry emitter.
  - Parses `fleet/tier-models.tsv` (git-tracked, worktree-stable) for the per-tier
    failover chains (frontier/strong/economy) and the deduped served-model set.
  - Best-effort live probe against `http://10.0.1.60:8080/charon/config` (Bearer token
    re-derived from `~/.config/opencode/opencode.json` — `CHARON_GATEWAY_TOKEN` shell env
    is documented STALE per CG-PROVIDERS.md / `preflight.sh:detect_gateway_token_drift`).
  - On probe success, annotates the source line with live model/pool counts (554 models,
    50 pools at last probe); on any probe failure (timeout/401/network) falls through
    to OFFLINE and annotates the probe status — the summary ALWAYS emits, never a silent
    empty pass.
  - Surfaced format (~7 lines, hard cap ~50): gateway URL, host map (gateway + token
    source), served-model count + first 12 (+N more if applicable), all three tier chains,
    source annotation. Designed to ride on every sub-agent via the SESSION-CTX-PROPAGATE
    preamble and on every primary session via SessionStart.
  - `CHARON_ENV_REGISTRY_OUTPUT=<file>` refresh path: when set, atomically writes the
    surfaced summary to that file — this is the "prefer refreshing CG-PROVIDERS.md over
    a new file" lever (operator wires the env var; the script never hardcodes a path).
  - NON-VACUOUS: zero parseable tiers from tier-models.tsv → exit 2 (RED), never a silent
    empty pass. An empty / unreadable tier-models.tsv fails loud by design.

- **fleet/tests/env-registry.test.sh** (16 asserts): the FAIL-ON-REVERT self-test.
  - (a) script exists + executable + non-empty output.
  - (b) surfaced summary lists the live gateway endpoint (10.0.1.60:8080) — the exact
    fact that cost multiple rediscovery probes per SESSION-RECALL-CHALLENGE.md §1e.
  - (c) surfaced summary lists the live served models from tier-models.tsv, anchored
    on `deepseek-v4-pro` (frontier leg, stable across the light-models-eval revision).
  - (d) tier->model chain lines for all three cost-band tiers (frontier/strong/economy).
  - (e) host-map line names the opencode config (Bearer token source).
  - (f) NON-VACUOUS: empty tier-models.tsv fixture → exit 2 (catches any revert that
    would make the script print a happy empty line instead of failing loud).
  - (g) `CHARON_ENV_REGISTRY_OUTPUT=<file>` refresh path: writes the surfaced summary
    to an external file (the CG-PROVIDERS.md refresh lever), with a `gateway:` line
    in the written output (proves the refresh emits the same format, not a degraded one).
  - Runs offline (pointed at a temp opencode config + unreachable gateway URL) so the
    test is deterministic in CI; the live probe path is exercised by the operator run.

## Key decisions
- **stdout surface, file refresh via env var, no new tracked file**: The ticket says
  "prefer refreshing CG-PROVIDERS.md over a new file" — that file is local-only state
  (untracked in `fleet/state/`) and lives in the main checkout, not in every worktree.
  The session-ctx-preamble.sh (SESSION-CTX-PROPAGATE, owner) explicitly avoids
  referencing gitignored local-only state for the same reason (it dangles in fresh
  worktrees). The clean answer: the surfaced registry is env-registry.sh's stdout, and
  the refresh of CG-PROVIDERS.md is `CHARON_ENV_REGISTRY_OUTPUT=$path env-registry.sh`
  — operator-wired, never hardcoded. The script does not need to be owned-by another
  file to do its job; it IS the surface.

- **Best-effort probe, OFFLINE-safe**: The /charon/config probe requires a live Bearer
  token (re-derived from opencode config; the `CHARON_GATEWAY_TOKEN` shell env is STALE
  per CG-PROVIDERS.md). The test runs offline (pointed at a temp config + unreachable
  URL) to stay deterministic in CI. The live path is exercised by the operator run
  before commit; both paths produce a well-formed surfaced summary with the same
  required pointers.

- **Bounded models list, "+N more" tail**: tier-models.tsv is small today (8 unique
  served models) but the per-tier chains can grow with new legs. Capping the served
  list to 12 + "+N more" keeps the surfaced line bounded under the per-sub-agent
  token budget the SESSION-CTX-PROPAGATE preamble enforces (~40 lines for the
  pointer index; the env-registry emits ~7 lines today).

- **NON-VACUOUS is the contract**: per the ticket, "zero served models = RED, never a
  silent empty pass". Test (f) drives the script with an empty tier-models.tsv fixture
  and asserts a non-zero exit. This is the dedicated gate for the silent-empty-pass
  failure mode that the ticket explicitly forbids.

- **Test does NOT depend on the live gateway**: `CHARON_OPENCODE_CONFIG=<tmp>` and
  `CHARON_GATEWAY_URL=http://127.0.0.1:1` make the probe fall through to OFFLINE in
  CI; the test still asserts all the required pointers are present in the surfaced
  summary. The LIVE status annotation is a side effect of the operator run, not a
  CI assertion.

## Out of scope (intentionally not done)
- **No edits to `fleet/hooks/session-start.sh`**: owned by SYNC-SCHEDULE. Wiring
  env-registry.sh as a SessionStart entry is an operator action (a new line in
  ~/.claude/settings.json alongside the existing session-start.sh hook) — documented
  in the env-registry.sh docstring as a wiring follow-up. Same for the SESSION-CTX-
  PROPAGATE preamble (owned by SESSION-CTX-PROPAGATE, merged #68): the preamble's
  existing pointer index can be extended to embed the env-registry output as a
  pointer-line, but the pointer-index file is not in this ticket's owns.

- **No rewrite of CG-PROVIDERS.md**: that file is a 60-line manually-curated human-
  facing reference (provider-by-provider status, per-model funding notes) — much
  richer than the compact env-registry. env-registry.sh is the SESSION-START
  auto-surface; CG-PROVIDERS.md is the human-investigation reference. They serve
  different jobs; this ticket does the former and points at the latter.
