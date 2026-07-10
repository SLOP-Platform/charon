tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: feat/request-normalizer
depends_on:
dep-pruned: INC-401-FAILOVER (removed 2026-07-08 — INC-401-FAILOVER parked for PROXY-FAILOVER-FIX; this ticket is DONE, so the proxy_server.py merge-order dep is already satisfied/historical. No restore needed on un-park.)
real-dep: INC-401-FAILOVER (the failover loop must correctly advance on non-DeepSeek
  provider errors before cross-provider substitution is safe).
owns: src/charon/proxy.py, src/charon/proxy_server.py, tests/test_proxy.py
accept: PYTHONPATH=src python3 -m pytest tests/test_proxy.py -v -q
prompt: /home/stack/charon-private/prompts/request-normalizer.md
scope: Strip output-only fields (reasoning_content) from inbound assistant messages in
  multi-turn requests. When a client sends a conversation history that includes a prior
  assistant response with reasoning_content (DeepSeek's chain-of-thought field), non-DeepSeek
  providers (Groq gpt-oss, etc.) reject the request because they don't understand that field.
  This is the KNOWN CROSS-PROVIDER BUG from HANDOFF-2026-07-04-v2 §"4-LOM live routing":
  routing deepseek-v4-pro to a non-DeepSeek provider breaks multi-turn because the replayed
  assistant reasoning_content field is rejected. Fix = a request-normalizer that inspects
  messages[] in the inbound request, and for any message with role=="assistant", strips
  output-only fields the target provider doesn't support. Must run BEFORE the request is
  sent to the upstream provider, in the proxy_server.py request path. Must be
  provider-aware (only strip when the target provider is non-DeepSeek). Unblocks free tiers
  as deepseek-v4-pro substitutes (decision #14: request-normalizer first, before
  quota/tool-repair hook wiring). Until this lands, keep non-DeepSeek providers out of the
  deepseek-v4-pro pool (decision #31). Suggested agent: DeepSeek V4-Pro (strong tier) —
  mechanical message-array filtering with a clear spec, no design judgement. The edge cases
  (streaming, tool_calls alongside reasoning_content) need careful tests but are
  well-defined.
