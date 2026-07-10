# Charon 4-LOM gateway — live config pass (P4) report

Date: 2026-07-09 (UTC) · Gateway: 4-LOM `charon-gateway-1` v0.3.6 (build f369b7c) · Executed live, hot-reload (NO restart)
Scope: P4 config-only (reversible, additive). NO code, NO restart, NO balance top-ups.
Access: `ssh -i ~/.ssh/4lom stack@10.0.1.60`; unprivileged `docker exec` (stack in docker group); setup-API POST hot-reloads.

## TL;DR
- **One change applied:** `fallback_providers` `[]` → `["opencode-go"]`. Appended LAST to every pool (order-safe), verified live.
  This gives **every OPEN-model pool** (glm/kimi/deepseek/qwen/minimax) a funds-independent last resort.
- **gpt-5.4 now serves 200** — but NOT because of my change: the acute outage had already **self-resolved** (nanogpt balance recovered; openrouter healthy). Both metered members return 200 right now.
- **No closed-model pool was widened** (gpt-5.4, gpt-5.x, claude-*, gemini-*, grok). Empirically confirmed **capability catch**: the ONLY providers that serve those closed models are nanogpt + openrouter (both balance-gated). Every funded/free/opencode backend returns `401 "Model X is not supported"`. A funds-independent backstop for gpt-5.4 is **not achievable by config** — it needs P2 (cross-model substitution, gated code) or balance monitoring.
- **CF-1010 assumption corrected:** groq/cerebras/together returned **200 through the gateway** on the real `charon-proxy/0.1` egress UA. The 1010 block was specific to literal `Python-urllib`, not the gateway's actual outbound UA. They were still HELD — for capability/ordering reasons, not UA (see below).

## STEP 0 — Backup (mandatory, done BEFORE any change)
- **Off-host (4-LOM host) full /data copy:** `/home/stack/backups/charon-4lom-20260709T011209Z/` (includes `secrets.json`, mode 600; values never printed).
- **In-container timestamped baks:** `/data/{providers,pools,gateway,models,secrets}.json.configpass-20260709T011209Z.bak`.
- `fallback.json` did not exist pre-change (empty fallback = absent file).

### Rollback (exact)
Token: `TOK=$(ssh -i ~/.ssh/4lom stack@10.0.1.60 'docker exec charon-gateway-1 printenv CHARON_GATEWAY_TOKEN')`

- **Targeted revert of THIS change (hot, no restart):**
  ```
  ssh -i ~/.ssh/4lom stack@10.0.1.60 \
    "curl -s -X POST -H 'Content-Type: application/json' --data '{\"providers\":[]}' \
     http://localhost:8080/charon/fallback?token=\$(docker exec charon-gateway-1 printenv CHARON_GATEWAY_TOKEN)"
  ```
  (restores empty fallback; optionally `docker exec charon-gateway-1 rm -f /data/fallback.json`)
- **Full restore from backup:**
  ```
  ssh -i ~/.ssh/4lom stack@10.0.1.60 \
    "docker cp /home/stack/backups/charon-4lom-20260709T011209Z/. charon-gateway-1:/data/ && \
     curl -s -X POST -H 'Content-Type: application/json' --data '{\"providers\":[]}' \
     http://localhost:8080/charon/fallback?token=\$(docker exec charon-gateway-1 printenv CHARON_GATEWAY_TOKEN)"
  ```

## Key mechanism facts discovered (load-bearing)
1. **Pool members are model-id aliases**, each with its own provider+`upstream_model` (`-ng`=nanogpt, `-or`=openrouter, `-ds`=deepseek, `-nw`=neuralwatt, `-hf`=huggingface, `-go`=opencode-go).
2. **The compiler RE-SORTS every pool by cost** (`gateway.py:160` `sorted(eligible, key=_rank)`; free-first then derived cost). **The setup-API does NOT honor list order** for serve priority — it only breaks ties. So "order input-cheap-first" is automatic, and a *cheaper* member always sorts ahead. Consequence: adding a cheap open substitute (deepseek `cost_rank 20`, groq/cerebras `cost_rank 0`) to a closed pool would make it serve **before** the requested premium model — a silent happy-path hijack. This is why open substitutes were NOT added to closed pools.
3. **`fallback_providers` are PROVIDER NAMES, forwarded with the client's requested model id** (`upstream_model=None`, `gateway.py:243`; `proxy_server.py:510` keeps the original `bj["model"]`). A fallback provider only rescues a request whose **vid it natively accepts**. opencode-go's `upstream_model == vid` for all ids, so it accepts vid-format → viable. HuggingFace expects `org/Model` ids (`zai-org/GLM-5.2`), so a bare `huggingface` fallback would 404 on the forwarded vid `glm-5.2` — **HF is unusable as a bare fallback** despite serving 200 directly. (This is a real gap vs. the P4 design note, which assumed you could name an HF-served model.)
4. **Fallback is appended AFTER the cost sort (last).** Order-safe: never reached unless all pool members are exhausted → zero happy-path change.
5. **opencode-go's `401 "not supported"` is failover-eligible** (`proxy.py:226` `_is_unsupported_model` → `dropped`), and does NOT cool the provider. So on a closed pool the fallback attempt fails over to the existing terminal **503 "all providers exhausted"** — no leaked 401, no regression, no sidelining of opencode-go elsewhere.

## Through-the-gateway test results (real charon-proxy/0.1 egress UA, tiny max_tokens)
| backend (model id) | provider | HTTP | result / decision |
|---|---|---|---|
| gpt-5.4-ng | nanogpt | **200** | existing member — **healthy now** (was 402 in diagnosis; recovered) |
| gpt-5.4-or | openrouter | **200** | existing member — healthy (the `400` seen at `max_tokens:1` was min-tokens validation, not 402) |
| gpt-5.4-go | opencode-go | **401** not-supported | **HELD** — opencode-go does not serve gpt-5.4 (no capability match) |
| deepseek-v4-pro-ds | deepseek ($9.93) | **200** | funded, live — but a DIFFERENT model; NOT added to closed pools (cost-order hijack). Already a member of the open `deepseek-v4-pro` pool. |
| paid-neuralwatt-code | neuralwatt ($22) | **200** | funded, live (serves Kimi-K2.7-Code) — capability sub; NOT added to closed pools |
| glm-5.2-hf | huggingface | **200** | already a member of open glm pools; HF unusable as bare fallback (id-format mismatch) |
| free-groq | groq | **200** | serves gpt-oss-120b only; **HELD** (capability mismatch + free rank-0 would sort first) |
| free-cerebras | cerebras | **200** | serves gpt-oss-120b only; **HELD** (same) |
| minimax-m3-together | together | **200** | serves MiniMax-M3 only; **HELD** (capability mismatch) |
| opencode-go OPEN vids: glm-5.2, kimi-k2.6, deepseek-v4-pro, qwen3.6-plus, minimax-m2.7 | opencode-go | **200** | **→ chosen as the global fallback** (funds-independent, vid-native) |
| opencode-go CLOSED vids: claude-opus-4-8, claude-sonnet-4-6, gpt-5, gpt-5.5, gemini-3.5-flash, grok-build-0.1 | opencode-go | **401** not-supported | fail-over-eligible → still 503 on closed pools (no regression) |

**Tested-and-ADDED:** opencode-go (via global fallback) — 200 on all open vids.
**Tested-and-HELD:**
- gpt-5.4-go / all opencode-go closed vids — 401 "not supported" (capability).
- deepseek-v4-pro-ds, paid-neuralwatt-code — 200 but capability-substitute + cost-order hijack for closed pools.
- free-groq, free-cerebras, minimax-m3-together — **200 (NOT 1010)** but capability-mismatch; free/cheap rank sorts ahead of the requested model. **Held for capability/ordering, not UA** — the P5 UA fix is NOT required for these to be reachable on the proxy serve path (correcting the six-provider-verify assumption). NB: the CF-1010 risk may still apply to the `balance.py` pollers, which use literal `charon-proxy/0.1`/urllib — out of scope here.

## Per-pool BEFORE → AFTER
The change is a single global fallback, so the transform is uniform: **every** pool (and every single-route model) gains `opencode-go` appended LAST. Representative pools (from live `/charon/status` after reload):

| pool | BEFORE (members, cost-sorted) | AFTER |
|---|---|---|
| gpt-5.4 | nanogpt, openrouter | nanogpt, openrouter, **opencode-go** (opencode-go 401s → no real rescue; capability catch) |
| deepseek-v4-pro | nanogpt, deepseek, openrouter | nanogpt, deepseek, openrouter, **opencode-go** (real funds-independent backstop) |
| glm-5.2 | nanogpt, neuralwatt, openrouter, huggingface | + **opencode-go** (real backstop) |
| qwen3.6-plus | nanogpt, openrouter | nanogpt, openrouter, **opencode-go** (real backstop) |
| (all other pools) | unchanged | + **opencode-go** appended last |

No member was removed or reordered; opencode-go sits last in every chain (post-sort append).

## gpt-5.4 post-change serve result
**HTTP 200** through the gateway (served by openrouter; `model: openai/gpt-5.4`). Both metered members (nanogpt + openrouter) are healthy right now — the diagnosis-era dual-402 had already cleared via balance recovery. The fallback does NOT contribute to gpt-5.4 (opencode-go 401s it); gpt-5.4's resilience remains entirely on nanogpt + openrouter balances.

## What still needs doing (routed elsewhere — NOT this pass)
- **gpt-5.4 / all closed-model pools have NO funds-independent backstop and cannot get one via config** (capability catch). Durable fix = **P2 cross-model/tier substitution** (gated code, separate droid) or **balance monitoring/alerting** on nanogpt+openrouter. Until then, a simultaneous dual-402 on those two providers will again 503 (now at least with the P1 `Retry-After` fix pending in the same design).
- **HuggingFace can't be a bare fallback** (id-format mismatch). If HF-as-backstop is wanted, the fallback mechanism needs a per-entry `upstream_model` map (small code change) — note for the P4/P5 droid.
- **P5 UA fix priority is lower than assumed** for the proxy serve path (groq/cerebras/together already 200 on `charon-proxy/0.1`); still relevant for the balance pollers.

## CONFIDENCE
- Change applied + order-safe + hot-reloaded, no restart: **HIGH** (live `/charon/config`, `/charon/status`, container `Up 20h healthy`).
- gpt-5.4 serves 200 / both members healthy: **HIGH** (live 200s).
- Capability catch (only nanogpt+openrouter serve closed models; opencode/funded backends 401): **HIGH** (per-backend live 401/200).
- CF-1010 correction (default UA not blocked): **HIGH** for right-now; **MEDIUM** on durability (CF rules can change; free tiers are bursty).
- opencode-go as a durable backstop: **MEDIUM** — it shares OPENCODE_ZEN_KEY and its own plan/rate limits are unquantified; it served all open vids at 200 now, but leaning on it fleet-wide as last resort is unproven under load.
