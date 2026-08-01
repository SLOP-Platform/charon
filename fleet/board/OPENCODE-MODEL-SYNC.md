repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: ci-infra
branch: feat/opencode-model-sync
owns: fleet/sync-opencode-models.sh
serial_justified: One sync tool whose --check mode IS the gate; separating them would ship a fixer with nothing to stop the drift recurring.
substrate: N/A
substrate-novel: |
  Nothing external can answer this: it is a consistency question between TWO rig-local artefacts —
  opencode's hand-maintained `provider.charon.models` map and this fleet's `tier-models.tsv`
  chains — mediated by our own gateway's /v1/models.

  Closest candidates, and why none covers it:
    * opencode itself — it does NOT auto-discover models for custom OpenAI-compatible providers.
      Every id must be hand-listed; there is no config flag to enable discovery. Confirmed in
      fleet/OPENCODE-MODEL-LIST-GAP.md §2 against the live client. That absence IS the defect.
    * LiteLLM / other gateway SDKs — they model provider->model routing, not "does THIS client's
      static config cover the ids MY tier chains name". Adopting one would not answer the question.
    * `jq`/`curl` — the transport, already used; not a substrate decision.
  No new dependency is introduced: curl + python3 only, both already required by the rig.
depends_on:
note: |
  ROOT CAUSE of every off-Claude job failing, measured 2026-08-01.

  opencode declares models by hand (36 entries) against a gateway serving ~2580. Critically,
  `minimax-m2.5-go` and `deepseek-v4-flash-ds` — the FIRST TWO legs of BOTH the frontier and strong
  chains in tier-models.tsv — were NOT declared. opencode therefore answered
  `{"name":"UnknownError","message":"Unexpected server error"}`, charon-run.sh classified that as an
  infra fault and failed over, and a single-leg run reported ALL-EXHAUSTED. The GATEWAY WAS HEALTHY
  THROUGHOUT — direct curl returned HTTP 200 on all six strong legs. So it presented as "the model
  pool is dead" when the truth was "the CLIENT was never told the model exists".
  Verified after declaring the two ids: charon-run rc=0, SUCCESS on minimax-m2.5-go.

  fleet/OPENCODE-MODEL-LIST-GAP.md diagnosed this on 2026-07-05 and prescribed exactly this script.
  It was never built. The gap ran 27 days.

  SCOPE DECISION (tried the alternative and reverted it): declaring ALL ~2580 served ids was
  implemented, run, and rolled back — the gateway also serves embedding and image models
  (BAAI/bge-*, Bria/*), and 2598 entries makes opencode's interactive /model picker unusable. The
  default scope is therefore the tier-chain ids plus whatever is already declared; `--all` opts
  into the full catalogue.

  THE --check MODE MATTERS MORE THAN THE SYNC. Syncing fixes today's drift; --check is what stops
  it recurring, failing loud the moment a tier chain names a model the client cannot call. It
  earned its keep immediately: on first run it found TWO further dead legs nobody had noticed —
  `kimi-k2.6` (frontier) and `minimax-m3-free` (strong) are named in tier-models.tsv but the
  gateway serves NO ROUTE for either, so both were burning a silent failover hop on every job.
accept: |
  - Regenerates provider.charon.models from the gateway's own /v1/models, preserving existing
    per-model overrides and re-adding the `auto` pool id (which /v1/models deliberately omits).
  - Default scope = tier-chain ids + already-declared; `--all` for the full catalogue;
    `--prune` (opt-in only) removes ids the gateway no longer serves.
  - `--check` exits 3 when any tier-chain model is undeclared to the client OR unserved by the
    gateway, naming the tier and flagging when the FIRST leg is affected. Exits 0 when clean.
  - FAILS CLOSED: a zero-model or unparseable /v1/models response (i.e. an auth failure) REFUSES to
    act rather than pruning the client's whole model map.
  - Writes atomically (temp file in the same dir + os.replace) after a parse-check, with a .bak —
    a crash mid-write can never leave opencode with an unparseable config.
  - The model list is passed to python by FILE, not env: ~2580 ids exceed ARG_MAX
    ("python3: Argument list too long", measured).

## Dependencies & Sequence

- **depends_on: (none).** Self-contained tool; reads tier-models.tsv and the gateway, writes only
  the opencode client config.
- **Sequence: IMMEDIATE, and wire `--check` into preflight.** Until --check runs on a cadence, this
  drift is invisible again the moment a chain is edited — which is exactly how it survived 27 days.
- **Blocks / unblocks:** unblocks ALL off-Claude work (fleet-droid, reviewer pools, dogfood runs);
  every one of them routes through the opencode client.
- **owns-collision:** none — new file.
- **Known follow-up, NOT fixed here:** 10 of 17 tier-chain legs are PROVIDER-PINNED
  (`-go`, `-ds`, `-groq`), which violates the north star that the BROKER picks the provider from a
  bare model id. The two legs `--check` flags as dead are in fact the only correctly-shaped ones;
  they fail because the gateway lacks a POOL for them. Fixing that means gateway pool changes,
  which are operator-gated (config-sync.sh --gateway). Separate ticket.
