# SR-13 security review — `/charon/login` cookie auth gate

Branch `feat/sr-13` @ 8c557fb · worktree `/home/stack/code/charon-wt-sr13` · READ-ONLY adversarial.
Design: `/home/stack/charon-private/fleet/AUTH-GUI-DESIGN.md` (Option C / TOFU).

## VERDICT: FIX (one must-fix before merge) — confidence HIGH

The core crypto and the `/v1/*` boundary for *direct* `/v1` requests are sound. But
the session cookie can reach the **money/data-plane forwarder** through an unmatched
`/charon/*`-prefixed path, which the design explicitly promised it could not
(§7: "a stolen GUI cookie ... is NOT a /v1/* bearer"). Fix that one thing, then SHIP.

---

## F1 (MUST-FIX, HIGH) — session cookie reaches the data-plane forwarder (spend path)

`proxy_server.py:_handle` treats any path with prefix `/charon/` as `is_gui`, and
`is_gui` requests are authorizable by a `charon_sess` session cookie. But only a
fixed set of `/charon/*` paths are consumed by `try_handle_public_gui` /
`try_handle_control_plane`; **any other `/charon/*` path falls through to
`forwarder.forward_with_failover(self, srv)`** — the billed provider-call path, which
routes purely on the request-body `model` and ignores the URL path.

- `src/charon/proxy_server.py:352-388` — `is_gui = path_only.startswith("/charon/")`;
  `authed_by_session` gates `is_gui`; after the two routers return False it falls to
  `forwarder.forward_with_failover(self, srv)`.
- `src/charon/console_router.py:try_handle_control_plane` — returns False for any
  `/charon/*` POST not in the enumerated setup list → fall-through.
- `src/charon/forwarder.py:forward_with_failover` — routes on `orig_bj["model"]`, no
  path check → real upstream call / real spend.

**Empirically confirmed** (live loopback server, session cookie only, no token):
```
A  POST /v1/chat/completions  + charon_sess  -> 401     (direct /v1 boundary holds)
B  POST /charon/spend         + charon_sess  -> 502 "all upstreams unreachable"
                                                  (reached forwarder — would BILL on a live upstream)
C  POST /charon/spend         no creds       -> 401     (so it IS the cookie granting it)
```
A stolen 30-day `charon_sess` cookie thus becomes a money-spending provider
credential — exactly the guarantee AUTH-GUI-DESIGN §7 sold as false. Also note the
enumerated-setup Origin/Sec-Fetch-Site CSRF guard does **not** cover this
fall-through POST; the only cross-site defense left is `SameSite=Lax` (blocks the
victim's cookie on a cross-site POST). Realistic exploit = a *replayed stolen cookie
value* or a same-site XSS (console loads zero external assets → low but nonzero), not
an arbitrary off-origin page. Contained, hence FIX not BLOCK.

**Exact fix (pick one):**
1. Preferred: gate the forwarder on token only. In `_handle`, before calling
   `forwarder.forward_with_failover`, require `authed_by_token` — i.e. a request that
   authed *only* by session must never reach the data plane. e.g. after the control-
   plane router returns False: `if not authed_by_token: self._json(404 or 401); return`.
2. Or: make `is_gui` match only the known console routes (exact set), so an unknown
   `/charon/xyz` is never session-authorizable and 404s instead of forwarding.

Add a regression test: session-cookie-only `POST /charon/<anything>` with a chat body
must NOT reach the forwarder (assert 401/404, never 502-from-upstream).

---

## Everything else that was attacked — HOLDS

**Auth boundary for `/v1/*` (the critical one):** `/v1/*` is not `is_gui`, so
`authed_by_session` is always False there; only `_authorized(token)` counts —
byte-for-byte unchanged (Bearer / `?token=` / legacy `charon_token` raw-token cookie).
`_verify_session` is never consulted for `/v1/*`. Confirmed 401 for session-cookie →
`/v1` (test A). Reverse (raw Bearer → `/charon` setup write) is *intended* admin
fallback per design, not a leak.

**Cookie forgery / signing (`_sign_session`/`_verify_session`, proxy_server.py:63-108):**
HMAC-SHA256 over `b64url(payload)`, constant-time `hmac.compare_digest`, MAC covers the
whole payload so field-flipping breaks the signature (test_tampered_payload_rejected),
missing/short sig rejected (needs exactly 2 non-empty parts), expired `exp` rejected,
wrong/rotated key rejected. No length-extension (HMAC). No missing-signature-accepted
path. Solid.

**Key handling (`_resolve_session_key` :96 / `set_secret` secrets.py:61-86):**
env → secrets.json → `secrets.token_hex(32)` (256-bit) persisted via `os.open(...,0o600)`
+ atomic replace. No weak/predictable default; failed persist falls back to an in-memory
random key (churn, not exposure). Never logged/printed/bannered (grep clean;
`gateway.py` untouched). CHARON_SESSION_KEY 0600 confirmed.

**CSRF on login/logout/setup POSTs:** login POST reuses the Origin/Sec-Fetch-Site guard
(console_router.py). Login-CSRF is meaningless (success needs the token). Setup writes:
`SameSite=Lax` stops the victim's cookie on cross-site POST + Origin check = same posture
as pre-SR-13. No synchronizer token, but adequate for this single-user threat model.

**TOFU `?token=` → cookie (proxy_server.py:369-378):** on `?token=` GET the server issues
`charon_sess` and 302s to `_strip_token_from_path()` (token dropped, other params kept).
Redirect target is the same-origin request path only — **no open redirect** (login
success → static `/charon`, logout → static `/charon/login`). `log_message` is a no-op
(proxy_server.py:167) so `?token=` never hits access logs; console loads zero external
assets and the token is stripped before the clean page loads → no Referer leak.

**Unauth reach:** unauthenticated GET `/charon*` → 302 to login; POST/`/v1` → 401.
No mutating endpoint reachable without a valid cookie or token (setup writes need
`is_gui`+auth; logout only *clears* a cookie).

## Low / informational (not blockers)
- **Logout CSRF (LOW):** `GET /charon/logout` clears the cookie unconditionally before
  the gate — a top-level cross-site navigation can force-logout the operator (annoyance
  DoS, no compromise). Optionally require POST + Origin for logout.
- Two-writer race on lazy `session_key()` caching (no lock) → at worst one throwaway key;
  cosmetic.
