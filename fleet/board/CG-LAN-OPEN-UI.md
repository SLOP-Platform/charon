repo: charon
tier: strong
priority: 2
difficulty: 2
work_class: gateway-auth
branch: feat/cg-lan-open-ui
parked: true
note: ABANDONED 2026-07-19 — superseded by the existing /charon/login session-cookie flow (already a simple browser auth layer); lan_open_ui introduced a key-exfil hole. Do not build. Also superseded 2026-07-21 by GATEWAY-LITELLM-ADOPT, which adopts litellm.Router for the proxy_server.py money-path; remains abandoned.
  DRAFT — operator review. Scoped 2026-07-19 from CG-AUTH-INVESTIGATION.md (code-confirmed).
owns: src/charon/proxy_server.py, src/charon/gateway.py, tests/test_gateway_lan_open_ui.py
depends_on:
serial_justified: The gate (proxy_server) and the bind-guard (gateway.py) are ONE auth
  decision — the flag must relax both together or it is either useless (bind still refused)
  or unsafe (bind opened but gate still blocks). One reviewer, one change.
accept: |
  GOAL: on the LAN, the browser CONSOLE (/charon/*) requires NO auth; the machine API
  (/v1/*) KEEPS its bearer token. Driven by an explicit config/env flag, default OFF.

  CODE-CONFIRMED FACTS (do not re-derive; verify before editing):
  - Auth is a single static shared bearer secret, checked once in `_authorized()`
    (proxy_server.py:245-262); its value is never used downstream. Access control only.
  - The gate is `authed_by_token = srv.token is None or self._authorized(...)` at
    proxy_server.py:402-412. UI vs API is already split: `_GUI_ROUTES`/`is_gui`
    (proxy_server.py:89-98,395); /charon/* = console, /v1/* = machine API.
  - The data-plane guard at proxy_server.py:442-449 ALREADY rejects the console session
    cookie for /v1/* — so /v1/* is structurally token-only. This is why the change is safe
    at ONE site: relaxing `is_gui` cannot leak into /v1/*.
  - gateway.py:455-460 REFUSES a non-loopback bind when token is None ("the gateway holds
    your provider keys"). A plain `token=None` therefore CANNOT give the operator's ask on
    the LAN — it would open BOTH surfaces. So config alone is insufficient; needs this change.
  - Auth sits ABOVE forwarder (resolved in _handle before forward_with_failover,
    proxy_server.py:451) → survives the planned LiteLLM substrate swap. Do not entangle.

  DO:
  1. New explicit flag (e.g. `[gateway] lan_open_ui` / `CHARON_LAN_OPEN_UI`), default FALSE.
  2. When SET: `is_gui` requests pass with NO credential; /v1/* STILL requires the bearer
     token (unchanged). The API token stays mandatory — "who can call /v1/*" == "who can
     spend the provider keys."
  3. Qualify the gateway.py:455-460 non-loopback guard so this mode is permitted (UI open,
     API token required) — but a fully token-less API on a non-loopback bind stays REFUSED.
  4. CRITICAL INVARIANT: opening the UI must NEVER open /v1/*. That is the whole review.

  OPERATOR DECISION baked into the ticket (VIEW vs WRITE) — see scope below. Default = (a).

  FAIL-ON-REVERT tests (tests/test_gateway_lan_open_ui.py):
  - flag ON + non-loopback bind: GET /charon/ returns 200 with NO Authorization header.
  - flag ON: GET/POST /v1/* WITHOUT a valid token returns 401 (API still gated). REVERTING
    the /v1 guard makes this RED — proves the UI-open change did not leak to the API.
  - flag OFF (default): current behavior exact — /charon/* AND /v1/* both require the token,
    and a non-loopback bind with token=None is still REFUSED at startup.
  - the bind-guard qualification allows (UI-open, API-token) but still refuses (API-tokenless).
scope: |
  Product gateway only. Rig-neutral. This is the "LAN, no web auth for now" step from
  [[git-hosting-gitea-primary]] — CG/SLOP run LAN-only today; real auth (tinyauth, then
  Traefik forward-auth) comes LATER as plugins, NOT here.

  THE VIEW-vs-WRITE DECISION (operator picks; ticket defaults to a):
  The console is NOT read-only — it has config-WRITE endpoints (console_router.py:138-142:
  POST /charon/providers|models|pools|tiers|enable|disable|remove|balance) + /charon/config.
  (a) FULL-OPEN UI on LAN (view + write, no auth). Simplest — one flag, the is_gui relax.
      Trusts the LAN: any host on the home network can reconfigure the gateway. Matches the
      operator's "LAN no auth is fine" + trusted home network + auth-plugin-coming posture.
      RECOMMENDED for now.
  (b) VIEW-open, WRITES still token-gated. Safer, but needs per-route read/write
      classification of the console routes (not the single is_gui boolean) — more work, and
      largely moot once the auth plugin lands. Defer unless the LAN is not fully trusted.

  DO NOT: build tinyauth/Traefik here; wire the dead VirtualKeyManager (proxy_server.py:581,
  .resolve() never called); or touch the separate orchestrator token (CHARON_SERVICE_TOKEN,
  service/app.py) — different service.
ds: |
  ## Dependencies & sequence
  depends_on: NONE. Independent of the gateway MVP wiring and ADOPT-SUBSTRATE-01 (auth is
  above the forwarder). Can land anytime. Blast radius: the AUTH GATE on the request hot
  path — adversarial review REQUIRED, with the single invariant "UI-open must not open
  /v1/*" as the thing to try hardest to break.
  wave: gateway usability. repo: charon (public product — keep product-neutral, no rig refs).
