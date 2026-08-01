repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
priority: 0
branch: fix/model-hardcode-purge
depends_on: REVIEWER-TAB-POOL, CAPTURE-WIRING-TIMEOUT-FIX, LEDGER-NO-EVIDENCE-NO-VERDICT
real-dep: REVIEWER-TAB-POOL owns fleet/review-pool.sh and is in flight closing B3; CAPTURE-WIRING-TIMEOUT-FIX owns fleet/charon-run.sh — both must settle before the purge edits those files
owns: fleet/checks/no-hardcoded-model.sh, fleet/tests/no-hardcoded-model.test.sh, fleet/review-pool.sh, fleet/session-ctl.sh, fleet/charon-run.sh
substrate: N/A
substrate-novel: |
  The rule is "no live-path script may name a specific MODEL or PROVIDER — resolve from the SSOT
  `fleet/tier-models.tsv`". That is a meta-invariant over OUR OWN config layout; no external
  linter models our tier file. Generic pattern scanners (semgrep, ruff, shellcheck — all already
  adopted) enforce syntax/security patterns, not "this identifier must come from that data file".
  The concrete instance of Keystone's DESIGNED-but-unbuilt KS19 `hardcoded-single-entity` lens.
serial_justified: |
  The purge and the gate are one deliverable: purging without the gate regresses on the next
  edit, and a gate over a dirty tree is red on arrival.
source: |
  Operator directive 2026-08-01: nothing hardcoded to a specific provider OR model. Re-affirms the
  standing rule [[charon-modular-agent-and-provider-agnostic]]. Measured population below.
note: |
  ## THE MEASURED POPULATION (live paths only — 2026-08-01)
  ```
  fleet/review-pool.sh:23,36     deepseek-v3          <- DEFAULT chain, and it returns HTTP 402
  fleet/deploy.sh:316,331,335,336 deepseek-v4-pro     (x4)
  fleet/spawn-worker.sh:13,171,173 gpt-5.4, deepseek-v4-pro, deepseek-v4-flash, minimax-m3-together
  fleet/charon-run.sh:93          kimi-k2.6
  fleet/capability/assign.py:42   glm-5.2
  fleet/session-ctl.sh:122        deepseek-v4-flash
  ```
  Provider names are also hardcoded in `fleet/spawn-worker.sh` (3), `fleet/deploy.sh` (1),
  `fleet/_lib.sh` (1). `fleet/add-provider-interactive.sh` (17) is likely a legitimate menu —
  JUDGE it, do not blanket-purge; an interactive picker listing known providers is not the defect.

  ## WHY IT MATTERS — this is not hygiene, it broke things TODAY
  - `review-pool.sh`'s hardcoded default `deepseek-v3` is **UNFUNDED (HTTP 402)**. The reviewer
    pool could not run, which is part of why PRs piled up.
  - `spawn-worker.sh:13` hardcodes `gpt-5.4` in its refusal list — a model-specific rule that goes
    stale the moment the catalog moves.
  - A hardcoded model is a silent single point of failure: when its provider caps or its id is
    retired, the script dies with an error that names the wrong cause.

  ## THE SSOT ALREADY EXISTS — RESOLVE, DON'T NAME
  `fleet/tier-models.tsv` is the machine-consumed per-tier chain and `fleet/state/TIER-CANON.md`
  defines the tiers. Every live path must ask for a TIER (frontier|strong|economy) and resolve the
  chain, exactly as `fleet-droid.sh` already does. **Reuse fleet-droid.sh's existing resolution
  helper — do not write a second parser.** If no helper is factored out, factor ONE and use it
  everywhere; do not copy the parse into each script.

  ## SCOPE
  1. Purge the live-path hardcodes above; each becomes a tier resolution or an explicit env
     override with a tier-derived default.
  2. `fleet/checks/no-hardcoded-model.sh` — gate: a live-path script naming a model id or provider
     that is not sourced from the SSOT is RED. Wire it into `fleet/checks/rig-ci-scope.sh`.
  3. **Allowlist with reasons, not blanket exclusions.** Legitimately-naming files (the SSOT
     itself, `add-provider-interactive.sh`'s menu, fixtures, benchmark selftests, docs) get an
     explicit reason-bearing entry. An unexplained exclusion is how this class comes back.
  4. Do NOT touch `fleet/benchmark/**` or `fleet/capability/selftest.py` (53 hits) in this ticket
     beyond allowlisting — test fixtures naming models is legitimate. Surface, do not purge.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline. Each RED on the named revert, then GREEN:
    a. a fixture live-path script naming a model id -> RED naming file:line. Revert the gate -> RED.
    b. the same script resolving from the SSOT -> GREEN.
    c. an allowlisted file naming a model -> GREEN, and the allowlist entry MUST carry a reason
       (an entry without one is itself RED).
    d. **`review-pool.sh` runs with NO hardcoded default and picks a funded model** — prove it by
       running `review-pool.sh status` and showing the resolved chain comes from tier-models.tsv.
    e. ANTI-OVER-BLOCK: a script mentioning a model only inside a comment or a doc string is not
       flagged (or is, deliberately — state which and why).
  Report the before/after count of live-path hardcodes.

D&S — Deps & Sequence:
  - `fleet/review-pool.sh` is also owned by REVIEWER-TAB-POOL (in flight). Sequence AFTER it lands
    to avoid a collision — or coordinate: if REVIEWER-TAB-POOL fixes its own default as part of
    B3, drop that file from this ticket's owns and say so.
  - Concrete instance of KS19 `hardcoded-single-entity` (designed, unbuilt). Feeds it.
