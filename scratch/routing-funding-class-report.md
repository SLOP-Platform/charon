# Funding-class routing reorder — live gateway (4-lom 10.0.1.60)

- **Date:** 2026-07-10 (UTC)
- **Host/container:** `10.0.1.60` / `charon-gateway-1` (image healthy, 10h uptime). Config in `/data`.
- **Method:** SANCTIONED setup-API (`POST http://127.0.0.1:8080/charon/<action>?token=…`, validates + hot-reloads + persists to /data). **No image redeploy, no source edit, no restart, no commit.**
- **APPLIED: YES.** All 5 pools now drain flat-fee-first; envelope defused; rollback ready.

---

## Mechanism discovered (important)
Pool failover order is **NOT** the pool members-list order. `gateway._build_routes_and_pools` (gateway.py:168) **re-sorts every pool by `(not free, cost_rank)`**; the members list only breaks ties. So the funding-class reorder was done by setting each leg's **`cost_rank`** via the `/charon/models` setup-API action (27 legs), plus setting the members list via `/charon/pools` (mirrors the rank order for clarity/ties).

**cost_rank scheme (funding class → rank):**
`10` nanogpt (flat $0-marginal) · `20` opencode-zen (class-1 per operator) · `30` huggingface (free/PRO, near-front) · `50` openrouter (finite prepaid) · `55` neuralwatt (finite prepaid, KEPT ENABLED) · `60` deepseek (PAYG) · `900` cline-pass (spill, last).

---

## Backups (STEP 1 — before any change)
In-container, timestamped `bak-routing-20260710T001233Z`:
- `/data/pools.json.bak-routing-20260710T001233Z`
- `/data/models.json.bak-routing-20260710T001233Z`  ← models.json backed up too (cost_ranks were changed)
- `/data/providers.json.bak-routing-20260710T001233Z`

## Persistence (STEP 5)
Verified by reading `/data/pools.json` and `/data/models.json` **directly from disk** after the change — they reflect the new members + cost_ranks. The setup-API persists via `config._save()` to `/data` (CHARON_HOME) and hot-reloads the live routes via `apply_routes()` under the routing lock (no restart).

---

## Per-pool BEFORE → AFTER (compiled failover order)

| Pool | BEFORE (effective order) | AFTER (effective order) |
|---|---|---|
| `glm-5.2` | **cline**, ng, nw, or, hf | **ng**, opencode-zen, hf, or, nw, **cline(last)** |
| `kimi-k2.6` | **cline**, ng, nw, or, hf | **ng**, opencode-zen, hf, or, nw, **cline(last)** |
| `deepseek-v4-pro` | **cline**, ng, ds, or | **ng**, opencode-zen, or, ds, **cline(last)** |
| `deepseek-v4-flash` | **cline**, ds, ng, or, hf | **ng**, opencode-zen, hf, or, ds, **cline(last)** |
| `minimax-m3-free` | **cline**, ng, or | **ng**, opencode-zen, or, **cline(last)** |

Provider legend: ng=nanogpt, opencode-zen (added), hf=huggingface, or=openrouter, nw=neuralwatt, ds=deepseek, cline=cline-pass.
Note: the operator named pool `minimax-m3` — no such pool exists; the live pool is **`minimax-m3-free`** (used).

## Probe results (non-streaming, real /v1/chat/completions, max_tokens:1, unique user= per call)

| Pool | BEFORE provider / choices | AFTER provider / choices / served |
|---|---|---|
| `glm-5.2` | cline-pass / **no** (`{data,success}`) | **nanogpt / YES** / `zai-org/glm-5.2` |
| `kimi-k2.6` | cline-pass / **no** | **nanogpt / YES** / `moonshotai/kimi-k2.6` |
| `deepseek-v4-pro` | cline-pass / **no** | **nanogpt / YES** / `deepseek/deepseek-v4-pro` |
| `deepseek-v4-flash` | cline-pass / **no** | **nanogpt / YES** / `deepseek/deepseek-v4-flash` |
| `minimax-m3-free` | cline-pass / **no** | **nanogpt / YES** / `minimax/minimax-m3` |

All 5 AFTER: HTTP 200, `X-Charon-Provider=nanogpt`, top-level `choices` present, 0 failovers, no downgrade. **Cline's broken `{"data","success"}` non-streaming envelope is defused** (it is now the last spill leg, no longer served on the primary path). PASS.

---

## opencode provider identification (FLAGGED AMBIGUITY)
- **Used `opencode-zen`** (the task's default when uncertain; audit `provider-cost-rationalization.md` calls it "prepaid ~$10, wired-into-no-pool").
- **AMBIGUITY — operator premise unverified:** the audit describes opencode-zen as **prepaid ~$10 (finite balance via `balance.py:150`)**, NOT confirmed as a **flat $10/mo** subscription. If it is finite-prepaid, it arguably belongs in **class 2** (drain before PAYG), not class 1. The other opencode provider `opencode-go` serves 4 of the 5 models (NOT minimax-m3) via distinct `-go` ids; its cost is unlabeled in the audit.
- **How it was wired:** opencode-zen serves all 5 models via its existing **bare-id catalog entries** (`glm-5.2`, `kimi-k2.6`, `deepseek-v4-pro`, `deepseek-v4-flash`, `minimax-m3-free`) — these ids collide with the pool names but this is **functionally safe** (traced in gateway/proxy_server: pool members resolve through the `routes` dict; `chain_for` checks `pools` first; no recursion). No new fake legs invented.
- **Placement caveat:** opencode-zen is at rank **20 = SECOND**, behind nanogpt (rank 10). So the AFTER probe resolves to **nanogpt, not opencode-zen** — the opencode-zen leg is present but **not independently exercised** by these probes (nanogpt shadows it while up). If the operator wants opencode-zen **drained first**, flip the ranks (opencode-zen→10, nanogpt→20). If they want it verified end-to-end through the gateway, temporarily demote nanogpt and re-probe.

## neuralwatt (KEPT ENABLED — reversal honored)
- **ENABLED and present** in `glm-5.2` and `kimi-k2.6` pools (rank 55). Provider `neuralwatt` intact in `providers.json`. Not disabled.
- **BUG-BLOCKER (ordered anyway, flagged):** neuralwatt reads **0/4 = FALSE downgrade** — `_normalize_model_id` (proxy.py:247) is case/quant-sensitive and mis-scores its `Kimi-K2.6` / `GLM-5.2-FP8` echoes as pseudo-success (failures). It **will not effectively drain until that fix lands**. Ordered in class 2 as requested.

## openrouter (ordered, flagged)
- rank 50 (finite prepaid, ~$9.90 credit). Known **flaky 1/10**. Ordered anyway per the class rule.

## SIDE-EFFECT on the `auto` pool (FLAGGED)
`cost_rank` is per-model/global. Three legs are shared with `auto`: `deepseek-v4-pro-ng` (10, unchanged), `deepseek-v4-pro-ds` (20→**60**), `deepseek-v4-pro-or` (30→**50**). `auto`'s compiled order is now: `free-groq, free-cerebras, deepseek-v4-pro-ng, paid-neuralwatt-code, deepseek-v4-pro-or, deepseek-v4-pro-ds, minimax-m3-together`. **Benign** — free legs still lead and nanogpt is still the first paid leg; only the ds-vs-or ordering among paid legs shifted, consistent with the same funding-class intent. The operator named only the 5 pools; this is an unavoidable consequence of per-model cost_rank and is flagged for awareness.

## Fix applied mid-run
The minimax pool's cline member was first written with a nonexistent id (`minimax-m3-free-cline`) which the compiler silently drops; corrected to the real id **`minimax-m3-cline`** so the cline spill leg is preserved (now last, rank 900). Verified.

---

## ROLLBACK (ready)
Primary — restores all three files from the pre-change backups and hot-reloads (no restart):
```
bash /home/stack/charon-private/scratch/rollback-routing-funding-class.sh
```
Manual disk-level fallback (then any setup-API write hot-reloads):
```
ssh -i ~/.ssh/4lom stack@10.0.1.60 "docker exec charon-gateway-1 sh -c 'cd /data && for f in pools models providers; do cp -p \$f.json.bak-routing-20260710T001233Z \$f.json; done'"
```
Backup timestamp: **20260710T001233Z**.

## Verdict
PASS — all 5 pools resolve to a flat-fee provider (nanogpt) with top-level `choices`; cline-pass demoted to last; neuralwatt kept enabled; opencode-zen wired as class-1 (2nd) with the flat-vs-prepaid ambiguity flagged; changes persisted to /data; rollback ready.
