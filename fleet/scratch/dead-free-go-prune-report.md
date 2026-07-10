# Dead `*-free-go` model prune — 4-LOM live gateway — 2026-07-07

Executed the recommended prune from `reds-triage.md` §2 / apply pattern from
`POOLS-EDIT-PLAN.md` §5. LIVE PRODUCTION change on `charon-gateway-1`
(`ghcr.io/slop-platform/charon:v0.3.5`). No errors encountered — no STOP
triggered. Container was **not restarted** (confirmed `Up 21 hours` before
and after).

## 1. Backup

- Container-internal backup (Step 0 pattern): `docker exec charon-gateway-1
  cp -a {models,pools,providers}.json {same}.<epoch>.bak` inside `/data`.
  Timestamp `1783464790`.
- Off-host copies pulled to
  `/home/stack/backups/charon-4lom-dead-free-go-prune-1783464790/`:
  `models.json` (27298 bytes, 206 top-level keys), `pools.json` (5911 bytes,
  50 pools), `providers.json` (375 bytes, 4 providers).
- Verified non-empty and valid JSON via `json.load` + byte-size check before
  proceeding. `secrets.json` deliberately NOT pulled off-host (avoid
  unnecessary key handling) — the in-container `.bak` copy is untouched if
  ever needed.
- Also backed up the local `opencode.json` mirror before regen:
  `/home/stack/backups/opencode.json.pre-regen-<epoch>.bak` (the regen
  script also makes its own internal `.bak-<timestamp>` copy).

## 2. Pre-removal confirmation

Confirmed each of the 5 ids in the live `models.json` (`provider:
opencode-go`, mid-chain) and their pool membership — each pool had exactly
4 members with the `-go` entry sandwiched between siblings (matches the
triage's "LOW risk" claim exactly):

| pool | members before |
|---|---|
| `deepseek-v4-flash-free` | `[..free, ..free-go, ..free-ng, ..free-or]` |
| `mimo-v2.5-free` | `[..free, ..free-go, ..free-ng, ..free-or]` |
| `qwen3.6-plus-free` | `[..free, ..free-go, ..free-ng, ..free-or]` |
| `nemotron-3-ultra-free` | `[..free, ..free-go, ..free-ng, ..free-or]` |
| `north-mini-code-free` | `[..free, ..free-go, ..free-ng, ..free-or]` |

Note on mechanism: `config.remove(kind="model", name)` (src/charon/config.py:430)
only deletes the entry from `models.json`; it does **not** scrub pool
membership lists in `pools.json`. However `gateway._build_routes_and_pools`
(gateway.py:155) filters pool members at compile time to `m in routes` —
any member id no longer present in the model registry is silently dropped
from the compiled failover chain. So a `/charon/remove {kind:model}` call
alone is sufficient; no separate `/charon/pools` edit is needed, and the
raw `pools.json` file retaining the dangling id is expected/harmless.

## 3. Removal calls (all via `POST /charon/remove?token=...`, `{"kind":"model","name":"<id>"}`)

| id | response |
|---|---|
| `deepseek-v4-flash-free-go` | `{"ok": true}` |
| `mimo-v2.5-free-go` | `{"ok": true}` |
| `qwen3.6-plus-free-go` | `{"ok": true}` |
| `nemotron-3-ultra-free-go` | `{"ok": true}` |
| `north-mini-code-free-go` | `{"ok": true}` |

All 5 succeeded on the first call. Each POST hot-reloads the live server
(`_reload()` → `apply_to_env()` → `load_config()` → `apply_routes()`), no
downtime.

## 4. Post-removal verification

- `GET /v1/models`: served-model count dropped **206 → 201** (exactly -5);
  all 5 ids confirmed absent from the served list.
- Raw `/data/models.json` on container: 201 entries (matches).
- Raw `/data/pools.json`: still 50 pools (unchanged, as expected — no pools
  deleted), and (as predicted) the 5 affected pools still list the removed
  id in their raw JSON — this is the harmless dangling reference described
  above.
- **Compiled effective pool membership** (`gateway.load_config(state_dir=
  "/data")`, inspecting `c.pools[...]`) for all 5 affected pools: each
  went from 4 → 3 compiled members, with the `-go` entry gone and the
  other three siblings (bare/opencode-zen, `-ng`/nanogpt or equivalent,
  `-or`/openrouter) intact and correctly ordered. Example:
  `deepseek-v4-flash-free -> ['opencode-zen', 'deepseek/deepseek-v4-flash'
  (nanogpt), 'deepseek/deepseek-v4-flash' (openrouter)]`, len 3.
- **Gateway health probe**: live `POST /v1/chat/completions` through the
  affected pool `deepseek-v4-flash-free` (`max_tokens: 5`) returned
  **HTTP 200** with a valid completion body, cost `"0"` — confirms the pool
  still routes correctly end-to-end via a sibling after the prune.
- `GET /charon/status`: gateway responsive, pool table intact.
- `docker ps`: `charon-gateway-1` still `Up 21 hours (healthy)` — container
  was never restarted.

## 5. `regen-charon-models.sh` mirror refresh

Ran `~/.config/opencode/regen-charon-models.sh` (pulls live from
`GET http://10.0.1.60:8080/v1/models`).

- Before regen, the local `opencode.json` mirror was **stale**: `charon`
  curated list = 30 ids (already didn't include any of the 5 — they were
  never in the curated allowlist), `charon-full` = 207 ids and **did**
  include all 5 `-go` ids plus `minimax-m3-free-go`.
- After regen: `charon` = 30 ids (unchanged), `charon-full` = **201 ids**.
  All 5 pruned ids confirmed **absent** from both `charon` and
  `charon-full`.

### `minimax-m3-free-go` note (pre-existing triage question)

Checked directly against the **pre-removal** live-gateway backup
(`models.json` pulled before any of today's changes): `minimax-m3-free-go`
was **already absent** from the live gateway's registry — it was never
among the 206 models served before this session touched anything. The
triage note that flagged it as "still in `charon-full`" was observing a
**stale local opencode.json mirror** (last regenerated before whatever
prior session removed that id from the gateway), not actual live gateway
state. Today's regen naturally picked up the correct (already-clean)
live state as a side effect — no gateway-side action was needed or taken
for `minimax-m3-free-go`; it is confirmed gone from both lists now.

## 6. Scope discipline

- Did not restart the container.
- Did not touch any volume/delete anything.
- Did not edit `pools.json` directly (filtering at compile time already
  achieves the goal; out of scope per the recommended recipe).
- No other models/pools/providers touched.

## Outcome

Clean, verified, zero-downtime prune. All 5 dead `*-free-go` ids removed
from the live registry, their pools' remaining siblings confirmed intact
and serving traffic (200 via a sibling), local opencode.json mirror
refreshed and confirmed clean on both lists, and the dangling
`minimax-m3-free-go` mirror-staleness question resolved as already-clean
on the live side.
