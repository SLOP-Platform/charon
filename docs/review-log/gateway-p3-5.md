## 2026-06-26 — Gateway P3.5: provider/key setup CLI (operator-requested)

- **Why:** a user needs to enter provider account info (keys) without hand-editing
  config. Operator decisions: **CLI wizard now, web setup page later** (P5); keys in a
  **user-local 0600 secrets file** (not OS keyring, not repo).
- **Change:** `src/charon/secrets.py` (`config_dir`/`secrets_path`/`load_secrets`/
  `set_secret`/`apply_to_env`) + a `charon providers` subcommand (`list`/`add`/`test`).
- **Security model (operator hard rule — keys NEVER in the repo):**
  - Keys live ONLY in `~/.charon/secrets.json` (or `%APPDATA%\charon`; override via
    `$CHARON_HOME`), written via `os.open(..., 0o600)` so the file is never briefly
    world-readable; dir `0700`. `.gitignore` now blocks `secrets*`/`*.key`/`.env*`/
    `*-keys.env` defensively.
  - `charon.toml`/`.charon/*.json` hold only preset names + `key_env` references — no
    literal keys — so config stays shareable/committable.
  - `apply_to_env()` loads stored keys via `setdefault` (an explicit env var always
    wins). `providers add` reads the key via `getpass` (no echo) when `--key` is
    omitted; the key is never printed or logged anywhere.
  - `providers test` probes `GET <base>/models` with the key only as an
    `Authorization` header (never in the URL/output); even a 401/404 confirms the base
    resolves — the way to verify the UNVERIFIED nanogpt/zai presets once keys exist.
- **Proofs:** `tests/test_secrets.py` — 0600 perms, explicit-env-wins, CLI add stores
  the key WITHOUT echoing it, list shows SET/MISSING, unknown-without-base_url errors,
  custom provider with base_url. **Live-smoked:** `providers add/list` wrote a 0600
  `secrets.json`, key not echoed.
- **Gate:** 143 passed, ruff clean, mypy clean (30 files), boundary OK, version OK.
- **Adversarial review — verdict SAFE TO KEEP** (keys never in a tracked file; no
  add/list/test/log path prints a key; 0600-on-create verified). Three MED + LOWs
  fixed:
  - **[MED] `providers test` shipped the real key to the (possibly unverified/
    redirecting) base** — and the key wasn't even needed (a 401 proves the base
    resolves). **Fixed:** `test` now sends **no credentials**, **disables redirects**
    (urllib doesn't strip `Authorization` cross-host), and **rejects non-http(s)** +
    link-local (cloud-metadata SSRF) hosts. A 401/403/404 now counts as "base
    resolves". This is the safe way to verify the UNVERIFIED nanogpt/zai bases.
  - **[MED] TOCTOU on `set_secret`** (pre-existing loose-perm/symlink file written
    before chmod). **Fixed:** write a fresh `O_NOFOLLOW` 0600 temp + atomic
    `os.replace` — no world-readable window, symlink-safe, atomic.
  - **[MED→LOW] `apply_to_env` loaded every name** (LD_PRELOAD/PATH injection if the
    file were tampered). **Fixed:** only valid env-name-shaped keys load, and a
    loader-sensitive denylist (PATH/LD_PRELOAD/PYTHONPATH/…) is never injected.
  - **[LOW] `set_secret` key-env validation** (`^[A-Za-z_][A-Za-z0-9_]*$`); no-echo
    test now also checks stderr.
  - New tests: key-never-sent-on-test (mock records no `Authorization`), non-http
    scheme rejected, bad key-env rejected, sensitive/malformed env skipped.
- **Gate after fixes:** 147 passed, ruff clean, mypy clean (30 files), boundary OK.
