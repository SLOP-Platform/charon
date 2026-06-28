# Fresh-install dogfood findings — 4-LOM gateway + non-Claude clients (2026-06-28)

Mode-A test: fresh docker Charon gateway on 4-LOM (10.0.1.60), driven from the operator PC's WSL.

## RESULT: Mode-A VALIDATED END-TO-END ✓
opencode (WSL) → fresh docker Charon gateway (4-LOM) → opencode-zen → reply, over the LAN.
Unblocked only after adding the upstream key via `providers add opencode-zen --key <k>` +
`docker compose restart gateway`.

## VALIDATED ✓
- **Fresh docker gateway** off published `ghcr.io/slop-platform/charon:v0.2.0`: `docker compose down -v`
  → `docker compose run --rm gateway setup` (opencode-zen) → `docker compose up -d` → `(healthy)`,
  serving ~50 models incl. gpt-5.4. Config persisted in the `charon-config` named volume across `--rm`.
- **LAN exposure:** editing the compose host port `127.0.0.1:8080:8080` → `8080:8080` makes it
  reachable from the PC; still token-gated (wrong token → 401, proving the gate).
- **`charon connect omp`** (CLIENT-CONNECT #72): verifies the gateway, installs omp, writes the
  config, prints "now run". The COMMAND works.
- Token gating + `/v1/models` over the LAN: confirmed.

## FINDINGS (real gaps surfaced — feed OHMYPI-ASSESS + a CLIENT-CONNECT-omp fix)
1. **`--install` used the Windows bun via WSL interop** → installed omp to `C:\Users\<u>\.bun\bin`
   (Windows), mismatching the **WSL** `~/.omp` config it wrote → WSL `omp` not found. CLIENT-CONNECT
   must detect WSL and use a WSL-native package manager (or refuse + warn clearly), not whatever
   `bun`/`npm` happens to resolve via interop.
2. **omp runtime deps:** omp (pi-coding-agent 16.2.2) requires **Bun ≥1.3.14** (not node). A clean
   WSL needed `sudo apt install unzip` + a WSL-native bun (`curl … bun.sh/install`) before `omp`
   would run. `charon connect --install` did none of this.
3. **BLOCKER — omp ignores the written config.** `charon connect omp` writes
   `~/.omp/agent/models.yml` with an inline `api_key`. omp 16.2.2 does NOT consume it: `omp models`
   (all providers) returns "No models available. Set API keys in environment variables", and
   `omp --model auto` falls back to its own OAuth sign-in. Tried: inline `api_key`, `env_key:
   CHARON_GATEWAY_TOKEN` + env var, `CHARON_API_KEY` env, `omp models refresh` — none worked. omp
   appears to manage provider creds via its **auth-broker / OAuth / a different schema**, so the
   models.yml-inline-key mechanism is the wrong integration for current omp. **OHMYPI-ASSESS must
   determine omp's real custom-openai-compatible-provider config** (likely auth-broker or a specific
   env/config schema) and CLIENT-CONNECT's omp writer must match it.

4. **`setup` accepts a bad/empty upstream key silently (BLIND masked input).** The fresh setup
   reported "2 models configured / Done" with an invalid opencode-zen key; the failure
   (`AuthError: Invalid API key` on every completion, while `/v1/models` 200s) only surfaced at the
   first real chat. Two fixes: (a) **validate the key at setup** (UX-POLISH "validate-key-at-setup")
   — probe a completion, not just import the catalog; (b) the masked key prompt should **echo/confirm
   the key** (operator couldn't tell a paste was wrong). Workaround that works today:
   `providers add <preset> --key <visible-value>`.

## RECOMMENDATION
- The **gateway** is validated fresh end-to-end. To get a GREEN client→gateway run NOW, use
  **opencode** (its connect writer is the proven one): `charon connect opencode --host 10.0.1.60
  --port 8080 --token <tok>` then drive it — decouples the gateway test from omp's quirks.
- Treat omp as **OHMYPI-ASSESS** work: nail omp 16.2.2's provider-config schema, then fix the
  CLIENT-CONNECT omp writer + the WSL-install routing (findings 1–3 above).
