## WORKCLASS-TAXONOMY — review/decision fragment

**Scope:** GATEWAY-PROGRAM §1.9 (open, append-only work-class taxonomy +
switchable exploration mode). One hot-path classifier + one CI import-guard.
Disjoint from the matrix/scorecard/actuals work; this ticket owns the
classifier + the rig-import guard, nothing else.

### Decisions

- **Hot-path classifier is regex-only, no LLM, no third-party deps.** Per
  the GATEWAY-PROGRAM §1.9 constraint that classification is "cheap, no
  per-request LLM", we hand-craft a seed table of ~6 canonical classes
  (`reasoning`, `coding`, `translation`, `creative`, `analysis`,
  `general`) with conservative regex patterns. Each request runs at most
  ~6 cheap pattern matches. Tail-latency budget is preserved.

- **Open append-only registry + offline crystallizer.** The hot path can
  only read (`classify_request`, `observe_unknown`). Mutations
  (`add`, `update_patterns`, `attest`, `crystallize`) are operator tools
  that run offline, never per request. This is intentional: we want the
  online gateway to be a pure function of the registry, while crystallizer
  iterations happen on a separate cadence.

- **`unknown` is a first-class sink, not a failure.** Every unknown
  request is logged with a SHA-256 signature (so the crystallizer can
  cluster without seeing the raw prompt) and a short sample (capped 240
  chars). The sink is bounded by LRU eviction (default 4096 entries) so
  a runaway stream of novel prompts cannot OOM the gateway.

- **NEW/unknown classes default to `risk="high"` (red-team fix #4).**
  `WorkClassTaxonomy.add(..., risk=...)` defaults to `"high"` for every
  class added via the API. The only way a class becomes `risk="low"` is
  an explicit `attest(name, risk="low")` operator call. Seed classes
  ship as `"low"` because the seed table is hand-curated and operator-
  approved. This breaks the novel-class × risk-gate deadlock the red team
  identified — the bandit CAN sample crystallized classes, just only via
  reds-replay / spec-floor until the operator says otherwise.

- **Crystallizer is `suggest_only` by default.** `crystallize()` returns
  proposal dicts (signature prefix, sample, suggested patterns) without
  mutating the registry. Operators inspect, edit, then `add()` by hand.
  Passing `suggest_only=False` inserts the top clusters but always as
  `risk="high"` — no auto-attestation.

- **The rig-import guard is AST-based, not regex.** `tools/check_no_rig_import.py`
  parses each `src/charon/*.py` with `ast`, walks `Import`, `ImportFrom`,
  and literal `__import__("...")` calls, and flags any package whose head
  is `benchmark` or `grader_daemon`. Comments + string literals are
  ignored (false-positive guard). Engine/ + `ports/worker.py` are
  excluded — those are the privileged-loop paths with their own stdlib-
  only invariant (`check_boundary.py`) and the rig guard's job is the
  product hot path, not the engine.

- **Excluded from scan (intentional, documented):** `charon/engine/*.py`
  and `charon/ports/worker.py`. The rig guard's job is the *product*
  hot path. The engine is privileged-loop stdlib-only by a separate
  rule (ADR-0010 D2 / ADR-0005 R3). Including engine/ here would
  double-report and obscure the real product concern.

### Test coverage (53 tests)

- Hot-path classification: each of the 6 seed classes has a smoke test
  that the canonical prompt routes to it.
- `unknown` path: empty input + off-pattern inputs.
- Sink mechanics: count bumping, LRU eviction when full, sample capping.
- Append-only + risk flow: re-add raises, default risk is high, attest
  moves classes, update_patterns preserves risk.
- Crystallizer: suggest-only is non-mutating, high-risk on auto-insert,
  proposal shape.
- Persistence: to_dict/from_dict round-trip preserves seed + added +
  unknown sink.
- Copy: independence between original and copy.
- **Fail-on-revert (red-team fix #2):** a synthetic `src/charon/leaky.py`
  containing `import benchmark` is caught by `scan_file`, `scan_hot_path`,
  AND the CLI subprocess (end-to-end, mirrors CI). The full repo tree
  (`scan_hot_path(Path("src"))`) is asserted clean.

### Open follow-ups (NOT in this ticket)

- Crystallizer pattern-derivation is intentionally naive (`_derive_patterns`
  picks 1-3 long tokens). A real LLM-backed pattern proposer is a separate
  ticket; this stub is good enough to surface clusters for operator review.
- Persistence layout: `to_dict()` is JSON-safe; persisting to disk + boot-
  time load is a small follow-up (no consumer in the gateway yet — the
  scoring engine is a separate Wave-2 ticket).
- Wiring the classifier into the proxy-server hot path: out of scope here
  (would touch `proxy_server.py`, which is not in `owns:`). The classifier
  is currently a library; an integration ticket can call
  `taxonomy.observe_unknown(text, now=time.time())` per request.