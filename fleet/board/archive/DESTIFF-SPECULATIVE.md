repo: charon
tier: frontier
difficulty: 3
work_class: routing
branch: feat/destiff-speculative
owns: src/charon/speculative_execution.py, tests/test_speculative_execution.py
depends_on:
note: |
  "No stiff single-provider tools" class-fix (operator directive 2026-07-15) — 4th and last known
  stiff caller. speculative_execution.py calls one upstream (_call_upstream, ~line 42) with no
  cross-provider failover. Adopt the SHARED primitive src/charon/failover_loop.py::invoke_with_failover
  (on master, #141) by COMPOSITION. Frontier tier because speculative execution is latency-sensitive
  and the failover interaction with speculation needs care (don't double-issue / race the primitive).
accept: |
  ## Task
  - Route speculative_execution's upstream call through failover_loop.invoke_with_failover over the
    ordered candidate list, so a provider transport/auth/limit failure fails over to the next instead
    of failing the speculation. Preserve the speculative-execution semantics (first-good-wins,
    cancellation) — do NOT let failover double-issue requests or defeat the speculation's own racing.
  - Keep the existing public surface + timeouts.
  ## Accept (fail-on-revert)
  - Test: first candidate 401s mid-speculation -> failover to next yields a result (not a hard fail);
    a genuine all-fail -> clear exhaustion error. Speculation's first-good-wins still holds.
  - PYTHONPATH=src python3 -m pytest -q tests/test_speculative_execution.py && PYTHONPATH=src python3 -m pytest -q
    && ruff check src/charon/speculative_execution.py && mypy src/charon/speculative_execution.py
    && PYTHONPATH=src python3 -m charon.cli gate
  ## Dependencies & sequence
  depends_on: (none) — failover_loop on master (#141). Disjoint from other DESTIFF tickets (own file).
