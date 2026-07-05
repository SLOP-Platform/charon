tier: economy
branch: feat/gpt-5-pool-reorder
depends_on: INC-401-FAILOVER
real-dep: INC-401-FAILOVER (the 401 fix must land first so reordering doesn't just
  change which provider's raw error gets relayed).
owns: /data/pools.json (live 4-LOM config, not src/)
accept: curl -s -H "Authorization: Bearer <token>" -d '{"model":"gpt-5.5","messages":[{"role":"user","content":"hi"}],"max_tokens":5}' http://10.0.1.60:8080/v1/chat/completions | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'choices' in d, d; print('OK')"
prompt: /home/stack/charon-private/prompts/gpt-5-pool-reorder.md
scope: IMMEDIATE MITIGATION for BUG 1 (not the systemic fix — that's DRAIN-ROUTING +
  COST-RANK-AUTO). Reorder the live gpt-5.5 pool on 4-LOM to NanoGPT-primary:
  ["gpt-5.5-ng", "gpt-5.5-or", "gpt-5.5", "gpt-5.5-go"] → put the working provider first.
  Also audit gpt-5, gpt-5.4, gpt-5.4-pro, gpt-5.5-pro pools for the same stale -or-first
  order. POOLS-EDIT-PLAN.md explicitly excluded gpt-5* from reordering ("branded premium
  pools — LEAVE") — that decision caused this incident (the incident report is in
  HANDOFF-2026-07-04-v2 §"INCIDENT"). This is a live config change via the /charon/pools
  setup API or direct pools.json edit on 4-LOM, NOT a code change. Operator decision #27
  permits immediate production routing updates after verification. Suggested agent: this
  session (manager) — it's a live SSH + curl verification, not a build task. Do NOT
  delegate to a droid.
