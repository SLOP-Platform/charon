tier: strong
work_class: greenfield-feature
branch: feat/rfl-1-quota-tracking
depends_on: SR-13
real-dep: SR-13 build (single-owner file src/charon/proxy_server.py) — proxy_server.py has a strict
  single-writer chain (SR-2 -> SR-6 -> SR-7 -> SR-8 -> TIER-SELECT -> SR-5b -> SR-13). SR-13 is the
  current TAIL. RFL-1 adds a pre-flight quota check at the failover/selection call site in
  proxy_server.py `_handle` (~:649 chain build / ~:697 order_by_cooldown), so it MUST rebase onto the
  final file, never a concurrent second writer. Shared-file sequencing, JUSTIFIED (not merge-order).
  The new src/charon/quota.py module + tests are fully independent of the chain and could be built as
  an earlier phase if the proxy_server.py wiring is split out (see prompt §Dependencies & sequence).
owns: src/charon/quota.py, src/charon/proxy_server.py, tests/test_quota.py
prompt: /home/stack/charon-private/prompts/rfl-1.md
scope: TOP PICK (RelayFreeLLM comparison R1). Proactive free-tier quota tracking — a stdlib
  (`collections.deque` + `time.monotonic`, thread-locked) per-(provider,model) sliding-window tracker
  (request + token deques over 1s/60s/1h/24h) with a pre-flight `can_handle(tokens)` and
  `get_wait_time()`. Hook it into the pool exclude/order step in proxy_server.py `_handle` alongside
  `order_by_cooldown` so Charon SKIPS a provider that would 429 instead of burning a request+latency+429
  to learn a counter already knew; record usage on each response (token counts already available).
  Complements — does NOT replace — the existing Retry-After cooldown; different axis from the
  client-side virtual-key max_rpm/max_tpm (this is UPSTREAM provider quota). Suggested agent: DeepSeek
  V4-Pro (strong tier) — WHY: mechanical + well-specced (mirror RFL's api_limits_tracker.py), pure
  stdlib deque bookkeeping with a hermetic unit test; no subtle security/design judgement — reserve
  Claude for genuinely tricky work. Give it the explicit "stdlib only, no third-party imports"
  guardrail; the hermetic test + CI gate is the backstop.
