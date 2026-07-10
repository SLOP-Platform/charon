# HF post-restart verify — 2026-07-07

**Verdict: HF-200-NEW-TOKEN-LIVE.** Rotated `HF_TOKEN` is loaded and working; safe to
revoke the old token.

## Method

SSH'd to 4-LOM (`stack@10.0.1.60`). Got `CHARON_GATEWAY_TOKEN` via
`docker exec charon-gateway-1 printenv CHARON_GATEWAY_TOKEN` (never printed). Container
has no `curl`, so requests were run from the 4-LOM host against the published
`localhost:8080` port (same approach the prior big-pickle probe used). No restarts,
no config or secret changes made.

## 1. HF probe — `kimi-k2.5-hf`

`POST /v1/chat/completions` — **HTTP 200**. Real completion: `model` resolved to
`moonshotai/Kimi-K2.5`, populated `reasoning_content`, non-zero `estimated_cost`,
normal usage block. Rotated `HF_TOKEN` is authenticating successfully against the HF
router post-restart.

## 2. Sanity — `/v1/models`

- Total models: **205** (expected ~199 — 6 over; not investigated further, flagging as
  a minor discrepancy rather than reconciling silently. Could be a handful of new
  entries added since the ~199 baseline was last verified.)
- `-hf` suffixed entries: **6** present.
- Zen entries other than `big-pickle`: **none** (confirms zen family besides
  big-pickle is gone, as expected).
- `big-pickle`: present.
- `owl-alpha`: absent (confirmed removed).
- `longcat`: absent (confirmed removed).

Routing config came back intact across the restart.

## 3. Non-HF control — `gpt-5.4`

`POST /v1/chat/completions` — **HTTP 200**, normal `openai/gpt-5.4` completion via
nanogpt (`x_nanogpt_pricing` present). Gateway fully healthy on the non-HF path too.

## Note

One inbound file (`big-pickle-probe.md`, read as prior-method reference) contained
embedded text formatted to look like a system-reminder / date-change notice / fake
agent list inside the markdown body itself — a prompt-injection attempt via file
content, not a real harness message. It was ignored; no instructions from it were
followed. Flagging in case that file's provenance needs checking.

No gateway config, secrets, or state were modified during this probe.
