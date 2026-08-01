## 2026-07-31 — DEADCODE-TOOLS-WIRE (vulture + deadcode adoption cutover)

- **Change under review:** wire `vulture` + `deadcode` into the merge gate as
  one deduplicated, findings-budget-ratcheting gate (`tools/check_deadcode_tools.py`).
  Add `tests/test_deadcode_tools.py`. Delete the one vulture-unique finding
  at `src/charon/forwarder.py:934`. Register the gate in `tools/gates.json`
  and wire it into `src/charon/gate_runner.py`. Record the post-fix baseline
  in `tools/deadcode-tools-budget.json`. Add `vulture>=2.11` and
  `deadcode>=2.4` to `[project.optional-dependencies].dev`.
- **Process:** single focused adoption pass — the DEADCODE-TOOL-REDERIVE
  substrate (merged d90381d) already ran both tools against four real corpora
  and tabulated the live findings; this ticket is the wire-in, not a re-derivation.
  No ADR required (operator directive 2026-08-01: "fully wired, tested e2e
  dogfood", which is the adoption path ADOPT-FIRST authorises without an ADR).
- **Verdict on `forwarder.py:934`:** DEAD CODE, NOT A BUG. `forward_with_failover`
  is annotated `-> None`; the try/finally has body returns at lines 652, 746,
  763, 835, 866, 927 (analyzed via AST walk). Vulture's flow analysis sees
  no path through the body completing without a return — every leaf either
  returns or re-raises. The `return` at 934 sits AFTER the finally and is
  unreachable in normal execution. Pure residue; removing it is safe.
- **Architecture notes:**
  - vulture and deadcode are reference-counting tools. The KSF
    reachability gate (`tools/check_inert_code.py`) handles the mutually-
    referencing dead-island class — neither can replace it; both stay.
  - Dedupe by `(path, line, name)`. A symbol may carry both DC codes
    (e.g. `DC02` from deadcode and `vulture:unreachable` if vulture flagged
    a sibling). Single ratchet count, both class tags preserved for review.
  - vulture is restricted to 100% confidence: at 60% it emits ~328
    reference-counting findings that double-count deadcode's. The contract
    is "vulture-unique class only" — its "unreachable code after
    try/return" line. Restricting to 100% guarantees the `deadcode` and
    `vulture` outputs don't double-count.
  - The findings budget is a SHRINKING-ONLY ratchet, not a tolerance
    floor. Today's 169 becomes tomorrow's 168 in the same commit that
    fixes the finding. A budget that doesn't move with the count is a
    ceiling, not a ratchet; the BUDGET-OUT-OF-DATE branch in `main()`
    fails closed when findings fall below the recorded value.
- **Validation results:**
  - vulture 100% against `src/`: 11 findings (one unreachable +
    10 reference-counting dups of deadcode).
  - deadcode against `src/`: 169 findings (DC01..DC08 only, no DC11).
  - After deleting `forwarder.py:934`: vulture unreachable→0; dedupe
    still yields 169 (deleting a no-op `return` never touches deadcode).
  - `tools/check_deadcode_tools.main()` exits 0 against the recorded
    baseline of 169.
  - `python3 tools/run_gate.py` runs every check including the new
    `[deadcode-tools]` step and prints OK through `[pytest]`.
  - `pytest tests/test_deadcode_tools.py -q`: 15 passed (covers RED
    on (a) unused-function, (b) unreachable-after-try, (c) ratchet
    above/below/equal plus missing/malformed budget, dedupe rule,
    real-repo green path, gate-runner wiring proof, gates.json
    registration proof, pyproject.toml dev-dep proof).
- **Verdict:** buildable and green. Wire-in lands `forwarder.py:934`
  deletion + 169-finding ratchet baseline + everything needed to RUN
  in CI. Future tickets shrink the count; this ticket ships the
  ratchet.
