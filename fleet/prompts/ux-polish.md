# UX-POLISH — First-run UX polish batch

## Dependencies & sequence
**depends_on: none** — Wave 1 (CLI cluster, alongside TIER-RECS). Many original items already
shipped in SETUP-UX-A (items 1–3: colorize presets, key validation, paste feedback). This ticket
covers the remaining 7 items.

## Remaining items

### Item 4: Use `sys.argv[0]` instead of hardcoded `charon` in CLI messages
**File: `src/charon/cli.py`**
- Replace `"charon gateway"`, `"charon setup"`, `"charon providers add"`, `"charon models import"`,
  etc. with `f"{sys.argv[0]} gateway"` etc. wherever the CLI suggests running another charon
  command. Also in `src/charon/gateway.py` and `src/charon/connect.py` if they hardcode "charon".
- The named subcommand arg should use `sys.argv[0]` — e.g. `f"{sys.argv[0]} setup"`.
- Gated when `--charon-dry-run` is set or during tests (non-interactive mode); keep test
  expectations from breaking.

### Item 5: Gateway startup URL hints — loopback vs LAN
**File: `src/charon/gateway.py`**
- When host is `127.0.0.1` or `localhost` → print `console: http://127.0.0.1:PORT/ (local only)`.
- When host is `0.0.0.0` → print `console: http://<LAN-IP>:PORT/` (resolve the host's LAN IP).
- Fallback: print the actual bind address as-is.

### Item 9: Web setup page discoverability
**Files: `src/charon/proxy_server.py`** (inline HTML templates)
- Add a visible "⚙ Setup" button/link on the `/` (CONSOLE_HTML) dashboard that links to
  `/charon/setup?token=...` (propagate the token from the URL).
- Add a "← Dashboard" link on the `/charon/setup` (SETUP_HTML) page that links back to `/?token=...`.
- Propagate `?token=` through these links so the user doesn't have to re-paste it.

### Item 10: Token cookie — smooth the `?token=` UX
**Files: `src/charon/proxy_server.py`** (request handler)
- On a successful `?token=` auth, set a short-lived (15 min) httpOnly+Secure cookie
  `charon_token` (same value as the token param).
- On subsequent requests, if the cookie is present and valid, skip the token check.
- Keep existing URL-param auth as fallback.
- Keep existing CSRF/Origin/Sec-Fetch guards.

### Items 6, 7, 8: Docs
- **Item 7** (Docker group): Add note to `docs/docker.md` about `sudo usermod -aG docker $USER` +
  re-login.
- **Item 8** (gateway vs orchestrator): Add clear separation in onboarding/README: gateway mode
  (proxy only) vs orchestrator mode (`charon work`).
- **Item 6** (secrets hot-reload): Already in handoff note, no code change needed.

## CONSTRAINTS
- **Owns**: `src/charon/cli.py`, `src/charon/proxy_server.py`, `src/charon/gateway.py`,
  `src/charon/connect.py` (sys.argv[0] propagation only)
- **Stdlib-only**. No new dependencies.
- **Provider/agent-agnostic**, product-clean.
- Items 4, 5, 9, 10 are the build items. Items 6–8 are docs (low priority, can be deferred).

## accept
```
PYTHONPATH=src python3 -m pytest tests/ -q -x && ruff check && mypy src/charon/cli.py src/charon/proxy_server.py src/charon/gateway.py src/charon/connect.py && python3 tools/check_boundary.py src && python3 tools/check_version.py
```
