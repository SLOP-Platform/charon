repo: charon
tier: economy
priority: 2
difficulty: 3
work_class: ci-infra
branch: feat/outcome-test-owed
owns: tests/test_gateway_outcome.py
depends_on:
dep-kind:
work_class_note: ci-infra — this is a D-005 trust mechanism (an acceptance test asserting
  client-observable behaviour), not a feature. It is how the operator gets quality they can
  verify without reading code.
note: |
  OWED WORK — see fleet/state/DECISIONS.md D-006. The operator asked for
  tests/test_gateway_outcome.py and it was NEVER delivered: `git log --all` showed zero commits
  on any branch. The design survived (fleet/state/OUTCOME-TEST-BLUEPRINT.md, deliberately
  git-tracked) and the implementation was dropped — D-007's class in a single artifact.

  BUILT 2026-08-03: 316 lines, 5 tests, implementing blueprint §3. §1 was correctly NOT
  implemented — it passes on a gateway with zero failover and reports "runner not found" as a
  behaviour failure.

  Behaviours asserted, all on client-visible surfaces (real HTTP status, real envelope, real
  X-Charon-* headers, real requests arriving at a mock upstream socket; hermetic loopback, 10s
  deadline, no skip/xfail anywhere):
    1. INFRA gate — mock upstream + gateway + /charon/status really come up (INFRA-worded, so an
       infra failure can never be misread as a behaviour failure).
    2. Every leg parked -> client still gets a real 200 with a non-empty completion; the first
       leg's socket really received the request; parks were not silently cleared.
       (covers the never-strand fallback at src/charon/forwarder.py:481-487)
    3. A parked leg receives NO http request while a live sibling exists; pre-flight exclusion is
       not miscounted as a failover.
    4. Total exhaustion (parametrized 429/402) -> real 503, never a success-shaped body;
       `all_providers_exhausted` names both legs with truthful per-leg status + non-empty reason;
       header reports 2 attempts; both upstreams really got traffic.
    5. Stranded (no HTTP response) and hung (no response inside the deadline) raise DISTINCT loud
       failures — "could not check" is never reported as "passed".

  RED-PROOF — 8 breaks, each applied to src/, run, then reverted (tree verified byte-identical
  to HEAD afterwards; branch diff touches tests/ ONLY):
    never-strand `else` removed        -> RED "closed connection without writing any HTTP response"
    `is_parked` continue disabled      -> RED "a PARKED provider was really dispatched"
    exhaustion 503 -> 200              -> RED (both params)
    per-leg `reason` blanked           -> RED (both params)
    X-Charon-Failovers hardcoded "0"   -> RED (both params)
    200 served with b"{}"              -> RED (silent-success caught)
    time.sleep(30) in forwarder        -> RED "no response within 10s"
    /charon/status route removed       -> RED **INFRA-worded only**; behaviour tests stayed green

  PARTS OF §3 DELIBERATELY REJECTED (each would have reproduced §1's fatal defect):
    - CHARON_FAULT_INJECT / CHARON_UPSTREAM_MODE / CHARON_LEDGER_PATH — **zero readers in src/ or
      tools/**, so monkeypatch.setenv on them injects NO fault. Faults now come from real upstream
      429/402 and real park state.
    - run_gateway_pipeline.py — does not exist on any branch.
    - the per-attempt "ledger" — src/charon/ledger.py is the WORK ledger and is **not wired into
      forwarder.py/proxy_server.py at all**; the real per-attempt record is `providers_tried` +
      headers. (NEW INERT-MODULE FINDING, worth its own ticket.)
    - pytest.importorskip — a skip is "could not check reported as passed".
    - `status in (200, "EXHAUSTED")` as one assertion — unfailable when a healthy leg exists; split
      into scenarios that each pin one required terminal state.

  VERIFIED BY THE MANAGER, not taken on report: file present (316 lines), worktree clean, branch
  diff = tests/ only, `pytest tests/test_gateway_outcome.py` = **5 passed in 0.56s**.

  This ticket was minted AFTER the work, because the commit hook correctly refused the branch
  ("maps to NO board ticket") and the agent had to use WORK_LEASE_BYPASS. The lesson is the
  ticket must exist BEFORE the branch — recorded so the next fan-out mints first.
