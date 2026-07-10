# GUI-API-SURFACE — can a static Svelte admin GUI run fully on Charon's current API?

Read-only investigation. Date: 2026-07-05. Product repo: `/home/stack/code/charon`
(gateway proxy: `src/charon/proxy_server.py` + `src/charon/gateway.py` +
`src/charon/config.py`). No product code touched.

---

## 1. API surface (gateway console, `_ProxyHandler._handle()`)

All routes are served by the SAME stdlib `http.server` process as the OpenAI-compatible
proxy (`/v1/*`). Token gate (`srv.token`) covers everything when set; `Authorization:
Bearer`, `?token=`, or `charon_token` cookie all satisfy it (`_authorized()`,
`proxy_server.py:433`).

| Method | Path | What it does | Read/Mutate |
|---|---|---|---|
| GET | `/v1/models`, `/models` | aggregated model list (ids + capability meta) | read |
| GET | `/charon` or `/` | HTML console (polls `/charon/status`) | read |
| GET | `/charon/status` | JSON: pools, per-provider stats+cooldown, cumulative usage (tokens/cost), last-50 failover events, build sha (`status_snapshot()`, `proxy_server.py:1143`) | read |
| GET | `/charon/setup` | HTML setup page | read |
| GET | `/charon/config` | JSON: `config.summary()` — providers (key_set bool, never the key), models, pools, unknown-pricing list, fallback providers, fallback pricing, failover-chain health | read |
| GET | `/charon/work` (`?json=1`) | JSON/HTML: orchestrator work-unit runs (status, checks, tokens, cost, lkg) via `console_work.gather_runs()` | read |
| POST | `/charon/providers` | add/edit a provider; validates the key with a live probe before persisting | mutate |
| POST | `/charon/models` | add/edit a model (preserves existing meta on re-add) | mutate |
| POST | `/charon/models/import` | bulk-import a provider's model catalog | mutate |
| POST | `/charon/pools` | create/edit a failover pool (ordered member list) | mutate |
| POST | `/charon/tiers` | set canonical tier order/members/aliases (low/med/high) | mutate |
| POST | `/charon/fallback` | set global fallback provider order | mutate |
| POST | `/charon/enable`, `/charon/disable` | toggle a model | mutate |
| POST | `/charon/remove` | remove a provider/model/pool by `{kind,name}` (no real HTTP DELETE verb is used anywhere — POST-as-delete is the house style) | mutate |

Writes are CSRF-guarded (Origin/Sec-Fetch-Site must be same-origin) on top of the token
gate — safe for a same-origin static bundle's `fetch()` calls.

Separate surface, NOT part of the gateway console (different process/product mode):
`src/charon/service/app.py` (FastAPI, "Mode B") — `/healthz`, `POST/GET /v1/runs`,
`GET /v1/runs/{task_id}`, `GET /v1/config`, `GET /` (its own read-only Ledger dashboard).
This is the task-orchestrator's HTTP surface, token-gated separately
(`CHARON_SERVICE_TOKEN`) — irrelevant to the gateway admin GUI unless the GUI is meant
to also front the orchestrator.

---

## 2. Coverage vs. what an admin GUI needs

| Need | Status | Notes |
|---|---|---|
| List providers | REACHABLE | `GET /charon/config` → `providers` (key_set bool only) |
| Add/edit provider | REACHABLE | `POST /charon/providers` (live key probe) |
| Remove provider | REACHABLE | `POST /charon/remove {kind:"provider"}` |
| List models | REACHABLE | `GET /charon/config` → `models` |
| Add/edit/import/enable/disable/remove model | REACHABLE | full set of POST actions above |
| List pools + view routing/pool order | REACHABLE | `GET /charon/config` (`pools`) and `GET /charon/status` (`pools`, live chain) |
| Add/edit pool | REACHABLE | `POST /charon/pools` |
| **View current tier config** (order/members/aliases) | **MISSING** | `set_tiers`/`load_tiers` exist in `config.py`, and `POST /charon/tiers` writes them, but `config.summary()` never returns `load_tiers()` output. The setup HTML's own "Tiers" panel is write-only — it can't prefill current tiers either. Aliases (e.g. `opus=high`) aren't exposed anywhere. |
| Metrics/usage/cost (cumulative) | REACHABLE | `GET /charon/status` → `usage.{tokens_in,tokens_out,cost_usd}`, per-provider `served/failed/errors/cost/last_status` |
| **View/set spend cap (budget limit + remaining)** | **MISSING** | `SpendLimiter` is constructed from CLI/env at gateway start (`gateway.py:343`) and enforces the cap per-request, but `status_snapshot()` never surfaces the configured limit or `remaining()`, and there's no POST action to change it. GUI can show money spent so far, not the ceiling or headroom. |
| Live request status/logs (work units) | REACHABLE (task-level) | `GET /charon/work` covers orchestrator work-unit runs (status/checks/tokens/cost), not individual `/v1/chat/completions` calls |
| Recent failovers (event feed) | REACHABLE | `GET /charon/status` → `recent_failovers` (last 50) |
| Provider health (cooldown state) | REACHABLE | `GET /charon/status` → `cooldown_seconds` per provider label |
| **Provider real account balance/credits** | **MISSING (and arguably out of scope)** | no ongoing balance check exists; `validate_provider_key` only probes at add-time |
| Prometheus-style `/metrics` scrape | MISSING but not needed by a GUI | `Observability.get_metrics()` exists in `observability.py` but is never wired to an HTTP route — irrelevant to a GUI since `/charon/status` already gives the same numbers in JSON |
| Per-provider proactive quota tracker (RFL-1) | NOT WIRED | `src/charon/quota.py` (commit `e06b193`) is a standalone module+tests only — not called from `gateway.py`/`proxy_server.py`, no data reaches any endpoint yet |

**Concrete gap list — 2 new endpoints needed for full admin-GUI parity:**
1. Expose `config.load_tiers()` — either add a `tiers` key to `GET /charon/config`'s
   response, or a dedicated `GET /charon/tiers` — so the Tiers panel can show/prefill
   current state (order, members, aliases).
2. Expose the spend cap — add `spend_limit` (configured ceiling) and `spend_remaining`
   to `status_snapshot()` (read), and a `POST /charon/spend-limit` action in
   `make_setup_handler()` (write) so the GUI can view and adjust the budget cap without
   restarting the process with a new CLI flag/env var.

Everything else a standard admin dashboard needs (CRUD on providers/models/pools,
routing view, cost/usage, failover events, provider cooldown) is already reachable
through the existing JSON API.

---

## 3. Current GUI

Lives entirely inline inside `src/charon/proxy_server.py` as three Python string
constants, served as `text/html` by the same handler that serves the API (no
templates/static dir, no build step, zero external assets/CDN calls):

- `_CONSOLE_HTML` (~line 83) — served at `GET /` or `GET /charon`. Dark dashboard:
  usage summary, providers table (served/failed/errors/cost/cooldown), pools table
  (with tier tag), recent-failovers feed. Polls `/charon/status` every 2s via vanilla
  JS `fetch`.
- `_SETUP_HTML` (~line 184) — served at `GET /charon/setup`. Forms to add a provider
  (with datalist of presets), add a model / bulk-import a provider's catalog, create a
  pool, set tiers, set global fallback. Posts JSON to the `/charon/*` write endpoints
  above; renders "Current config" from `GET /charon/config`.
- `_WORK_HTML` (~line 137) — served at `GET /charon/work`. Read-only table of
  orchestrator work-unit runs, polling `/charon/work?json=1` every 5s.

All three are self-contained single-file HTML+CSS+vanilla-JS (dark theme, `#0b0e14`
background) — no framework, no bundler. This is the "barebones GUI" the ticket is
meant to replace/upgrade with a proper static Svelte bundle.

---

## 4. CLIENT-CONNECT-GUI ticket + AUTH-GUI-DESIGN

- `/home/stack/charon-private/fleet/board/CLIENT-CONNECT-GUI.md` is a thin, PARKED
  backlog stub — "add cline + continue to the connect registry" (`src/charon/connect.py`,
  `tests/test_connect_gui.py`). It is about the **client-connection-string registry**
  (wiring external agents like opencode/cline/continue to point at the gateway), NOT
  the admin dashboard itself. No admin-GUI spec lives here.
- `/home/stack/charon-private/fleet/AUTH-GUI-DESIGN.md` (2026-07-03, design-only, DTC'd)
  is the relevant spec for GUI auth. Recommends **"TOFU session, token is the
  credential"** (Option C): the existing gateway token stays the sole `/v1/*` API
  credential, unchanged; `/charon/*` gets a friendly `/charon/login` page (paste the
  token once) that exchanges it for a durable **signed** `charon_sess` HttpOnly cookie
  (HMAC-SHA256, 30-day sliding expiry, separate `CHARON_SESSION_KEY` secret) — replacing
  today's raw-token-in-cookie. A `charon login` CLI prints a click-once pre-authed URL.
  Session cookie authorizes `/charon/*` ONLY, never `/v1/*`. Ticket-ready as `GUI-AUTH-1`
  with 10 acceptance criteria and a full test plan — **none of it is built yet**:
  confirmed no `/charon/login`, `/charon/logout`, `_valid_session`, or `charon_sess`
  exist anywhere in `proxy_server.py` today.

---

## 5. Static feasibility verdict

**Yes, with 2 new endpoints** for full parity (tiers read, spend-limit read/write —
§2 above). Everything else a static bundle needs is already there:

- The write endpoints (`POST /charon/{providers,models,...}`) already do Origin/
  Sec-Fetch-Site CSRF checks scoped to same-origin — exactly the posture a
  same-origin static bundle served by Charon itself gets for free (no CORS needed).
- `GET /charon/config` + `GET /charon/status` + `GET /charon/work` together already
  provide everything for list/view screens.
- The one thing that's genuinely a build-out, not just missing polish, is **tiers
  round-tripping** (can write but not read back) and **spend-cap visibility/control**
  (can't see or change the ceiling from the GUI at all).

**Auth for a static page today (works NOW, no new endpoint required):** the existing
mechanism already supports a JS single-page app cleanly — store the token (entered
once) and send it as `Authorization: Bearer <token>` on every `fetch()`, exactly like
any other API client; or land once via `?token=` and rely on the existing (currently
raw-token) `charon_token` cookie for subsequent page loads. This is functionally
sufficient to ship a static Svelte GUI TODAY without waiting on GUI-AUTH-1.

**Auth, done properly (per AUTH-GUI-DESIGN, not yet built):** implement `GUI-AUTH-1` —
`/charon/login` (POST token → signed `charon_sess` HttpOnly cookie, 30-day sliding
expiry, `CHARON_SESSION_KEY` HMAC) and `/charon/logout`. This removes the raw token
from the cookie jar and gives a "paste once, never again" flow instead of a bearer
token the SPA must hold in JS-reachable storage. Recommended before shipping the
static GUI as the default/primary way operators manage Charon, since a token sitting in
`localStorage`/JS-held state is a materially worse XSS blast radius than an HttpOnly
signed session cookie the JS never touches.

**Bottom line:** the static GUI can be built and be FULLY functional against the
current API for provider/model/pool CRUD, routing view, and usage/failover
observability. Two small read/write endpoints (tiers, spend-limit) close the only
functional gaps. Auth is not a blocker (token-as-bearer works now); GUI-AUTH-1 is a
recommended hardening/UX follow-up, not a prerequisite.
