# HF_TOKEN reload verification — 2026-07-08

## Verdict
**PROBLEM: reload cannot make the rotated HF_TOKEN live without a restart.**
This is a code-level limitation, confirmed by static analysis of the running
version (matches `/home/stack/code/charon` at the current commit), not a
config or scope error. No restart was performed (per instructions).

## Ground truth: how (re)load works
- `src/charon/gateway.py` `make_setup_handler._reload()` (line ~437) does, on
  every `/charon/{providers,models,models/import,pools,tiers,fallback,enable,
  disable,remove}` write:
  `secrets.apply_to_env()` → `load_config(state_dir=setup_dir)` →
  `server.apply_routes(...)`.
- `load_config` → `_route_from_spec` (gateway.py:104-106) bakes
  `api_key=os.environ.get(key_env)` into each `UpstreamRoute` **at reload
  time**, and that baked value is what's used per-request
  (proxy_server.py:547-548). So a reload *does* re-read `os.environ` fresh
  each time — routing is not the problem.
- The problem is `secrets.apply_to_env()` itself (`src/charon/secrets.py:90-97`):
  ```python
  def apply_to_env() -> None:
      for k, v in load_secrets().items():
          if _KEY_ENV_RE.match(k) and k not in _SENSITIVE_ENV:
              os.environ.setdefault(k, v)   # <-- only sets if ABSENT
  ```
  `os.environ.setdefault` is a no-op if the key is already present. The
  module docstring confirms the design intent: secrets are "loaded into the
  process environment **at gateway start**" — i.e. once. The `_reload()`
  call comment even says `# newly-stored keys → env so routes resolve`,
  scoping it to *new* keys, not *rotated* ones.
- Net effect: once `HF_TOKEN` was set in the gateway's `os.environ` at first
  HF activation, no later `apply_to_env()` call — no matter how it's
  triggered — can ever overwrite it with a new value from
  `/data/secrets.json`. Only a process restart (fresh `os.environ` from
  scratch) picks up a rotated value for a key that's already set.
- Server is single-process, multi-threaded (`GatewayProxyServer(ThreadingMixIn,
  HTTPServer)` — proxy_server.py:985), so there's no worker-recycling path
  that would incidentally pick up the new value either.

## What was done (live, 4-LOM, `charon-gateway-1`)
1. Confirmed no restart risk: container `Up 6 hours (healthy)`, gateway PID 1,
   cmdline `charon gateway --state-dir /data --host 0.0.0.0 --port 8080`.
2. Confirmed on-disk secret already rotated:
   `/data/secrets.json["HF_TOKEN"]` sha256[:10] = `242bc9a106` (fingerprint
   only — value never printed).
3. Confirmed `HF_TOKEN` is **not** a container-declared env var (absent from
   a fresh `docker exec ... os.environ` dump, and absent from `/proc/1/environ`)
   — it only exists inside PID 1's live Python `os.environ`, set once at
   original HF activation via `apply_to_env()`'s `setdefault`. (Note:
   `/proc/1/environ` reflects only the env passed at `execve()` time and does
   not reflect later in-process `os.environ`/`putenv` mutations on this
   kernel, so it can't be used to read the *current* in-memory value either
   way — this was a dead end for direct fingerprinting, consistent with the
   static-analysis conclusion above, not contradicting it.)
4. Triggered the benign, idempotent reload exactly as scoped: read
   `pools.json["kimi-k2.5"]` (`["kimi-k2.5-ng","kimi-k2.5-or","kimi-k2.5-hf"]`),
   then `POST /charon/pools` with that **exact unchanged** member list,
   authenticated with the container's own `CHARON_GATEWAY_TOKEN`.
   - Response: `200 {"ok": true}`.
   - Confirmed `pools.json["kimi-k2.5"]` identical before/after — zero config
     drift, no pool/model/membership changed.
5. Probed the HF-routed model post-reload:
   `POST /v1/chat/completions {"model":"kimi-k2.5-hf", ...}` →
   **HTTP 200**, `model: moonshotai/Kimi-K2.5`, valid `choices[]` shape.
   Per the task's own caveat, this 200 is **not proof** the new token loaded
   — the old token is still valid/unrevoked, so routing succeeds either way.
6. Fingerprint match check: **not obtainable** without a restart or a code
   change, for the reasons in §"Ground truth" — there is no safe,
   non-invasive way to read PID 1's live `os.environ["HF_TOKEN"]` from
   outside the process (no `gdb`/`py-spy`/`strace` in the container, and the
   product intentionally never exposes secret values or hashes via any
   `/charon/*` endpoint). Given the deterministic `setdefault` behavior,
   the answer is known without needing to read it: the in-memory value is
   still the OLD token.

## Bottom line
- The rotated `HF_TOKEN` (fingerprint `242bc9a106`) is correctly on disk.
- The benign-reload path requested (re-POST an unchanged pool) is safe and
  was executed with **zero config/pool/model changes** and **no restart**.
- It did **not** and **cannot** make the new token live, because
  `secrets.apply_to_env()` uses `os.environ.setdefault`, which is a
  structural no-op for any key already resident in the process env — this
  is true for *every* `/charon/*` write action, not just `pools`, since they
  all funnel through the same `_reload()`.
- **The only way to make the rotated HF_TOKEN take effect is a container
  restart** (out of scope for this task — not performed).
- Suggested follow-up (not done — code change, needs review/DTC): give
  `apply_to_env()` an optional "force" mode (or have `_reload()` explicitly
  refresh only the just-touched `key_env`) so provider-key rotation can be
  hot-applied without a restart. File as a ticket rather than hotfixing a
  live prod gateway.
