repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: money-path
branch: feat/sr-5b-cost-usd-wire
depends_on: SR-5, SR-2, TIER-SELECT
real-dep: SR-5 build — SR-5 CAPTURES per-token pricing into the model registry; SR-5b CONSUMES it
  (cost_usd = tokens_in*cost_input + tokens_out*cost_output). Pricing must be captured AND stored in
  SR-5's canonical unit FIRST, or the multiply is garbage. Disjoint owns (SR-5 config/discover/
  providers vs SR-5b proxy.py/proxy_server.py) — JUSTIFIED real build/correctness prereq, NOT
  merge-order. SR-5b must read SR-5's canonical price unit exactly (coordinate the unit with SR-5).
real-dep: SR-2 build (single-owner file src/charon/proxy_server.py) — SR-2's revision is the sole W2
  owner of proxy_server.py; SR-5b edits the same spend-limiter pre-flight/record call sites and must
  rebase onto SR-2's file, never write it concurrently.
real-dep: TIER-SELECT build (single-owner file src/charon/proxy_server.py) — proxy_server.py has a
  strict single-owner chain SR-2 -> SR-6 -> SR-7 -> SR-8 -> TIER-SELECT (W2/W3 + tier-select). SR-5b
  lands AFTER the last current owner (TIER-SELECT) so it rebases onto the final file, never a
  concurrent second writer. Shared-file sequencing, JUSTIFIED (not merge-order-only). Also transitively
  orders SR-5b after SR-1 (proxy.py owner) via SR-2 -> SR-1.
owns: src/charon/proxy.py, src/charon/proxy_server.py
prompt: /home/stack/charon-private/prompts/sr-5b.md
scope: Consumption half of SR-5 — the money-path multiply. SR-5 captures per-token pricing but nothing
  multiplies it by tokens, so cost_usd (proxy.py ~:98 _gateway_usage) still reads ONLY the provider's
  self-reported cost/total_cost; providers that don't echo a cost record cost_usd=0, leaving
  cost-ranking + spend caps inert (root of the "cost_usd always 0 / availability-only routing" seen all
  session). Compute cost_usd from stored pricing when the provider reports none, and feed the SAME
  computed cost to the spend limiter's pre-flight estimate (proxy_server.py ~:657, currently a hardcoded
  rate) and spend_limiter.record (~:777, currently the provider number). Distinguish "unknown/unpriced"
  (leave 0 + flag) from "priced at 0". Sole new proxy_server.py owner after the SR chain + TIER-SELECT;
  does NOT own spend_limits.py (SR-7) — only its call sites in proxy_server.py.
