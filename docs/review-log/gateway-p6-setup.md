## 2026-06-26 — P6 (gateway-first README) + Setup phase

Operator-approved reshape: P6 + a real setup experience; the Windows `.exe`
deferred (most tools like this ship `pipx`/`uvx`, not an `.exe`; the operator's
users are devs). Live-validated against real providers throughout.

- **P6:** README reframed gateway-first (gateway = headline + first section; the
  orchestrator is a clearly-marked "Advanced: autonomous mode", with the autonomy
  disclosure scoped to it). Test enforces ADR-0005 **R3**: the gateway shares the
  `GatewayProxy` core AND never imports the privileged coordinator loop.
- **Config layer** (`config.py`): one validated, atomic writer for
  providers/models/pools JSON in the user config dir — shared by the CLI and the web
  page; the gateway now defaults its config source to `~/.charon` so it "just works"
  after setup. `providers add` now **persists the provider** (base_url/key_env), so a
  CUSTOM provider (DeepSeek, Chutes, …) works with no hand-edited TOML.
- **More presets:** deepseek, chutes, groq, together, mistral — **all base URLs
  verified live** via `providers test`. README: any OpenAI-compatible provider works
  via `--base-url`.
- **`charon setup` wizard:** guided providers→keys→models→pool, written to the config
  dir; getpass (no echo); graceful no-TTY exit.
- **Web setup page** (read-WRITE — security-sensitive): `GET /charon/setup` form +
  `POST /charon/{providers,models,pools,remove}` behind a hook (`proxy_server` stays
  lean). Token-gated (same gate); **CSRF/Origin guard** rejects cross-origin/cross-site
  writes even with a leaked token; body-size capped; the key field is a password input
  and **never rendered back**; the summary exposes key-SET state, not the value. Writes
  persist config + keys (0600) and **hot-reload** the running routes (proven:
  POST provider+model → `/v1/models` updates with no restart). Disabled (read-only)
  for `--config` TOML mode.
- **Gate:** 161 passed, ruff clean, mypy clean (31 files), boundary OK, version OK.
- **Adversarial review:** the web write endpoint (key handling + CSRF + hot-reload) is
  being sent to an independent security reviewer.
- **Independent security review — reconciled (verdict was NEEDS FIXES):**
  - **[HIGH] DNS-rebinding defeated the Origin-only CSRF guard on the ungated-loopback
    default** → a web page could add a provider with a victim `key_env` + attacker
    `base_url`, then a completion would ship the real key to the attacker. **Fixed:**
    an **anti-DNS-rebinding Host guard** — on a loopback bind, any request whose `Host`
    header is not a loopback literal is 403'd (defeats `Host: evil.com` rebinding),
    applied to the WHOLE gateway (forward + setup), failing closed. Tested ungated.
  - **[MED] web-added `base_url` was unvalidated** (SSRF / key-exfil sink). **Fixed:**
    `config.add_provider` now rejects non-http(s) and link-local/metadata hosts
    (mirrors `providers test`) — covers CLI + web. Tested.
  - **[MED/LOW] Origin guard fail-open when header absent** — closed by the
    fail-closed Host guard above.
  - **[LOW] hot-reload 3-attr swap not atomic** → `server.apply_routes(...)` swaps
    under the lock `chain_for` reads, so no torn routes/pools view.
  - **[LOW] `_SENSITIVE_ENV` incomplete / error-path path-disclosure / key-env on
    half-write** — hardened the denylist (LD_AUDIT/NODE_OPTIONS/BASH_ENV/…), the setup
    error path now returns a generic message for non-ValueError (no secrets-path leak),
    and `add_provider` validates `key_env`.
  - **Verified-correct (kept):** token gate covers all endpoints when set; no key
    leak (0600, never echoed/rendered/returned); cross-origin + null-origin blocked;
    non-loopback bind without token refused at build time; no path traversal; body cap.
  - **Gate after fixes:** 164 passed, ruff clean, mypy clean (31 files), boundary OK.
