---
description: "CommandCode as a Charon provider is BLOCKED on plan tier — Go plan lists /models but 403s /chat/completions; only the $15/mo \"Provider\" (API Builder) plan exposes the OpenAI/Anthropic API Charon needs."
metadata: 
name: charon-commandcode-plan-gate
node_type: memory
originSessionId: f0885a70-8492-49ca-91ec-8aac49fad3b7
type: project
tags: [charon, gate]
last_referenced: 2026-07-13
---
**2026-07-04 — CommandCode provider integration is plan-gated (verified by probe + pricing page).**

Operator supplied a valid `COMMANDCODE_API_KEY` (Go plan). base_url `https://api.commandcode.ai/provider/v1`, Bearer auth. Findings:
- **Key valid**: `GET /models` → 200, 35 models incl. `deepseek/deepseek-v4-pro`, `deepseek/deepseek-v4-flash`, `claude-opus-4-8`, `claude-sonnet-5`, `claude-fable-5`, `claude-haiku-4-5`.
- **BUT `/chat/completions` → 403**: *"Your Go plan doesn't include API access. Upgrade to Provider or higher."* So CommandCode CANNOT be wired as a Charon provider on Go — every real call 403s. Did NOT touch prod `secrets.json`/pools (would poison pools with a dead primary).
- **Pricing reality (corrects the handoff premise):** the "$40 of DeepSeek-V4-Pro for $1/mo" Go perk is redeemable ONLY inside CommandCode's own app ("taste-1"), NOT via API. The consumer plans (Go/Pro/Max) give in-app credits, no API. Only the **API Builder "Provider" plan ($15/mo + pay-as-you-go, "zero markup, every deal applied", credits roll over)** exposes the OpenAI/Anthropic-compatible endpoints Charon calls. Provider is metered, not a fixed cheap bundle.
- **Cloudflare note:** api.commandcode.ai fronts with Cloudflare; python-urllib default UA got a transient `1010` bot-challenge once, but `python-httpx`/`charon-gateway` UAs then returned 200 — outbound User-Agent is NOT a hard blocker, just occasional CF challenges.

**2026-07-08 update:** re-confirmed the Provider $15/mo plan DOES expose `/chat/completions` (the 403 is the Go/coding plan, not Provider). But CommandCode is now **SUPERSEDED by Cline Pass** ($9.99/mo flat, confirmed full 256K context) for the cheap-open-weight coding leg — CommandCode stays PARKED. Its only distinct angle if revisited: zero-markup metered access to Claude frontier (Opus/Sonnet) + DeepSeek — not a need while the operator is on gpt-5.4. Stack decision recorded in [[charon-pools-redesign]] cost logic.

**DECISION — CONFIRMED (operator, 2026-07-10):** GO on the CommandCode **Provider $15/mo** API plan — operator confirmed $15/mo is the correct API tier (the 2026-07-08 supersede-by-Cline-Pass recommendation is OVERRIDDEN; operator wants both in the stack). Operator noted ~15–25k request headroom, DeepSeek V4 Pro + **99%-off MiMo V2.5**, $40/$120 usage tiers. This UN-PARKS CommandCode integration (#2 in [[charon-project-state]] handoff). If upgraded: probe `/chat/completions` again, add key to `/data/secrets.json`, add built-in preset (product code change → gate/merge chain), place PRIMARY in `deepseek-v4-pro` pool. Relates to [[charon-silent-downgrade-leak]], [[charon-deploy-drift-lessons]].
