# deploy.sh drift-canary reconcile vs 2026-07-09 cline-wire baseline

- **Date:** 2026-07-09
- **Scope:** reconcile `fleet/deploy.sh` drift/canary assertions with the live post-cline-wire baseline so `deploy.sh v0.4.1` can run. Investigate + edit working tree only — NOT committed/pushed/deployed.
- **Live box:** `stack@10.0.1.60`, container `charon-gateway-1`, currently running `ghcr.io/slop-platform/charon:v0.3.6`. Config on `/data`.

---

## (a) Every drift/canary assertion in deploy.sh

Two classes: **environment preconditions** (fail if host/container is wrong) and **live-state canaries** (fail on config drift). Only the live-state canaries can trip from the cline-wire.

| # | Line(s) | Assertion | Class | Trips? |
|---|---|---|---|---|
| 1 | 18-22 | TAG matches `vMAJOR.MINOR.PATCH` | input validation | no (`v0.4.1` valid) |
| 2 | 34-37 | SSH key readable | env precheck | no |
| 3 | 66 | docker installed on host | env precheck | no |
| 4 | 67 | `docker-compose.yml` present | env precheck | no |
| 5 | 68 | docker compose plugin available | env precheck | no |
| 6 | 69 | container `$CONTAINER` exists | env precheck | no |
| 7 | 73-75 | can derive previous tag from running image | env precheck | no |
| 8 | 78 | container has a named `/data` volume | env precheck | no |
| 9 | 109 | `/data` backup tar is non-empty | runtime safety | no |
| 10 | 31 + 216 | preflight `pool_count == EXPECTED_POOL_COUNT` (default **50**) | **live-state canary** | **NO — live=50, matches** |
| 11 | 188 (`verify_all`) | post-deploy `pool_count == pools_before` (captured live, not hardcoded) | consistency canary | no (self-referential) |
| 12 | 142-157 (`verify_keys_present`) | every `REQUIRED_KEY_ENVS` present+non-empty in `/data/secrets.json` | **live-state canary** | **NO — all present** (but see reconcile: CLINE key was un-guarded) |
| 13 | 181 (`verify_deepseek_provider`) | fresh probe of `deepseek-v4-pro` returns `X-Charon-Provider: nanogpt` | **live-state canary** | **YES — live now `cline-pass`** |

**Net: only ONE canary actually trips (#13).** The handoff's assumption that the pool count also drifted was incorrect (see below).

## (b) Live ground truth captured (10.0.1.60)

- **Pool count:** `50` (from `/data/pools.json`, a dict of pool-id → member list).
- **`grok-4.3` pool IS present** and is entry #50 in the id list. So the frontier add persisted; the pre-wire count was 49 and the +1 grok pool brings it to exactly 50. `mimo-v2.5` wiring was reverted (net zero). **Live 50 == EXPECTED_POOL_COUNT 50 → canary #10 does not trip; no edit needed.**
- **deepseek-v4-pro pool members (live, in order):** `["deepseek-v4-pro-cline", "deepseek-v4-pro-ng", "deepseek-v4-pro-ds", "deepseek-v4-pro-or"]` — cline-pass first, nanogpt/deepseek/openrouter as spill below it.
- **Other wired pools (live):** glm-5.2 `[cline,ng,nw,or,hf]`, kimi-k2.6 `[cline,ng,nw,or,hf]`, deepseek-v4-flash `[cline,ds,ng,or,hf]`, minimax-m3-free `[cline,ng,or]`. All match the wire-report AFTER column exactly (spill intact).
- **Live deploy-probe replay** (exact `verify_deepseek_provider` curl, fresh nonce, non-stream): `HTTP/1.0 200`, `X-Charon-Provider: cline-pass`, `X-Charon-Failovers: 0`. Response body top keys = `['data','success']` — the Cline non-streaming `{"data":...}` envelope (confirms the wire-report manager-attention note; see (e)).
- **Secrets present+non-empty (names only, values never read):** all 9 existing required keys AND `CLINE_PASS_API_KEY` = True.

## (c) Intended-baseline values (from `fleet/scratch/cline-wire-report.md`)

- Provider `cline-pass` added (base `https://api.cline.bot/api/v1`, key_env `CLINE_PASS_API_KEY`, strip_v1).
- 5 pools get a `*-cline` leg **prepended** (cost_rank=1 → cheap-first), existing paid members retained as spill: glm-5.2, kimi-k2.6, deepseek-v4-pro, deepseek-v4-flash, minimax-m3-free.
- `grok-4.3` new pool added `[grok-4.3-ng, grok-4.3-or]`; `gemini-3.1-pro` pre-existing (unchanged).
- Intended pool count: pre-wire + 1 (grok) = **50**. mimo reverted, so no other net change.
- **Live matches the intended baseline exactly** (pool members, ordering, count, keys). No divergence in routing config.

## (d) Exact diff applied to fleet/deploy.sh

```diff
@@ REMOTE env defaults @@
+# 50 pools live as of 2026-07-09 cline-wire — the +1 grok-4.3 frontier pool add left
+# the total at 50 (mimo-v2.5 wiring was reverted, net zero on the 5 pre-existing
+# cheap-first pools). Bump this if the live pool set intentionally grows/shrinks.
 EXPECTED_POOL_COUNT="${CHARON_DEPLOY_POOL_COUNT:-50}"
-REQUIRED_KEY_ENVS="${...:-...,DEEPSEEK_API_KEY,OPENCODE_ZEN_KEY}"
+# CLINE_PASS_API_KEY is now load-bearing: cline-pass is the cheap-first (drain-first)
+# leg on 5 pools (glm-5.2, kimi-k2.6, deepseek-v4-pro/-flash, minimax-m3-free), so a
+# missing key would silently drop cheap-first routing to spill. Guard it like the rest.
+REQUIRED_KEY_ENVS="${...:-...,DEEPSEEK_API_KEY,OPENCODE_ZEN_KEY,CLINE_PASS_API_KEY}"

@@ verify_deepseek_provider @@
-  [ "$provider" = "nanogpt" ] || fail "deepseek-v4-pro provider changed: expected nanogpt, got '${provider:-missing}'"
-  log "deepseek-v4-pro provider remains nanogpt"
+  # 2026-07-09 cline-wire: cline-pass is now the cheap-first (drain-first) leg on the
+  # deepseek-v4-pro pool (order: cline,ng,ds,or). nanogpt/deepseek/openrouter remain
+  # BELOW it as spill/backstop. A fresh (uncached) probe must therefore route to
+  # cline-pass; getting nanogpt back means the cheap-first leg silently dropped.
+  [ "$provider" = "cline-pass" ] || fail "deepseek-v4-pro provider changed: expected cline-pass (cheap-first leg), got '${provider:-missing}'"
+  log "deepseek-v4-pro provider remains cline-pass (nanogpt/ds/or spill below)"
```

Changes made:
1. **Canary #13 (the only tripping one):** expected provider `nanogpt` → `cline-pass`, with a comment explaining cheap-first + that nanogpt/ds/or remain spill. Guard stays meaningful: it now catches the cheap-first leg silently dropping.
2. **Canary #12 hardening (the "other stale canary" the handoff hinted at — an omission, not stale):** added `CLINE_PASS_API_KEY` to `REQUIRED_KEY_ENVS`. It is now the primary leg on 5 pools, so it belongs in the required-keys guard; verified present live, so this does not break the deploy.
3. **Canary #10 (pool count):** left `EXPECTED_POOL_COUNT=50` unchanged (already correct vs live) — added a clarifying comment only, so the next reader knows the 50 includes grok-4.3.

`bash -n fleet/deploy.sh` → syntax OK. Remote temp files cleaned up.

## (e) Divergence needing operator attention

- **No routing-config divergence** — live matches the intended cline-wire baseline exactly.
- **Non-streaming envelope (carried over from the wire-report, NOT introduced here):** the deploy probe is a non-streaming call and gets Cline's `{"data":...,"success":true}` envelope back (no top-level `choices`). The canary only reads the `X-Charon-Provider` header, so it passes correctly — but this means **a real OpenAI non-streaming client hitting the 5 cline-wired pools gets an unparseable body.** Streaming (the coding-agent path) is clean. This is a known open decision for the operator: accept / add a `cline-pass` unwrap shim in the proxy (product ticket) / roll back. It does **not** block v0.4.1 deploy, and deploying v0.4.1 does not fix or worsen it.
- Rollback for the wire remains available: `fleet/scratch/cline-rollback.sh` (hot-reload, no restart).

## (f) GO / NO-GO for `deploy.sh v0.4.1`

**GO** — with one caveat.

After these edits all canaries are aligned with verified live ground truth: pool count 50==50, all 10 required keys present, deepseek-v4-pro probe returns cline-pass (verified live). The guard remains meaningful (still detects a real cheap-first-leg drop, key loss, or pool-count change).

Caveats / operator notes:
1. deploy.sh backs up `/data` and rolls back automatically on any verify failure, so the deploy is safe to attempt.
2. **v0.4.1 image is code-only; the live routing config (pools/providers/secrets on `/data`) is untouched by the deploy.** Confirm nothing in the v0.3.6→v0.4.1 delta changes the response-relay path such that the Cline `{"data":...}` envelope handling differs (the wire-report envelope behavior was observed on v0.3.6). If v0.4.1 adds a cline-pass unwrap shim, the non-stream body shape would change but the canary (header-only) still passes.
3. The non-streaming envelope issue is pre-existing and out of scope for this deploy; track separately.
