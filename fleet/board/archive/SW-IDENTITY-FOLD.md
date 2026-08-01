repo: charon
tier: strong
difficulty: 3
work_class: bugfix
priority: 0
branch: fix/sw-identity-fold
depends_on:
owns: src/charon/proxy.py, tests/test_model_identity_fold.py
serial_justified: |
  ONE primitive plus its fail-on-revert proof. `_normalize_model_id` (src/charon/proxy.py:269) is
  the SINGLE cross-provider model-identity function in the tree — `routing_policy/catalog_refresh.py:61-68`
  `_normalize()` imports it rather than defining its own. Splitting the regex from the corpus test
  reproduces the defect being fixed (a partial suffix table that nobody can see is partial).
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  The run IS a graded sample: record it into the model scorecard (fleet/model-scorecard.tsv) with the
  work_class above. Wall-clock, retries and any fabricated-success must be logged as scorecard evidence.
  One checkout, one agent — run in its OWN git worktree of the product repo, never in the shared main tree.
source: |
  Switchboard-convergence investigation, 2026-07-26 (manager session). Facts pre-verified against the
  live 4-LOM gateway (image v0.6.0, build 289cf93) and product HEAD — do NOT re-derive.
note: |
  ## THE INSTANCE (release-blocking)
  `src/charon/proxy.py:265-266` — `_QUANT_SUFFIX` enumerates `fp8|fp16|fp32|bf16|int8|int4|q\d+...`
  and **omits `fp4`**. Together advertises `MiniMaxAI/MiniMax-M2.5-FP4`, which therefore normalizes to
  `minimax-m2.5-fp4` and forms an ORPHAN pool instead of folding into `minimax-m2.5`. A funded,
  unparked provider is stranded behind an id-spelling artifact.

  Per ADR-0011 (docs/adr/0011-the-switchboard-demand-routed-no-pools.md, Accepted) that is an **INV-SW2
  violation** — "never falsely exhausted." A capable, funded leg that demand cannot reach is exactly the
  false exhaustion the Switchboard exists to make impossible. Release-blocking.

  ## THE CLASS (this is what the ticket owns — the regex fix ships INSIDE it, never alone)
  Identity folding is table-driven and the table is incomplete by construction. A one-token `fp4` patch
  leaves the class standing. Audit and disposition EVERY variant-spelling family that can split one model
  into two pool ids, with the live catalog as the corpus:
    - quantization: `fp4` (known miss), and any other family the live catalog advertises (nvfp4, mxfp4,
      awq, gptq, w8a8, q8_0 stacked forms).
    - marketing/serving suffixes: `-turbo`, `-fast`, `-instruct`, `-latest`, `-preview`, `-hf`.
    - mode selectors: `:thinking`, `:reasoning`, `:free`, `:nitro`, `:online` (colon-tail, not hyphen).
    - CASE: the compare already lower-cases; prove it, do not assume it.
    - vendor path prefixes: `openai/gpt-4o` (OpenRouter) vs bare `gpt-4o` — the final-path-segment rule
      already covers this; prove it with a test so a future refactor cannot silently drop it.
  For each family: FOLD it, or record in-code WHY it is a genuinely different model (a `:thinking`
  variant may legitimately be distinct — say so explicitly rather than leaving it to the regex's silence).

  ## WHY THIS IS THE ANCHOR
  Pool membership (SW-STATIC-LEGS-RETIRE) and every id-keyed lookup on the selection path
  (SW-P2-CONTEXT-ADMIT, SW-P2-METER-OBSERVED) resolve model identity through this ONE function.
  If it changes after those land, their keys silently miss. **Land this before fan-out.**
accept: |
  DONE-CONTRACT (observable, on the LIVE gateway — not "code written"):
  - `MiniMaxAI/MiniMax-M2.5-FP4` and any bare `minimax-m2.5` leg resolve to the SAME routable pool id;
    the orphan `minimax-m2.5-fp4` pool no longer exists in `/charon/status` pool output, and Together's
    leg is reachable by a request for `minimax-m2.5`. State the before/after pool counts.
  - `tests/test_model_identity_fold.py` carries a CORPUS test: a table of real advertised ids drawn from
    the live catalog, each with its expected folded id, INCLUDING the deliberate non-folds and the reason.
  - FAIL-ON-REVERT, red-proofed by execution: revert the suffix table to its current value -> the corpus
    test goes RED and the fp4 case is named in the failure. Report BOTH exit codes (green run and the
    deliberately-broken run). A green you did not first make fail is not evidence.
  - Non-vacuous: a corpus of zero ids is RED, never a silent pass.
  - `PYTHONPATH=src python3 -m charon.cli gate` GREEN and `PYTHONPATH=src python3 -m pytest -q` GREEN
    from the worktree.
  - ADVERSARIAL REVIEW (reviewer != builder): routing identity is a money/routing path — a wrong fold
    merges two genuinely different models into one pool, which is worse than the orphan it fixes.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately.** This is the ANCHOR of the Switchboard-convergence wave.
- **Blocks (as a real build-prereq, not merge order):** SW-STATIC-LEGS-RETIRE, SW-P2-CONTEXT-ADMIT,
  SW-P2-METER-OBSERVED. All three key on the model identity this function defines; building them against
  a table that is about to change is throwaway work.
- **Wave:** wave 0 (anchor). Land THIS, then fan Phase 1 and Phase 2 out concurrently.
- **Concurrency safety:** `src/charon/proxy.py` is owned by NO other live board ticket (verified against
  the full `owns:` set of `fleet/board/*.md`, 2026-07-26). No collision.
- **Do NOT duplicate:** `DISCOVERY-NORMALIZE` touches discovery-side id shaping — read it before starting;
  if it already folds a family listed above, extend it rather than adding a second table (anti-accretion).
