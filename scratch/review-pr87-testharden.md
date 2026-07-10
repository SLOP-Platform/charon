# Review — PR #87 `feat/test-harden-contract` (TEST-HARDEN-CONTRACT)

Independent review of the **branch diff** vs `origin/master` (+374, test-only: 3 files).
CI green (gate + wheel-smoke). Ran the two new files in a throwaway worktree:
`46 passed, 1 xfailed` (the xfail is cline). This review finds what CI can't.

## Verdict: **FIX**

The machinery is largely sound and valuable, but the PR **re-introduces the exact
self-mirroring anti-pattern it exists to kill — for the `anthropic` preset** — and
the new lint that is supposed to catch that pattern **does not gate anything**. Both
are cheap to fix and go to the PR's core thesis.

---

## Findings

### 1. MAJOR — `anthropic` case is a self-mirroring false-green (undermines the thesis)
- `anthropic` is `wire=WIRE_ANTHROPIC` — native `/v1/messages`, **NOT OpenAI-compatible**
  (`src/charon/providers.py:56-63`). Its real upstream response is
  `{"type":"message","content":[...],"usage":{...}}` with **no top-level `choices`**.
- The proxy does **not** translate Anthropic responses to OpenAI shape. `wire` only
  drives request-side prompt-cache enrichment (SR-6 Phase-1); the preset note itself
  says "full OpenAI<->Anthropic translation is Phase-2." Response is relayed verbatim
  (`proxy_response.py` has no anthropic/choices conversion; `proxy_server.py` uses
  `wire` only for `anthropic_prompt_cache` on the outbound body).
- Yet the contract test lists `anthropic` in `_OPENAI_SHAPE_PRESETS` and feeds it the
  fabricated `_canonical_shape` (OpenAI top-level `choices`). So the anthropic case
  passes green **only because the mock lies about anthropic's true wire shape** — the
  precise self-mirroring blind spot this PR claims to eliminate. A real Anthropic
  upstream is the *same class of bug as cline*, but it is not flagged.
- The `_canonical_shape` docstring ("every currently-wired preset is a real
  OpenAI-compatible chat-completions API… mocking this shape is representative") is
  **factually false for anthropic**.
- Fix: give `anthropic` a native-shape fixture (content blocks, no `choices`) and mark
  it `xfail` like cline (response translation is Phase-2/unimplemented), or explicitly
  document/ticket why it's exempt. As written the headline invariant ("EVERY preset
  yields client-observable top-level choices+usage") is proven for Anthropic by a
  self-mirroring mock.

### 2. MODERATE — the self-mirroring lint rule (rule e) gates nothing
- `check_test_patterns.py` classifies self-mirroring as a **WARNING**, not an error.
- The enforcer is **never invoked in CI**: `python3 -m charon.cli gate` produces no
  test-pattern output, and `ci.yml` has no `check_test_patterns` step. `gates.json`
  marks it `ci_step:true` but nothing consumes that flag to run it.
- Its only CI exposure is via `tests/test_check_test_patterns.py`, and the clean-codebase
  red-proof (`TestCleanCodebase`) asserts **`errors == []` only** — warnings are never
  asserted. Gate is not run `--strict`.
- Net: the self-mirroring nudge fires **nowhere that fails CI**. If the intent was to
  prevent future self-mirroring mocks, it currently cannot block one — advisory only.
  (The rule *logic* is correct: the unit tests prove it fires/does-not-fire as designed.)
- Fix: run the enforcer in the gate (at least in `--strict` or promote rule e to error),
  or state clearly in the PR that the rule is advisory.

### 3. GOOD — coverage is genuinely every-preset + loud-fail guard
- `_PARAMS` is built from `sorted(providers.PRESETS.keys())` (all 25), not a hand-picked
  subset. A new preset with no fixture fails **loudly**: `_shape_fixture_for` raises
  `AssertionError` in the test body, and `test_every_preset_has_a_declared_shape_fixture`
  fails. No silent skip/miss for new OpenAI presets.
- Caveat tied to Finding 1: a **new non-OpenAI-wire** preset dropped into
  `_OPENAI_SHAPE_PRESETS` would repeat the anthropic false-green.

### 4. GOOD (minor caveat) — xfail is correctly scoped to cline only
- `xfail(strict=False)` is attached to the single `cline-pass` param, not blanket.
  Mechanism verified: `route_kwargs["adapter"]="cline"` raises `TypeError` (no `adapter`
  field on `UpstreamRoute` today) → xfail. Not suppressing any real failure elsewhere.
- Minor: `strict=False` means once the adapter lands the case **xpasses silently** — the
  "flip" is not enforced (a lingering stale xfail marker won't break CI). Acceptable to
  leave to the RESPONSE-ADAPTER-UNIVERSAL ticket, but worth tightening to strict then.

### 5. GOOD — assertion is shape-sensitive (real fail-on-revert)
- The assertion targets the **client-observable** top-level `choices`/`usage`, exercising
  the real forwarder path (`GatewayProxyServer` + `UpstreamRoute` + `serve_in_thread`).
- The cline xfail demonstrates the assertion is genuinely shape-sensitive: a wrapped
  `{data,success}` envelope yields no top-level `choices` and the assertion fails
  (→ xfail). Not self-fulfilling — a proxy that mangled the envelope would be caught.
- Lint fail-on-revert also holds: `TestSelfMirroringMock` goes red if
  `_check_self_mirroring_mock` is reverted.

### 6. GOOD — scope is clean
- Test-only: 2 test files + 1 tool. No production code touched. Confirmed by diff stat.

---

## Recommended remediation before merge
1. Reclassify `anthropic` as a native-Anthropic-shape `xfail` case (or documented
   exemption) + fix the false `_canonical_shape` docstring claim. (Finding 1)
2. Wire the self-mirroring enforcer into the CI gate, or state it is advisory. (Finding 2)

Both are small. The parametrization design, loud-fail guard, cline xfail scoping, and
scope discipline are all correct and worth keeping.
