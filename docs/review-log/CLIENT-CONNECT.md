# CLIENT-CONNECT — `charon connect <client>`

## What
New `charon connect <client> [--host --port --model --token --install --yes]`
subcommand wiring a client to the local Charon gateway (gateway-first last mile).
Flow: verify gateway via `GET /v1/models` (token) FIRST → discover a served model
→ optionally install the client → write that client's provider config → print the
verify launch command.

## Design decisions
- **Agnostic by construction.** The ONLY client-specific knowledge is the
  per-client writer entries in `connect.REGISTRY`. The gateway probe + model
  discovery (`discover_models`) are client-neutral. `supported_clients()` is
  derived from `REGISTRY`, so the supported list can never drift from the writers
  (adding a client — incl. the GUI follow-ons cline/continue — is one entry).
- **Gateway-first / fail-closed.** Unreachable (or token-rejected) gateway →
  non-zero exit and NO config written; prints `charon gateway` to start it. We
  never point a client config at a dead gateway.
- **Reuse, not reimplement.** Discovery reuses `providers._parse_models` (OpenAI
  `{"data":[...]}` shape) and `providers._NoRedirect` (no cross-host token leak);
  token resolves like the gateway path (`--token` → `CHARON_GATEWAY_TOKEN`, via
  `secrets.apply_to_env()`).
- **stdlib-only / no new dep.** PyYAML is a dev/test dep only (core has zero
  runtime deps), so YAML configs (omp/aider) are written with a small top-level
  merge (`yaml_merge_toplevel`): managed keys re-emitted deterministically, every
  other top-level block preserved byte-for-byte. opencode.json uses a JSON
  deep-merge into `provider.charon`. All writers are idempotent and preserve
  unrelated keys.
- **Token hygiene.** The token is written ONLY into the client's own config file;
  it is never printed/logged (stdout shows `token: set (written to config)`).
  Asserted in tests.
- **Install is opt-in.** Without `--install` we only detect + print the per-OS
  install command (with the Windows/WSL PATH-gap note — the omp case the operator
  hit). `--install` shells out best-effort behind a confirmation (`--yes` skips).

## Client matrix (this ticket)
`opencode` → `~/.config/opencode/opencode.json`; `omp` →
`~/.omp/agent/models.yml`; `aider` → `~/.aider.conf.yml`. GUI clients
(cline/continue) are a documented follow-on — the registry is the extension point.

## Tests (`tests/test_connect.py`)
Live loopback-server discovery (asserts `/v1/models` + `Bearer` header);
unreachable → exit 1, no file; each writer's shape (baseURL+token+model) at the
right path + idempotency; opencode preserves existing providers/keys; explicit
`--model` override; no-models-served → exit 1, nothing written; unknown client
lists supported; token absent from stdout; no install attempted without
`--install`; `yaml_merge_toplevel` preserves unrelated keys & is idempotent;
registry is the single source of the supported list.

## Owns
`src/charon/cli.py`, `src/charon/connect.py`, `tests/test_connect.py` (+ this
per-ticket fragment). Gate green: pytest 596 + new 12, ruff, mypy, boundary,
version.
