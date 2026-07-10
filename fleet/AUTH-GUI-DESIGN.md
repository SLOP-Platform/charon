# AUTH-GUI-DESIGN — friendly login for the Charon web GUI

Status: DESIGN (read-only investigation, no product code touched)
Date: 2026-07-03
Scope: make the `/charon/*` web console/setup GUI reachable without pasting
`?token=` into a URL, WITHOUT breaking the token as `/v1/*` API auth.
Product constraints: stdlib-only (`http.server`), ships standalone (no
fleet/SLOP dependency), home-network app (NOT enterprise).

---

## 1. How auth works TODAY

There is exactly **one secret** — `srv.token` — and it gates **everything**.

Resolution order (`gateway.py:232`, `gateway.py:167-177`, `cli.py:159`):
`--token` arg → gateway config file `gw.token` → `CHARON_GATEWAY_TOKEN` env
(env is populated from `secrets.json` via `secrets.apply_to_env()`).
`token=None` ⇒ ungated (only permitted on a loopback bind; a non-loopback bind
without a token is refused — `gateway.py:346` `GatewayBindRefused`, ADR-0005 D5/R8).

The gate lives in ONE place — `proxy_server.py:_handle()` line 525:

```python
if srv.token is not None and not self._authorized(srv.token):
    self._json(401, {"error": {"message": "missing or invalid bearer token"}})
    return
```

`_authorized()` (`proxy_server.py:403-420`) accepts the token from **any** of three
places, then does a constant-time `hmac.compare_digest`:
1. `Authorization: Bearer <token>` header  (machine clients)
2. `?token=<token>` query string           (browser URL)
3. `charon_token` cookie                    (browser, after first `?token=`)

There is **already a cookie mechanism** — but it stores the **raw token**:
`_maybe_set_token_cookie()` (`:422-428`) sets
`charon_token=<raw token>; HttpOnly; SameSite=Lax; Max-Age=900` (15 min) whenever a
request authed via `?token=`. So today's "session" is literally the secret itself,
short-lived, put in the browser jar.

Same gate covers BOTH surfaces — there is no separation:
- `/v1/*` OpenAI API (`/v1/chat/completions`, `/v1/models`) — machine clients.
- `/charon`, `/charon/status`, `/charon/setup`, `/charon/config`, `/charon/work`,
  and the `/charon/*` POST setup writes.

Existing defenses to preserve/reuse:
- **Anti-DNS-rebinding**: loopback binds reject a non-loopback `Host` header (`:517`).
- **CSRF/Origin guard on `/charon/*` writes**: `Origin` netloc must match `Host`;
  `Sec-Fetch-Site` must be `same-origin`/`none` (`:582-590`).
- **`?token=` never forwarded upstream**: upstream URL is path-only (`:487`) — the
  bearer can't leak into provider logs.

---

## 2. Blast radius — every consumer of the token (CRITICAL)

The gateway token is a **shared machine credential**, not just a GUI password.
Any GUI-login change MUST be **purely additive** and leave `/v1/*` Bearer auth
byte-for-byte unchanged. Consumers found:

| # | Consumer | How it uses the token | Break risk if we touch `/v1/*` |
|---|----------|----------------------|-------------------------------|
| 1 | **opencode** (operator's agent) | `connect.py` writes `apiKey: <token>` (or `{env:CHARON_GATEWAY_TOKEN}`) into the client's provider config (`connect.py:241,328`) | opencode can't reach any model |
| 2 | **Work engine / ACP** | `CHARON_GATEWAY_TOKEN` passed through `_ACP_KEY_PASSTHROUGH`; spawned `opencode acp` reads apiKey from `{env:CHARON_GATEWAY_TOKEN}` (docs/review-log/WORK-GATEWAY-WIRE.md) | the whole autonomous work path dies |
| 3 | **Any OpenAI-compatible LAN client** (Windows apps, curl) | `Authorization: Bearer <token>` (docs/docker.md:175) | every LAN client 401s |
| 4 | **`charon connect` / `discover_models`** | `GET /v1/models` with `Bearer` (`connect.py:52-69`) | client wiring/discovery fails |
| 5 | **Docker entrypoint / healthcheck / CI smoke** | refuses to start without `CHARON_GATEWAY_TOKEN`; healthcheck = `GET /v1/models -H "Authorization: Bearer …"` (docs/docker.md:60, RELEASE-SMOKE-FIX.md) | container marked unhealthy; CI red |
| 6 | **The GUI itself** | `?token=` → `charon_token` cookie (`proxy_server.py`) | this is the thing we're improving |
| 7 | **Startup banner** | prints `console: <url>?token=<token>` (`gateway.py:529`) | cosmetic; already flagged for masking (ATC-AUDIT) |

**Design invariant (non-negotiable):**
> The gateway token MUST keep working as the `/v1/*` Bearer credential, unchanged.
> The new GUI login is an **additional** way to authenticate `/charon/*` **only**.
> The token also remains a valid admin fallback for `/charon/*` (so headless recovery
> and existing `?token=` links keep working).

**Pending token rotation → secrets.json:** the token is moving out of ad-hoc env
into `secrets.json`. This is transparent to auth — it still resolves to `srv.token`
via `apply_to_env()`. Note `secrets.py:_SENSITIVE_ENV` (loader-hijack blocklist) does
NOT include `CHARON_GATEWAY_TOKEN`, so it loads normally. The new **session-signing
key** (below) rides in the same `secrets.json`, auto-generated on first start.

---

## 3. Options

### Option A — First-run password → login page → signed session cookie
A dedicated GUI password (separate from the token), stored as a salted hash
(`hashlib.scrypt`/`pbkdf2_hmac`, stdlib) in `secrets.json`. Login form POST →
HMAC-signed HttpOnly session cookie.

- **Pros:** the mental model home users expect (Jellyfin/Sonarr login box); GUI
  access can be granted without handing out the API token.
- **Cons:** a **second secret** to invent, store, and recover, for a **single user
  who already holds the token**. Headless first-run is awkward (where does the
  password get set on a container with no console?). "Forgot password" needs a CLI
  reset anyway. Redundant security: the token already gates the same box.

### Option B — LAN/localhost-trusted (RFC1918 no-auth)
No auth for private-IP clients; auth only for non-local — the Jellyfin/HA/Pi-hole
default.

- **Pros:** zero friction; familiar home-app default.
- **Cons:** **wrong blast radius for THIS app.** Charon holds real **provider API
  keys** and can **spend money**; the setup GUI can read/rotate keys and rewire
  routing. "Trust the LAN" = trust every IoT device, guest phone, and any web page a
  LAN browser visits (DNS-rebinding is only partly mitigated). That is a far bigger
  blast radius than a media server. It's also **inconsistent**: `/v1/*` already
  *refuses* to bind non-loopback without a token, so making `/charon/*` LAN-open
  contradicts the API posture. **Reject as default;** acceptable only as an explicit
  opt-in flag for someone who really wants it.

### Option C — TOFU / one-time token → durable signed session cookie
Paste the token **once** (or click a pre-authed link once); the server exchanges the
valid token for a **long-lived HMAC-signed session cookie**; never paste again.
This is essentially **what exists today, hardened** — the raw-token 15-min cookie
becomes a signed opaque session with a 30-day sliding lifetime, and the first contact
is a friendly form/redirect instead of a hand-edited URL.

- **Pros:** simplest; **no second secret**; no password-recovery problem (recovery =
  the token you already have, or rotate it); directly kills "pasting a token into a
  URL"; the token stays the single root credential.
- **Cons:** it's "token-in-a-form", not "username/password" — some users emotionally
  want a password box. (Mitigated by making the login field accept an optional
  password too, later.)

---

## 4. RECOMMENDATION — "TOFU session, token is the credential" (Option C core, A optional)

**Ship Option C as the core, with two friendly front doors and an OPTIONAL password
as a deferred phase.** Rationale (the outside-the-box call):

> For a **single home user**, a password is a *second* secret with *worse* recovery
> and *no* added security over the token they must already possess (machine clients
> require it; it can't be removed). The honest simplest-safe design is: **possess the
> token ⇒ you're in, and let the browser remember it** via a signed session cookie.
> A password only matters when you want to grant GUI access *without* granting the API
> token — a multi-user concern a solo home user doesn't have. So make the password
> **opt-in**, not mandatory.

Concretely:

1. **`/v1/*` is untouched.** Bearer-token gate stays exactly as-is (protects
   consumers 1-5 above).
2. **Friendly first contact for `/charon/*`:**
   - A **login page** at `/charon/login` (single field: "gateway token" — the thing
     they already have, pasted into a box **once**, not into the URL). This is the
     Jellyfin-shaped answer to the complaint.
   - A **`charon login` CLI** that prints a **click-once pre-authed URL**
     (`http://host:8080/charon?token=…`, token read from secrets.json). One click →
     server sets the session cookie and **302-redirects to `/charon`**, stripping the
     token from the address bar/history. Zero typing on the box that has a browser.
3. **Durable signed session cookie** replaces the raw-token cookie: `charon_sess`,
   HttpOnly, SameSite=Lax, ~30-day sliding expiry. The browser never again holds the
   raw token, and the operator never pastes it again.
4. **Token stays an admin fallback** for `/charon/*` (headless recovery; existing
   `?token=` links still work and now auto-upgrade to a cookie).
5. **Optional password = Phase 2:** `charon gui-password set` stores a scrypt hash;
   if set, the login field also accepts the password. Not required for v1.

Bind posture unchanged: keep the LAN bind the operator wants (already token-required
on non-loopback); document the SSH-tunnel/reverse-proxy path for anyone who wants TLS.

---

## 5. Implementation sketch (stdlib only)

### 5.1 Session key
New secret `CHARON_SESSION_KEY` (32 random bytes hex, `secrets.token_hex(32)`),
**generated on first gateway start if absent** and stored via `secrets.set_secret`
(0600, atomic — reuse the existing writer). It is **separate** from the gateway
token, so **rotating the token does NOT log the operator out** (good default).
Deliberate revocation = bump the session key (`charon logout --all`).

Add a tiny helper in `secrets.py`:
```python
def get_or_create(key_env: str, factory) -> str:
    v = load_secrets().get(key_env)
    if not v:
        v = factory(); set_secret(key_env, v)
    return v
```

### 5.2 Cookie format (opaque, signed, stdlib)
```
charon_sess = b64url(payload) + "." + b64url(HMAC_SHA256(session_key, b64url(payload)))
payload      = compact JSON: {"exp": <unix_ts>, "v": 1}
```
Verify: split on `.`, constant-time `hmac.compare_digest` the MAC, then check `exp`.
No PII, no username — for a single user the cookie just means "this browser proved it
held the token before `exp`". Sliding refresh: on each authorized GUI request within
the refresh window, re-issue with a new `exp`.
Attributes: `HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000` (30d). **No `Secure`** —
plain http on the LAN would drop it (see §7 tradeoff).

### 5.3 Dispatch hook (in `proxy_server.py:_handle`)
Refactor the single gate at `:525` into surface-aware handling. Compute `path_only`
first (already done at `:541`), then:

```
is_gui = path_only == "" or path_only == "/charon" or path_only.startswith("/charon/")

# public GUI routes (no auth):
if is_gui and GET and path_only == "/charon/login":   -> serve _LOGIN_HTML ; return
if is_gui and POST and path_only == "/charon/login":  -> validate + set cookie (below)
if is_gui and path_only == "/charon/logout":          -> clear cookie ; 302 /charon/login

# gated routes:
authed = (srv.token is None) or self._authorized(srv.token) \
         or (is_gui and self._valid_session())   # session cookie only counts for GUI
if not authed:
    if is_gui and GET:
        302 -> /charon/login          # browser sees a login page, not raw 401 JSON
    else:
        self._json(401, {...})        # /v1/* machine clients: unchanged 401
    return
```

- `_valid_session()` — parse+verify `charon_sess` per §5.2. **Session cookie
  authorizes `/charon/*` only**, never `/v1/*` (clean separation; keeps API auth = token).
- `_authorized()` continues to accept Bearer / `?token=` / (legacy) `charon_token`
  for one release, so old links + all machine clients keep working.

### 5.4 Login POST
```
POST /charon/login  (form-encoded: field "token" [or "password" if Phase 2])
  - reuse existing Origin/Sec-Fetch-Site CSRF guard (:582-590)
  - constant-time compare submitted value against srv.token
    (and/or scrypt-verify against stored gui-password hash if set)
  - on success: Set-Cookie charon_sess=<signed>; 302 -> /charon
  - on failure: 200 _LOGIN_HTML with an "invalid token" message (no timing leak)
```
The `?token=` path also mints `charon_sess` (replacing today's raw-token cookie) and
should 302 to strip the token from the URL — TOFU upgrade in one hop.

### 5.5 CLI (`cli.py`)
- `charon login` → resolve token from secrets, print
  `http://<host>:<port>/charon?token=<token>` (click-once). Optionally `--open`.
- `charon logout --all` → rotate `CHARON_SESSION_KEY` (invalidates all sessions).
- Phase 2: `charon gui-password set` / `charon gui-password reset` (scrypt hash in
  secrets.json).
- Update `gateway.py:529` banner: prefer printing `run 'charon login'` over the raw
  `?token=` URL (also closes the ATC-AUDIT token-in-banner finding).

---

## 6. First-run + recovery UX

- **Fresh install / headless container:** no GUI password needed. The token already
  exists (secrets.json / `.env`). Operator runs `charon login` on the host → clicks
  the printed URL from any LAN browser → durable cookie. Or browses to
  `http://host:8080`, gets 302'd to `/charon/login`, pastes the token once.
- **New browser / new device:** re-run `charon login` (or paste token once). Cookie is
  per-browser by design.
- **"Forgot" / lockout:** there is nothing to forget — the token is the credential and
  is always retrievable on the host (secrets.json). Recovery = re-login, or rotate the
  token (`charon` token rotation) which every machine client already tracks via
  `CHARON_GATEWAY_TOKEN`. If Phase-2 password is set and forgotten:
  `charon gui-password reset` (or just keep using the token — it always works as admin
  fallback). No email, no lockout timer, no external dependency.
- **Deliberate revoke-all:** `charon logout --all` bumps `CHARON_SESSION_KEY`.

---

## 7. Blast-radius / security tradeoffs (disclose)

- **Cookie over plain http on LAN:** can't set `Secure` without breaking http, which
  is the home-LAN norm (Jellyfin/HA/Pi-hole all ship http). Mitigations: `HttpOnly`
  (XSS-theft resistant; the console loads **zero external assets**, so XSS surface is
  tiny), `SameSite=Lax`, signed+expiring, and **documented** SSH-tunnel/reverse-proxy
  path for TLS. Consistent with existing accepted tradeoff W-7 (web-dashboard review).
- **Session cookie ≠ API access:** session authorizes `/charon/*` only; a stolen GUI
  cookie can drive setup but is scoped to the console — it is NOT a `/v1/*` bearer.
- **Token unchanged = no machine-client regression** (the whole point of §2).
- **Rotation decoupled:** token rotation doesn't nuke sessions by default; that's a
  deliberate UX choice, with `logout --all` for when you *do* want it.
- **DNS-rebinding + CSRF guards preserved** and extended to `/charon/login`.
- **DO NOT adopt Option B as default** — LAN-trust for a key-holding, money-spending
  admin surface is the one genuinely dangerous option here.

---

## 8. Ticket-ready spec

**Title:** `GUI-AUTH-1` — friendly session login for the `/charon/*` web console
(token stays the `/v1/*` API credential)

**Owns (files):**
- `src/charon/proxy_server.py` — `_LOGIN_HTML`; `_valid_session()`;
  `_issue_session()`/`_clear_session()`; login/logout routes; surface-aware dispatch;
  swap raw-token cookie → signed `charon_sess`; 302-to-login for unauth GUI GETs.
- `src/charon/secrets.py` — `get_or_create()`; (Phase 2) gui-password hash helpers.
- `src/charon/gateway.py` — generate/inject `CHARON_SESSION_KEY` on start; pass session
  key to the server; update startup banner to prefer `charon login`.
- `src/charon/cli.py` — `charon login`, `charon logout --all`; (Phase 2) `gui-password`.
- `tests/test_gateway_gui_auth.py` (new).
- Docs: `docs/getting-started.md`, `docs/docker.md` (login flow + TLS/tunnel note).

**Dependencies & sequence:**
- Depends on the pending **token-into-secrets.json** rotation only loosely (both touch
  secrets.json); sequence GUI-AUTH after rotation lands, or coordinate the single
  `secrets.py` writer to avoid a two-writer collision. No `/v1/*` code is touched.
- Single writer per file — no other ticket should be editing `proxy_server.py`
  dispatch concurrently.

**Acceptance criteria:**
1. `/v1/chat/completions` and `/v1/models` behave **identically** to before with a
   valid/invalid/absent Bearer token (regression-locked). Session cookie does NOT
   authorize `/v1/*`.
2. Unauthenticated GET `/charon` (or `/charon/setup`) 302-redirects to `/charon/login`
   and renders a login page (not raw 401 JSON).
3. POST `/charon/login` with the correct token sets an HttpOnly signed `charon_sess`
   cookie and 302s to `/charon`; subsequent `/charon/*` GETs succeed with **no** token
   in URL or header.
4. POST `/charon/login` with a wrong token re-renders the form with an error, sets no
   cookie, and is constant-time (no early return leaking validity).
5. A tampered/expired `charon_sess` is rejected (falls back to login); a valid cookie
   within the refresh window is re-issued (sliding expiry).
6. The gateway token still works as `?token=` and as an admin fallback for `/charon/*`;
   an old `?token=` link auto-upgrades to a `charon_sess` cookie and strips the token
   from the URL.
7. `charon login` prints a working click-once URL that lands authenticated.
8. `charon logout --all` rotates `CHARON_SESSION_KEY` and invalidates prior cookies.
9. Existing CSRF/Origin and DNS-rebinding guards still pass; `/charon/login` POST is
   CSRF-guarded.
10. `CHARON_SESSION_KEY` is auto-created 0600 in secrets.json on first start; never
    logged; never forwarded upstream.

**Test plan (stdlib `unittest` + a live loopback server, matching existing gateway
tests):**
- Unit: cookie sign/verify round-trip; tamper (flip a MAC byte) → reject; expired
  `exp` → reject; sliding re-issue.
- Integration (spawn `GatewayProxyServer` on 127.0.0.1):
  - `/v1/models` with Bearer → 200; wrong Bearer → 401; **with only a session cookie →
    401** (proves API stays token-only).
  - GET `/charon` no creds → 302 `/charon/login`.
  - POST `/charon/login` good token → `Set-Cookie: charon_sess`; follow-up GET
    `/charon/config` with cookie → 200.
  - POST `/charon/login` bad token → form + no cookie.
  - `?token=` GET → sets `charon_sess` + 302 stripping token.
  - Cross-origin POST `/charon/login` (bad `Origin`/`Sec-Fetch-Site`) → 403.
  - Loopback bind + non-loopback `Host` → 403 (rebinding guard intact).
- CLI: `charon login` prints a URL that authenticates end-to-end; `logout --all`
  rotates the key and 401s an old cookie.

**Out of scope (v1):** mandatory password, multi-user/roles, TLS termination
(documented as reverse-proxy/tunnel), rate-limiting the login (single home user —
constant-time compare is the guard).
