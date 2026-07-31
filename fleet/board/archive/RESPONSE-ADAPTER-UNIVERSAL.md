tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: feat/response-adapter-universal
depends_on: BILLING-EST-COST-FIX
real-dep: BILLING-EST-COST-FIX shared-file hand-off — this ticket edits the SAME forward_with_failover non-stream 200 path in forwarder.py that BILLING-EST-COST-FIX edits; it must rebase onto that merge and never run as a concurrent second writer. This edge makes the shared forwarder.py ownership legal under validate_board.sh.
owns: src/charon/response_adapters.py, src/charon/providers.py, src/charon/gateway.py, src/charon/proxy_server.py, src/charon/forwarder.py, tests/test_response_adapters.py, tests/test_proxy_server.py
accept: PYTHONPATH=src python3 -m pytest tests/test_proxy_server.py tests/test_response_adapters.py -q
prompt: /home/stack/charon-private/scratch/briefs/RESPONSE-ADAPTER-UNIVERSAL.md
scope: Implement fleet/ADR-UNIVERSAL-RESPONSE-ADAPTER.md (T1-T5; T6 streaming DEFERRED). New response_adapters.py (ResponseAdapter Protocol, IdentityAdapter+IDENTITY singleton default, ClineAdapter unwrap {data:{...choices...},success:true}, _ADAPTERS registry + get_adapter). Plumb an adapter key mirroring wire: ProviderPreset (providers.py) -> _route_from_spec (gateway.py) -> UpstreamRoute (proxy_server.py) -> resolved per attempt in the forwarder. Plug into forward_with_failover non-stream 200 path (~forwarder.py:271) behind `if route.adapter:` so IDENTITY stays byte-identical; guarded non-200 unwrap too. Add cline-pass preset (adapter=cline, strip_v1). Restores real usage metering for cline non-stream.
note: Money-path — ADVERSARIAL review before merge. Wave 2, gated on BILLING-EST-COST-FIX merge+done.sh. Frontier pool auto-claims once Fix 1 lands. Fix 3's cline-pass contract case is xfail(strict=False) and simply xpasses after this — no cross-ticket edit.
