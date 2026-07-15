repo: charon
tier: economy
difficulty: 2
work_class: routing
branch: feat/destiff-cli-chat
owns: src/charon/cli.py, tests/test_cli_chat_failover.py
depends_on:
note: |
  "No stiff single-provider tools" class-fix (operator directive 2026-07-15). The cli.py chat
  call (cli.py:395, POST to /chat/completions) is single-provider-stiff. Adopt the SHARED
  primitive src/charon/failover_loop.py::invoke_with_failover (on master, #141) so the CLI chat
  path fails over across configured providers instead of hard-failing on one. Fix-at-the-CLASS
  by COMPOSITION, not a bespoke loop. See MANAGER-OPERATING-RULES §12.
accept: |
  ## Task
  - Route the cli.py:395 chat call through failover_loop.invoke_with_failover over the ordered
    trusted-model candidate list; on transport/auth/limit failure, fail over to the next
    provider; exhaust the pool before erroring, with a clear "pool exhausted" message.
  - Preserve the CLI command's existing output contract + flags. Do NOT change unrelated cli.py.
  ## Accept (fail-on-revert)
  - New tests/test_cli_chat_failover.py: first candidate 401s, second succeeds -> the CLI uses
    the second (failover proven); all fail -> clear non-zero exit + "pool exhausted" message.
  - PYTHONPATH=src python3 -m pytest -q tests/test_cli_chat_failover.py
    && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/cli.py && mypy src/charon/cli.py
    && PYTHONPATH=src python3 -m charon.cli gate   (all GREEN)
  ## Dependencies & sequence
  depends_on: (none) — failover_loop is on master (#141). Disjoint from DESTIFF-RECOMMEND (cli.py vs recommend.py).
