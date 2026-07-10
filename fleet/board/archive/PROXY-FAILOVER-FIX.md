tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: money-path
branch: fix/proxy-failover
depends_on:
real-dep: none (Phase 1 is self-contained). SEQUENCE-INTERNAL: P1 (Retry-After) must land
  before P2 (cross-model substitution) is enabled; P2 is gated on an operator decision for the
  least-surprise contract + confirmation that tiers.json is populated in prod. P3 (balance
  demotion) strongly complements P2 but is not a hard prereq.
owns: src/charon/proxy_server.py, src/charon/balance.py, tests/test_proxy_server.py,
  tests/test_balance.py
accept: PYTHONPATH=src python3 -m pytest tests/test_proxy_server.py tests/test_balance.py -v -q
phase1-note: SCOPED TO PHASE 1 (P1 Retry-After + P5 outbound UA) ONLY. Phase-1 code is
  header-only / outbound-only and LOW-RISK (no routing or spend change). work_class stays
  money-path to carry P2's later framing, but Phase 1 itself is NOT a money-path change.
  owns trimmed to the 4 Phase-1 files (gateway.py/config.py/test_gateway_*.py belong to P2/P3,
  not this tab). BUILD PROMPT is proxy-failover-fix.md (P1+P5); the design doc remains the
  full multi-phase spec.
prompt: /home/stack/charon-private/prompts/proxy-failover-fix.md
scope: Root-fix the confirmed gateway failover bug (raw client got 503 all_providers_exhausted
  on gpt-5.4 when both 2-member-pool backends returned 402, then ran away to ~8h client
  backoff). PHASED — build in order; DESIGN of record is the prompt file. Phase 1 (ship alone,
  NO money-path): P1 emit a bounded Retry-After on the terminal 503 (proxy_server.py:826) and on
  single-upstream 402/429 relays (:838), via a new retry_after param on _send_resp_headers
  (:483) + a retry_after_hint(chain) helper tied to the soonest cooled member and clamped to
  [1, max_cooldown_s=120]; P4 config guidance (populate a non-balance-gated fallback_providers
  backstop — mechanism already exists at gateway.py:236-258); P5 outbound browser-like
  User-Agent fix — groq/cerebras/together return 403 "error code: 1010" (Cloudflare bot-block on
  a non-browser UA, NOT auth/credit), which marks funded providers dead. Make the shared default
  UA browser-like: proxy_server.py:71 _DEFAULT_UA is currently "charon-proxy/0.1" (NOT
  browser-like) and balance.py:41/70/100 hardcode the same string on the deepseek/openrouter/
  nanogpt pollers (blocked polls corrupt P3's demotion signal). Promote ONE shared browser-like
  UA constant used on all outbound provider requests + probes/polls (per-provider UA override is
  a fast-follow for the forwarded-client-UA case); sweep other urllib users (discover/connect/
  providers/observability/routing_proxy/speculative_execution) onto it. P5 is header-only,
  no-money-path, and is a PREREQUISITE for widening the fragile 2-member pools with those
  spillover backends (P4) actually working. Phase 2 (MONEY-PATH, opt-in
  default OFF — this is why work_class=money-path): P2 cross-model/tier substitution on the
  proxy serve path — when a model's own pool is exhausted, substitute a same-tier sibling using
  a model_tier reverse index built from tiers.json (config.load_tiers) and the already
  cheapest-first-compiled tier pool (gateway._tier_pools); extend chain_for/serve loop, announce
  via X-Charon-Downgrade, gate behind a new default-OFF gateway.json toggle, same-tier-only,
  premium-gated, spend-cap-checked. Do NOT duplicate engine failover (failover.py/router.py) —
  reuse the shared _build_routes_and_pools ordering semantic. Phase 3: P3 wire the currently-
  dead BalanceTracker into gateway.load_config + demote is_drained providers to a last bucket in
  order_by_cooldown (fail-safe: unknown balance = not drained). P3 SCOPE GENERALIZED (decision #4,
  2026-07-08): balance-aware demotion must be generalized to RESOURCE-AVAILABILITY monitoring, not
  just balance. Resource = balance (PAID providers: nanogpt, openrouter) AND quota / rate-remaining
  (FREE tiers: daily/weekly/monthly request or token limits). Use free-tier resources up to their
  daily/weekly/monthly limits, then spill when exhausted. ALERTING: warn when nanogpt AND openrouter
  both run low at once — because of the capability catch (closed pools have no other backstop), if
  both paid backstops drain there is nothing left to fail over to. Demotion input becomes a unified
  "resource remaining" signal (balance for paid, quota/rate-remaining for free), fail-safe unknown =
  available. BLAST RADIUS: P2 routes spend to
  a provider/model the client did not name — money-path; mitigations (default OFF, same-tier,
  premium gate, spend cap, P3 demotion) are mandatory, not optional. Suggested split: spec is
  done (prompt file); implement Phase 1 on strong tier, Phase 2 on frontier (Claude Opus 4.8) —
  WHY: the Retry-After header math is mechanical, but the substitution contract's interaction
  with the downgrade-detection path, spend cap, and tier reverse-index is design-sensitive.
  Product must ship STANDALONE — no fleet/SLOP/rig dependency may leak in (confirmed in design).
  PRIORITY NOTE (decision #2, 2026-07-08): P2 (cross-model/tier substitution) is THE priority
  durable fix for closed-pool resilience — when a closed pool is exhausted, same-tier substitution
  is the only backstop that keeps serving. P1 (Retry-After) stops the ~8h client stall but does not
  restore service; P2 is what actually keeps requests flowing once a pool is dry. Sequence stays
  P1 first (ship solo, no money-path), but P2 is the load-bearing resilience fix to prioritize next.
