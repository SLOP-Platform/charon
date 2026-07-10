# Retire dead model/pool `gpt-5.3-codex-spark` — 4-LOM

Date: 2026-07-07 (session clock 2026-07-08 UTC crossing during the run)
Refs: `fleet/scratch/zen-remove-report.md` §"Skipped (zen-only)", `fleet/POOLS-EDIT-PLAN.md` §5
Container: `charon-gateway-1` (`ghcr.io/slop-platform/charon:v0.3.6`), healthy throughout,
**never restarted** (uptime climbed monotonically across the whole operation, confirmed
`Up 3 hours (healthy)` before and after).

## Scope

`gpt-5.3-codex-spark` was one of the 2 zen-only pools flagged (not removed) by the
recent zen-family-removal pass, because it has no non-zen provider. Confirmed dead:
its only providers are opencode-zen (`opencode-zen`, `opencode-go`), which 401 on
the depleted/unfunded account (probe returns 503 `all_providers_exhausted`). Task:
fully retire it (pool + model entries). `big-pickle` is structurally identical
(zen-only) but works free (200, cost 0) — explicitly out of scope, left untouched.

## 1. Backup

Off-host copy at `/home/stack/backups/charon-4lom-spark-retire-1783475048/`:
`models.json` (26540 bytes, 201 keys), `pools.json` (3969 bytes, 50 keys),
`providers.json` (375 bytes, 4 keys). All verified `json.load`-parseable and
non-empty before any writes. In-container timestamped `.bak` copies also left in
`/data/{models,pools,providers}.json.1783475048.bak`.

## 2. Re-confirmation (live, immediately before removal)

```
gpt-5.3-codex-spark pool: ['gpt-5.3-codex-spark', 'gpt-5.3-codex-spark-go']
big-pickle pool:          ['big-pickle', 'big-pickle-go']

models.json:
  gpt-5.3-codex-spark:    {free: False, cost_rank: 1000, provider: opencode-zen}
  gpt-5.3-codex-spark-go: {free: False, cost_rank: 1000, provider: opencode-go, upstream_model: gpt-5.3-codex-spark}
```

Pool has exactly 2 members, both zen-family (`opencode-zen` + its `opencode-go`
sibling), no non-zen alternative present. Matches the "confirmed dead, no working
alternative" premise — proceeded. (`big-pickle` was inspected in the same pass and
left completely alone, per scope.)

## 3. Apply mechanism

Setup API, same pattern as prior sessions: `POST /charon/remove {"kind": ..., "name": ...}`,
which deletes the entry from the relevant JSON file and hot-reloads
(`apply_to_env → load_config → apply_routes`), no restart. Three calls, all `HTTP 200 {"ok": true}`:

```
POST /charon/remove {"kind":"pool",  "name":"gpt-5.3-codex-spark"}     -> {"ok": true}
POST /charon/remove {"kind":"model", "name":"gpt-5.3-codex-spark"}     -> {"ok": true}
POST /charon/remove {"kind":"model", "name":"gpt-5.3-codex-spark-go"}  -> {"ok": true}
```

Touched only this id — no other pool or model entry was written.

## 4. Verification

- **Pool count: 50 → 49** (decremented by exactly 1). `gpt-5.3-codex-spark` absent
  from `/data/pools.json`. `big-pickle` pool unchanged: `['big-pickle', 'big-pickle-go']`.
- **Model count: 201 → 199** (both `gpt-5.3-codex-spark` and `-go` removed).
  `big-pickle` / `big-pickle-go` model defs byte-identical to before.
- **`GET /v1/models`**: served count 199, no id containing `spark` present,
  `big-pickle` still present.
- **Full before/after diff** of `pools.json` and `models.json` (off-host backup vs.
  live post-apply): `removed pool ids: {'gpt-5.3-codex-spark'}`, `added pool ids: {}`,
  0 other pools with changed membership. `removed model ids:
  {'gpt-5.3-codex-spark', 'gpt-5.3-codex-spark-go'}`, `added model ids: {}`, 0 other
  models with changed definitions. Confirms the change was surgical — nothing else
  touched.
- Container never restarted (uptime monotonic across the whole operation).

## 5. Health probes (live chat completions)

| Model | HTTP | Result |
|---|---|---|
| `big-pickle` | 200 | served by opencode-zen, `"cost":"0"` — confirms it still works free, untouched by this change |
| `gpt-5.4` (unrelated model, sanity check) | 200 | served by NanoGPT (`openai/gpt-5.4`), `"pong"` |

## 6. Mirror regen

`~/.config/opencode/regen-charon-models.sh` (run locally, pulls live from
`GET /v1/models` on the gateway — not run inside the container):

```
backed up -> /home/stack/.config/opencode/opencode.json.bak-20260707-184649
curated: 30 ids (charon-full removed, opencode-zen disabled)
OK: /home/stack/.config/opencode/opencode.json is valid JSON
```

## Summary

- `gpt-5.3-codex-spark` pool + both model entries (`gpt-5.3-codex-spark`,
  `gpt-5.3-codex-spark-go`) fully removed from the live gateway via the setup API.
- `big-pickle` pool and model entries confirmed **untouched** and **still working**
  (200, cost 0) — explicitly left alone per scope.
- 0 failures, 0 unrelated pools/models touched (verified by full diff), pool count
  -1, model count -2 exactly as expected, container never restarted, unrelated
  model (`gpt-5.4`) health-probed 200, local opencode.json mirror refreshed.
- Backup: `/home/stack/backups/charon-4lom-spark-retire-1783475048/` (off-host) +
  `/data/*.1783475048.bak` (in-container).
