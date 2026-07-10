# Reds triage — 2026-07-07

Scope: the 4 open Charon reds per HANDOFF-2026-07-06. All investigation only,
except item 1 which was genuinely verified and closed. No production edits,
no push, no repo commits.

## 1. stale-charon-token-env (P2) — CLOSED

**Verified GENUINELY resolved, not a non-interactive-shell false-green.**

Checked file *contents* directly (not `env` in this shell, which proves
nothing about interactive sessions):
- `~/.bashrc`: zero `CHARON`/IP references except `source
  ~/.charon-work-aliases.sh`.
- `~/.charon-work-aliases.sh` (the sourced file): sets
  `CHARON_GATEWAY_TOKEN="317d22ce..."` — a bare token string, no IP, no
  baseURL override.
- `~/.profile`: zero `CHARON`/IP references.
- `~/.bash_profile`, `~/.zshrc`: do not exist.
- The **only** file anywhere on disk containing `10.0.3.91` is
  `/home/stack/.config/opencode/opencode.json.proofbak` — a 351-byte
  one-off manual backup from Jun 27, not sourced by any shell startup file,
  not the active config, not read by opencode (`.proofbak` isn't a
  recognized extension). The live `opencode.json` (regenerated straight
  from the deployed gateway via `regen-charon-models.sh`) correctly points
  at `10.0.1.60`.

Conclusion: the red's own framing ("shell profile sets a stale token") was
never quite accurate — the stale IP lived only in an inert backup file, and
the token env var itself never carried an IP. `check_cmd` is legitimately
green in any shell, interactive or not.

**Action taken:** closed via
`preflight.sh close stale-charon-token-env --evidence "..."` (see reds.tsv).

---

## 2. dead-free-go-entries (P2) — READ-ONLY, needs gated decision

**Where they live:** confirmed these 5 ids (`deepseek-v4-flash-free-go`,
`mimo-v2.5-free-go`... — full names: `deepseek-v4-flash-free-go`,
`mimo-v2.5-free-go`, `qwen3.6-plus-free-go`, `nemotron-3-ultra-free-go`,
`north-mini-code-free-go`) do **not exist anywhere in the charon git repo**
(`git grep` / `git log -S` across all refs: zero hits). They exist only as
**live runtime state on 4-LOM's `/data` volume** (`models.json`/`pools.json`
under the deployed gateway's state dir), mutated exclusively via the
token-gated `/charon/{models,pools,remove}` setup API
(`src/charon/proxy_server.py:298` client-side JS calls `/charon/remove`
`{kind:'model', name}`; server handlers hot-reload via `apply_to_env()` →
`load_config()` → `apply_routes()`, per fleet/POOLS-EDIT-PLAN.md §5). This
is exactly how `minimax-m3-free-go` was removed previously (same API,
confirmed by the `/charon/remove` endpoint's existence and the
POOLS-EDIT-PLAN precedent) — **note:** the current `opencode.json` mirror
(regenerated live Jul 7) still lists `minimax-m3-free-go` under
`charon-full`, so either that removal only touched a subset (the `charon`
curated list, not `charon-full`) or it was re-added; worth the operator
double-checking which list it should be gone from.

**This is LIVE PRODUCTION config — not touched.**

**Recommended prune (for operator/manager to apply via the setup API,
following the POOLS-EDIT-PLAN.md §5 pattern: backup `/data/*.json` first,
then `POST /charon/remove {kind:"model", name:"<id>"}` for each of the 5,
verify via `GET /v1/models` that they're gone, then re-run
`regen-charon-models.sh` to refresh the opencode.json mirror):**

- `deepseek-v4-flash-free-go`
- `mimo-v2.5-free-go`
- `qwen3.6-plus-free-go`
- `nemotron-3-ultra-free-go`
- `north-mini-code-free-go`

**Risk / blast radius: LOW.** These are pool *members*, not primaries (e.g.
the `deepseek-v4-flash-free` pool is
`[groq-llama-3.1-8b, deepseek-v4-flash-free, deepseek-v4-flash-free-go,
deepseek-v4-flash-free-ng, deepseek-v4-flash-free-or]` — the `-go` entry
sits mid-chain with siblings on both sides). Confirmed via
`_is_unsupported_model` classification (`proxy.py`) that a 401 "not
supported" body already correctly fails over to the next pool member today
(same fix that closed `failover-401-not-classified`), so removing them is
**cosmetic/efficiency, not correctness** — it just stops each pool traversal
that reaches them from wasting one guaranteed-401 round-trip. No dropped
model becomes unreachable (their live siblings still serve the same slot).

---

## 3. cooldown-anchor-demotion (P2) — READ-ONLY, concrete fix recommended

**Root cause identified**, in `src/charon/proxy_server.py` +
`src/charon/proxy.py`:

- `_retry_after()` (`proxy.py:102`) parses the upstream `Retry-After` header
  verbatim (`int(float(v))`) with **no upper bound**.
- `set_cooldown()` (`proxy_server.py:1132`) uses that value **verbatim** as
  the cooldown duration: `secs = float(retry_after) if (retry_after and
  retry_after > 0) else self.default_cooldown` (default 60s otherwise) —
  again no clamp.
- `order_by_cooldown()` (`proxy_server.py:1123`) buckets strictly into
  "not currently cooled" (tried first) vs "cooled" (last resort), with
  **no notion of role** (anchor vs. any other provider) and **no ordering
  within the cooled bucket** by remaining time.
- Separately, a `dropped` (unsupported-model / 404) classification does
  **not** call `set_cooldown` at all (`proxy_server.py:810`, by design —
  it's model-level, not account-level) — so a provider that's persistently
  broken via 401-not-supported/404 never accumulates a cooldown and reads
  as permanently "fresh" to `order_by_cooldown`.

**Mechanism that produces the observed ~57min demotion:** NanoGPT (the
anchor) hit one failure whose response carried a large `Retry-After` (or
was classified as an exhausted/billing 429 with a long provider-reported
backoff, ~3420s ≈ 57min) → `set_cooldown` honored it verbatim → NanoGPT sits
in the "cooled" bucket for the full 57 minutes. Meanwhile OpenRouter, which
is *also* broken but via a code path that doesn't set cooldown (e.g. a
dropped/unsupported classification, or a cooldown that already expired
since nothing re-triggered it), reads as "fresh" and sorts ahead of the
still-cooling anchor. Net effect: the intended-primary anchor loses to a
provider that is actually just as broken but isn't currently *marked*
broken.

**Recommended fix (pick one, not mutually exclusive):**

1. **Clamp the retry_after-derived cooldown** to a sane ceiling (e.g.
   `min(secs, 120.0)` or a configurable `max_cooldown_s`) so one upstream-
   reported long backoff can never sideline a provider — anchor or not —
   for tens of minutes. Smallest, safest change; fixes the proximate cause.
2. **Order the cooled bucket by remaining cooldown time** (ascending)
   instead of leaving it in original/arbitrary order, so among cooled
   providers the one closest to recovering is preferred — reduces (but
   doesn't eliminate) the chance of picking a worse-off provider.
3. **Anchor-awareness in `order_by_cooldown`**: accept an optional
   "protected" provider id (the pool's designated anchor/primary) and only
   demote it behind cooled peers if *no* fresh peer exists — i.e. never
   let a merely-cooled anchor lose to another *equally-cooled-or-worse*
   provider that just happens not to be tracked as cooled. Bigger change,
   more precise, needs a way to identify "the anchor" per pool (cost_rank
   0? explicit flag?).

Recommend (1) as the immediate low-risk fix — it directly caps the
mechanism that produced the 57-minute demotion — with (2) as a natural
follow-on. (3) is a larger design change, worth its own ticket if the
operator wants stronger anchor guarantees.

No code changes made (proxy_server.py/proxy.py are repo files I could edit,
but this task was investigate + recommend only per the brief).

---

## 4. opencode-zen outage (triage) — READ-ONLY

**Status: largely self-healing already, via the `failover-401-not-classified`
fix (closed 2026-07-05).** opencode-zen's depletion shows as a 401 with an
"insufficient balance"-style body, which `_is_billing_error()` /
`_EXHAUSTION_BODY_PATTERNS` in `proxy.py` correctly classifies as
`exhausted=True` → `failover=True` → the live per-request loop in
`proxy_server.py` fails over to the next pool member **and** calls
`set_cooldown()` (60s default, no Retry-After from opencode-zen typically),
so repeat requests within that window skip it via `order_by_cooldown`.

**What's NOT yet fixed:** per `fleet/HANDOFF-2026-07-06.md`, opencode-zen
was the primary/first member of the `auto` pool (48× duplicated) — that was
already fixed by the `auto-pool-broken` red closure (rebuilt to 7 diverse
providers, verified 200 via groq, anchor NanoGPT). But `HANDOFF-2026-07-04.md`
records opencode-zen/`-go` as primary across a much larger set — **"cross-
account fallback across 47 pools: opencode-zen/go primary → deepseek /
nanogpt / neuralwatt / openrouter"** — and `HANDOFF-2026-07-06.md` flags it
explicitly as a **"NEW finding to triage... it still backs several pools;
worth its own investigation/ticket"**, not yet closed or even registered as
its own red in `reds.tsv` (it currently only appears as prose inside the
now-closed `auto-pool-broken` entry).

Balance is dashboard-only (no balance API per `SESSION-DRAIN-BALANCE.md`),
last known $2.99 → -0.04 (i.e., genuinely depleted, not a transient blip) —
this is not going to self-recover without an operator top-up.

**Risk if left alone:** functionally low (failover + cooldown cover it
correctly today) but **not zero-cost** — every pool where opencode-zen still
sits first/primary wastes one guaranteed-401 round-trip per cooldown window
(up to every ~60s under load) before reaching a working provider, adding
latency and log noise across potentially dozens of pools, not just `auto`.

**Recommendation:**
- Register this as its own red (e.g. `opencode-zen-primary-in-N-pools`,
  P2 — degraded/self-healing, not broken) rather than leaving it as
  buried prose in a closed red's evidence field, so it's tracked to
  closure.
- Same treatment as `auto` (already done): re-rank/demote opencode-zen to
  last-resort (or remove) across the remaining pools where it's still
  primary, via the same `/charon/pools` setup API + `/data` backup pattern
  documented in POOLS-EDIT-PLAN.md — **LIVE PROD, gated operator action**,
  did not touch it here.
- Lower urgency than `auto-pool-broken` was: no pool is fully broken (there
  are always working fallbacks), so this is a cleanup/latency item, not a
  P1.

---

## Summary for the manager gate

- **CLOSED (safe, verified):** `stale-charon-token-env` — genuinely green,
  evidence recorded in reds.tsv.
- **dead-free-go-entries:** confirmed LIVE-ONLY (4-LOM `/data`, setup API),
  low-risk cosmetic prune identified with exact removal list + apply
  recipe — needs operator/manager to run it, not done here.
- **cooldown-anchor-demotion:** root cause pinned to unclamped
  `Retry-After`-derived cooldown in `proxy_server.py:set_cooldown` +
  `proxy.py:_retry_after`; concrete minimal fix recommended (clamp to a
  ceiling) — needs a gated decision to implement + test, not done here.
- **opencode-zen outage:** mostly self-healing already (failover-401 fix
  covers it), but still primary in ~46 other pools beyond the fixed `auto`
  pool; recommend registering its own P2 red and applying the same
  demote/prune treatment via the live setup API — LIVE PROD, gated
  decision, not done here.
