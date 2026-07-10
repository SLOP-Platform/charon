# HuggingFace provider activation — 4-LOM live gateway

Date: 2026-07-08 (server clock). Container: `charon-gateway-1`. State dir: `/data`.

## 1. State assessment (prior interrupted run)

A previous session got partway through before being interrupted. Found on arrival:

- `secrets.json`: `HF_TOKEN` already present (added earlier — a self-made backup
  `secrets.json.bak-20260708T020103` sat right before it, confirming a
  backup-before-edit pattern was followed; diff showed only `HF_TOKEN` added, no
  other keys touched).
- `models.json`: 6 HF-routed model entries already added, each
  `{"free": false, "cost_rank": 1000, "provider": "huggingface", "upstream_model": "..."}`:
  `glm-5.2-hf`, `glm-5.1-hf`, `glm-5-hf`, `deepseek-v4-flash-hf`, `kimi-k2.6-hf`,
  `kimi-k2.5-hf`.
- `quality.json`: a `"huggingface"` provider-level entry with `calls: 2,
  successes: 2, reliability_score: 1.0` — the prior run had already made (at
  least) one successful real completion through HF before it was interrupted.
- `providers.json`: **no** explicit `huggingface` entry (see mechanism note
  below — not needed, and confirmed not needed for any of the other
  non-custom-base providers on this box either).
- `pools.json`: **zero** references to any `-hf` model id in any of the 49
  pools — this was the unfinished part of the prior run (backup-use fallback
  step never happened).
- No `regen-charon-models.sh` had been re-run since the HF models were added
  (opencode.json was stale re: HF).

Conclusion: activation + verification (steps 1–3 of the plan) were already
~done; only the backup-use fallback wiring (step 4) and the opencode regen
(step 5) were missing. Proceeded idempotently — no re-adding of `HF_TOKEN` or
duplicate model entries, only the pool-fallback + regen work.

## 2. Activation mechanism (from reading `providers.py` / `gateway.py` / `secrets.py`)

- A provider is "active" only when **both** hold: a `models.json` entry whose
  `"provider"` field names it, **and** its resolved `key_env` present in
  `os.environ`. Setting `HF_TOKEN` alone does nothing; a model entry with the
  key unset produces a route with a null key (fails auth upstream, but the
  route still exists) — `gateway.py:87-110` (`_route_from_spec`).
- `huggingface` is already a **built-in preset**
  (`src/charon/providers.py:88-91`: base `https://router.huggingface.co/v1`,
  key env `HF_TOKEN`), so **no `providers.json` override entry is required** —
  same pattern already used for `deepseek`/`groq`/`mistral`/`together`/`nanogpt`
  on this box (none of them have explicit `providers.json` entries either).
- Reload path used (no restart): `POST /charon/pools` (and any other
  `/charon/*` write) → `make_setup_handler`'s `_reload()`
  (`gateway.py:437-441`) → `secrets.apply_to_env()` (env refresh) →
  `load_config()` (re-read `/data/*.json`, recompile routes) →
  `server.apply_routes(...)` (`proxy_server.py:1100-1113`, atomic swap under
  the cooldown lock). This is the exact path exercised for the pool writes
  below.

## 3. Live verification (HTTP 200, real completion)

Backed up current (mid-run) state first — see §5. Then probed the gateway
directly (not just trusting the old quality.json counters):

```
POST http://10.0.1.60:8080/v1/chat/completions
model: kimi-k2.5-hf
-> HTTP 200
{"model":"moonshotai/Kimi-K2.5", "choices":[{"finish_reason":"length", ...}], "usage":{...}}
```

Confirmed: `HF_TOKEN` is valid and has inference permission; the HF router
successfully served `moonshotai/Kimi-K2.5` through the Charon gateway. No
token error to report.

## 4. Backup-use: HF added as LAST fallback to 6 pools

All 6 target pools (one per HF model added) already existed and got `-hf`
appended as the final (lowest-priority) member via `POST /charon/pools`
(full members list posted back, all returned HTTP 200, hot-reloaded, no
restart):

| pool | before | after |
|---|---|---|
| `glm-5.2` | ng, nw, or | ng, nw, or, **hf** |
| `glm-5.1` | ng, or | ng, or, **hf** |
| `glm-5` | ng, or | ng, or, **hf** |
| `deepseek-v4-flash` | ds, ng, or | ds, ng, or, **hf** |
| `kimi-k2.6` | ng, nw, or | ng, nw, or, **hf** |
| `kimi-k2.5` | ng, or | ng, or, **hf** |

Skipped: `big-pickle` (explicitly excluded per instructions). No other pool
had a HF-served model to map to id-for-id, so no further pools were touched.
Verified post-write by re-reading `/data/pools.json` on the container — all 6
match the table above.

## 5. Backups

- Fresh backup of the live (mid-run) state, taken **before** any further
  changes this session:
  `/home/stack/backups/charon-4lom-hf-activate-20260708T021032/`
  (`gateway.json`, `models.json`, `pools.json`, `providers.json`,
  `quality.json`, `secrets.json`, `spend.json`).
- A prior full backup from the interrupted run also exists (predates the
  `HF_TOKEN`/model additions, so it's the pre-HF baseline if a full revert is
  ever needed): `/home/stack/backups/charon-4lom-hf-activate-20260707T190311/`.

## 6. `regen-charon-models.sh`

Re-ran on the host: completed OK — `curated: 30 ids (charon-full removed,
opencode-zen disabled)`, `opencode.json is valid JSON`. Script made its own
backup of `opencode.json` before writing.

## No container restart

Every change was applied through the setup API's hot-reload path
(`POST /charon/pools` → `_reload()`); the container was never restarted.
