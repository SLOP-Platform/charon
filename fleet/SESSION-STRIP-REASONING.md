# Build session — #5: strip output-only fields (reasoning_content) from inbound messages

You are a Charon build session (strong coder). Repo: `/home/stack/code/charon`.

## MANDATORY isolation (Fleet-Droid process — no exceptions)
1. `git worktree add /home/stack/code/charon-strip -b feat/strip-reasoning-content master`
2. Register on the session-bridge (repo:"charon"), claim this ticket, announce you OWN `src/charon/proxy_server.py` (the request-forwarding path) + any new helper. Work ONLY in `charon-strip`. Do NOT touch `gateway.py`.

## Scope (the bug this fixes)
When Charon fails over / continues multi-turn across providers, the conversation can carry an assistant `reasoning_content` field emitted by one provider (DeepSeek-style). Another provider (e.g. Groq) then rejects the request: `role:assistant ... property 'reasoning_content' is unsupported`. This blocks using free/cheap tiers as cross-provider substitutes.
1. In the request-forwarding path (before sending the body upstream), STRIP output-only fields from INBOUND `messages[*]` — at minimum `reasoning_content` on assistant messages; also drop other known provider-only echo fields (e.g. `reasoning`, provider-specific `tool_call`-metadata that isn't OpenAI-spec). Be conservative: only strip fields that are output-only and not part of the OpenAI chat request spec.
2. Symmetric in spirit to `response_normalizer.py` — keep it small, stdlib, well-commented. Config-gate if risky, else safe-by-default.
3. Tests: an inbound body with assistant `reasoning_content` is forwarded WITHOUT it; a normal body is untouched; tool_calls preserved.

## Gate + finish
Run BOTH `python3 -m charon.cli gate` AND `PYTHONPATH=src python3 -m pytest -q`. Commit to `feat/strip-reasoning-content`. **DO NOT push/PR** — Claude review + operator gate (routing path). Report branch + test counts. No fleet/SLOP/personal strings in `src/`. **D&S:** owns proxy_server.py; disjoint from #6 (gateway.py) + #17 (balance.py). #4a/#4b/Global-Fallback sequence AFTER this on proxy_server.py.
