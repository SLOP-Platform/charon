repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: money-path
branch: feat/sr-7-spend-cap-hardening
depends_on: SR-2, SR-5
dep-pruned: SR-6 (removed 2026-07-08 — SR-6 parked for PROXY-FAILOVER-FIX; this ticket is DONE, so the proxy_server.py single-writer merge-order dep is already satisfied/historical. No restore needed on un-park.)
real-dep: SR-2 build (single-owner file proxy_server.py) — shared-file sequencing on proxy_server.py.
real-dep: SR-6 build (single-owner file proxy_server.py) — shared-file sequencing on proxy_server.py
  (SR-7 lands after SR-6 in the W3 chain).
real-dep: SR-5 needs pricing — SR-7's estimated-cost cap relies on the pricing capture SR-5 adds; a
  true correctness prereq. Owns are DISJOINT here (SR-7 spend_limits.py/proxy_server.py vs SR-5
  config.py/discover.py/providers.py), so the dep is JUSTIFIED, not assumed.
owns: src/charon/spend_limits.py, src/charon/proxy_server.py
prompt: /home/stack/charon-private/prompts/sr-7.md
scope: W3, second in the SR-6 -> SR-7 -> SR-8 proxy_server.py chain. Record an estimated cost even
  when computed cost is 0 so the universal monthly cap can't be bypassed by zero-priced/served calls.
