# opencode-go cheap-first / opencode-zen deactivation — live gateway (4-lom 10.0.1.60)

- **Date:** 2026-07-10 (UTC)
- **Host/container:** `10.0.1.60` / `charon-gateway-1` (Up 11h, healthy). Config in `/data`.
- **Method:** SANCTIONED setup-API (`POST http://127.0.0.1:8080/charon/<action>?token=…`, validates + hot-reloads + persists to /data). **No image redeploy, no source edit, no restart, no commit.**
- **APPLIED: YES.** 4 of 5 pools now drain opencode-go-first (nanogpt immediate fallback); minimax-m3-free stays nanogpt-first (opencode-go does not serve it); opencode-zen removed from active routing but retained as provider + catalog entries; rollback ready.

---

## The fix (operator-confirmed)
The prior funding-class pass wired **opencode-zen** as a cheap-first leg (rank 20) on the 5 pools, but the operator does NOT hold the opencode-zen subscription — routing to it would fail. The held flat-rate opencode provider is **opencode-go** ($10/mo flat, $0-marginal, shares `OPENCODE_ZEN_KEY`).
1. **Deactivated opencode-zen** from active routing: removed its bare-id leg from all 5 pool member lists. **Provider entry KEPT** in providers.json and its catalog model entries KEPT in models.json (for future re-activation). Provider not deleted.
2. **Added opencode-go as the flat cheap-first leg** (`cost_rank=5`, ahead of nanogpt=10) on each pool **where opencode-go actually serves the model** — verified by direct `-go` probes before wiring. nanogpt (10) is the immediate next fallback on every pool.
3. Rest of the interim flat-fee-first order intact; cline-pass stays spill (rank 900, last).

**Mechanism (unchanged from prior pass):** pool failover order = `_build_routes_and_pools` re-sort by `(not free, cost_rank)` (all these legs are `free=False`, so cost_rank alone orders them). The member-list order mirrors ranks for clarity/ties. Lever = per-leg `cost_rank` via `/charon/models` + member lists via `/charon/pools`.

---

## Backups (STEP 1)
Timestamped `bak-opencode-20260710T010620Z`, in-container `/data`:
- `/data/pools.json.bak-opencode-20260710T010620Z`
- `/data/models.json.bak-opencode-20260710T010620Z`  ← backed up too (4 cost_ranks changed)
- `/data/providers.json.bak-opencode-20260710T010620Z`  (unchanged by this pass, backed up for a clean 3-file rollback)

---

## opencode-go model support (verified, not assumed)
Direct probes of the `-go` leg ids through the gateway BEFORE wiring:

| `-go` leg | HTTP | provider | choices | note |
|---|---|---|---|---|
| `glm-5.2-go` | 200 | opencode-go | YES | carries X-Charon-Downgrade (false-flag, see below) |
| `kimi-k2.6-go` | 200 | opencode-go | YES | carries X-Charon-Downgrade (false-flag) |
| `deepseek-v4-pro-go` | 200 | opencode-go | YES | clean |
| `deepseek-v4-flash-go` | 200 | opencode-go | YES | clean |
| `minimax-m3(-free)-go` | **does not exist** | — | — | no opencode-go catalog entry → NOT wired |

opencode-go serves **4 of the 5** models. There is no `minimax-m3-go`/`minimax-m3-free-go` catalog entry (opencode-go has `minimax-m2.5-go`/`minimax-m2.7-go` only), so **minimax-m3-free was left nanogpt-cheap-first, unchanged** except the zen bare-id leg was removed.

---

## Per-pool BEFORE → AFTER

Provider legend: go=opencode-go, ng=nanogpt, zen=opencode-zen (bare-id), hf=huggingface, or=openrouter, nw=neuralwatt, ds=deepseek, cline=cline-pass.

| Pool | BEFORE member list (rank) | AFTER member list (rank) |
|---|---|---|
| `glm-5.2` | ng(10), **zen(20)**, hf(30), or(50), nw(55), cline(900) | **go(5)**, ng(10), hf(30), or(50), nw(55), cline(900) |
| `kimi-k2.6` | ng(10), **zen(20)**, hf(30), or(50), nw(55), cline(900) | **go(5)**, ng(10), hf(30), or(50), nw(55), cline(900) |
| `deepseek-v4-pro` | ng(10), **zen(20)**, or(50), ds(60), cline(900) | **go(5)**, ng(10), or(50), ds(60), cline(900) |
| `deepseek-v4-flash` | ng(10), **zen(20)**, hf(30), or(50), ds(60), cline(900) | **go(5)**, ng(10), hf(30), or(50), ds(60), cline(900) |
| `minimax-m3-free` | ng(10), **zen(20)**, or(50), cline(900) | ng(10), or(50), cline(900)  *(zen removed; nanogpt-first unchanged)* |

`cost_rank` changes applied (via `/charon/models`, identity preserved): `glm-5.2-go` 1000→5, `kimi-k2.6-go` 1000→5, `deepseek-v4-pro-go` 40→5, `deepseek-v4-flash-go` 1000→5. The 4 `-go` legs were **not members of any pool before**, so re-ranking them has **no side-effect on other pools** (verified). No other leg ranks touched.

---

## Probe results (non-streaming /v1/chat/completions, Bearer token, max_tokens:1, unique user= per call)

| Pool | BEFORE prov / choices | AFTER prov / choices / downgrade |
|---|---|---|
| `glm-5.2` | nanogpt / YES | **opencode-go / YES** / downgrade-header (false-flag) |
| `kimi-k2.6` | nanogpt / YES | **opencode-go / YES** / downgrade-header (false-flag) |
| `deepseek-v4-pro` | nanogpt / YES | **opencode-go / YES** / none |
| `deepseek-v4-flash` | nanogpt / YES | **opencode-go / YES** / none |
| `minimax-m3-free` | nanogpt / YES | **nanogpt / YES** / none *(no opencode-go leg)* |

All AFTER: **HTTP 200, top-level `choices` present, 0 failovers.** PASS.

### Downgrade-header caveat (glm-5.2 + kimi-k2.6) — NOT a failure
opencode-go echoes a case/namespace-variant model id on glm-5.2 and kimi-k2.6, which `_normalize_model_id` (proxy.py) mis-reads as a "served a different model than requested" downgrade — the **same false-flag bug** that mis-scores neuralwatt (documented in `provider-cost-rationalization.md` Q3). It is cosmetic here: the response is a valid HTTP 200 with correct top-level `choices`, and it does **NOT** trigger failover because `failover_on_downgrade` is unset in `/data/gateway.json` (default **False**, forwarder.py:286). So opencode-go **is** served as the primary leg. If that toggle is ever set True, glm-5.2/kimi-k2.6 would false-fail over to nanogpt — fix the normalize bug first. deepseek-v4-pro/flash have no downgrade.

---

## opencode-zen: DEACTIVATED but RETAINED (confirmed from disk)
- **Provider entry retained:** `providers.json` still has `opencode-zen` → `{key_env: OPENCODE_ZEN_KEY, base_url: https://opencode.ai/zen/v1}`. Not deleted.
- **Catalog entries retained:** `models.json` still has `glm-5.2`, `kimi-k2.6`, `deepseek-v4-pro`, `deepseek-v4-flash`, `minimax-m3-free` with `provider=opencode-zen`. Not deleted.
- **Removed from active routing:** the zen bare-id is **no longer a member** of any of the 5 pools (verified on disk). It is therefore not exercised by the gateway.
- **Out-of-scope note (flagged, not touched):** the `big-pickle` pool still lists a zen bare-id member (`big-pickle`, rank 1000, behind `big-pickle-go`). That pool is outside the operator's named 5 and was left as-is. If a full zen purge is wanted, that leg remains.

---

## Persistence (STEP 5)
Verified by reading `/data/pools.json` and `/data/models.json` **directly from disk** after the change — member lists show go-added/zen-removed and the 4 `-go` legs read `cost_rank=5`, `provider=opencode-go`. The setup-API persists via `config._save()` to `/data` (CHARON_HOME) and hot-reloads live routes via `apply_routes()` under the routing lock (no restart).

---

## ROLLBACK (ready)
Primary — restores all three files from the pre-change backups and hot-reloads (no restart):
```
bash /home/stack/charon-private/scratch/rollback-routing-opencode-go.sh
```
Manual disk-level fallback (then any setup-API write hot-reloads):
```
ssh -i ~/.ssh/4lom stack@10.0.1.60 "docker exec charon-gateway-1 sh -c 'cd /data && for f in pools models providers; do cp -p \$f.json.bak-opencode-20260710T010620Z \$f.json; done'"
```
Backup timestamp: **20260710T010620Z**.

## Verdict
**PASS** — 4/5 pools (glm-5.2, kimi-k2.6, deepseek-v4-pro, deepseek-v4-flash) resolve to opencode-go (flat $0-marginal) with top-level `choices`; minimax-m3-free stays nanogpt-first (opencode-go does not serve it); nanogpt is the immediate fallback everywhere; opencode-zen removed from active routing but retained as provider + catalog; cline-pass stays last spill; changes persisted to /data; rollback ready. Flagged: the glm-5.2/kimi-k2.6 false-downgrade header (cosmetic, served, non-failing under default toggle) and the out-of-scope big-pickle zen leg.
