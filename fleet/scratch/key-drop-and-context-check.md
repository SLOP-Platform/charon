# Key-drop + context check (READ-ONLY investigation; no config changed; no secret value ever printed)

Host: `ssh -i ~/.ssh/4lom stack@10.0.1.60`  · container `charon-gateway-1` runs as unprivileged user `charon` (no sudo needed).
Verified in-container: `CHARON_HOME=/data`, `secrets.config_dir() -> /data`, `secrets_path() -> /data/secrets.json` (0600, `charon`-owned).
`secrets.json` current KEY NAMES only (values NOT read): CEREBRAS_API_KEY, DEEPSEEK_API_KEY, GROQ_API_KEY, HF_TOKEN, MISTRAL_API_KEY, NANOGPT_API_KEY, NEURALWATT_API_KEY, OPENCODE_ZEN_KEY, OPENROUTER_API_KEY, TOGETHER_API_KEY.
Confirmed FEATHERLESS_API_KEY and CLINE_PASS_API_KEY are NOT present in the container env today (both brand-new).

---

## PART A — SAFE KEY-DROP (hidden prompt, no file edit, key never in chat/history/git, manager never sees value)

### Mechanism found
- `/data/rotate-hf.py` exists but is HF-specific (validates `hf_` prefix, writes `HF_TOKEN`). It is the *pattern*, not a generic helper.
- The generic, hardened writer is already shipped: `charon.secrets.set_secret(key_env, value)` (src/charon/secrets.py:61).
  It writes a FRESH 0600 temp with `O_NOFOLLOW`|`O_EXCL`, then atomic `os.replace` — never world-readable, never logs the value, validates the env-name.
- No standalone "reload-secrets" HTTP route exists. The live reload path is the web-setup handler `_reload()` (gateway.py:437) =
  `secrets.apply_to_env()` -> `load_config()` -> `server.apply_routes()`. It runs on every setup write action (e.g. the `providers` action, gateway.py:466).

### Operator commands (copy-paste). Run BOTH inside the SSH session. `-it` is required for the hidden prompt.

```
ssh -i ~/.ssh/4lom stack@10.0.1.60
```

Featherless:
```
docker exec -it charon-gateway-1 python3 -c 'import getpass; from charon import secrets as s; k=getpass.getpass("Featherless key (hidden, no echo): ").strip(); assert k, "empty - aborted"; p=s.set_secret("FEATHERLESS_API_KEY", k); print("stored FEATHERLESS_API_KEY len", len(k))'
```

ClinePass:
```
docker exec -it charon-gateway-1 python3 -c 'import getpass; from charon import secrets as s; k=getpass.getpass("ClinePass key (hidden, no echo): ").strip(); assert k, "empty - aborted"; p=s.set_secret("CLINE_PASS_API_KEY", k); print("stored CLINE_PASS_API_KEY len", len(k))'
```

- `getpass.getpass` reads with echo OFF; the value never touches the terminal, shell history, chat, or git. Only a length prints.
- No `read`/`unset` juggling needed — nothing lands in a shell variable in the operator's session.
- Manager role: after the operator reports "stored", the manager wires the provider config referencing only the env NAME
  (`key_env=FEATHERLESS_API_KEY` / `CLINE_PASS_API_KEY`, no key value) via the setup `providers` action. That call runs `_reload()`
  -> `apply_to_env()` picks up the just-stored key -> routes re-bake. Manager never handles the value.

### RESTART NEEDED?  ->  NO (for these brand-new keys), provided a reload is triggered.
- `apply_to_env()` uses `os.environ.setdefault` (#33). `setdefault` only no-ops when the key is ALREADY resident.
  Both new keys are confirmed absent from the process env, so setdefault WILL inject them on the next `_reload()`.
- Routes resolve `api_key` from env at `load_config()` time; `_reload()` re-reads env + re-applies routes, so the new key goes live hot.
- Trigger for `_reload()`: the manager adding the Featherless/ClinePass provider via the setup API (any setup write action runs it).
  So: drop key (operator) -> add provider referencing env NAME (manager) -> live. No container restart.
- #33 caveat applies ONLY to a FUTURE ROTATION of an already-resident key: then setdefault no-ops and that rotation DOES need a
  container restart (or the reload won't overwrite). First-add of these two keys does not hit that.

---

## PART B — CONTEXT LIMITS + ECONOMICS (verified from primary Featherless / Cline docs)

### Featherless tier ladder (context vs $/mo) — CONFIRMED
| Plan | $/mo | Context cap | Concurrency | Billing |
|---|---|---|---|---|
| Premium (Chat) | $25 | **~32K HARD** | 4 units | flat/unlimited |
| Agent Standard | **$100** | **up to 256K** | 8 units | flat/unlimited requests, model <=229B |
| Agent Standard (higher) | $200 | up to 256K | 8 units | flat/unlimited, any model incl DeepSeek/Kimi/GLM |

- 32K on **Premium $25 is a real HARD platform cap**, applied regardless of the model's native window. DeepSeek V4 / Qwen3 / Kimi K2.x
  have 128K+ native, but Premium truncates to ~32K. (Legacy docs also show a 4k/8k/16k model tiering — same story: platform-capped, not model-native.)
- The lift to 256K is the **$100/mo Agent Standard** tier (operator's figure confirmed). $200 variant same 256K, adds full model catalogue.

**Verdict on Premium as coding backbone: NON-STARTER.** Operator's sessions run 100K-200K+; 32K Premium cannot hold them. Confirmed dealbreaker.

### Economics re-run at $100/mo / 256K vs metered gpt-5.4-direct
- Load: ~500-720M input tok/mo. gpt-5.4-direct ~$0.81/1M eff -> **~$405-583/mo**.
- Featherless Agent Standard: **$100/mo flat, unlimited requests, 256K, 8 concurrent** -> beats metered by **~$305-483/mo (4-6x cheaper)** AND clears the context wall.
- **Net: open-model backbone is still worth it at $100/mo** — but ONLY once an open model is proven good enough.
  GATE: this is gated on the benchmark open-model cutover. Do NOT pay $100/mo flat until a real-outcome benchmark clears an open model
  (DeepSeek V4 / Qwen3.7 / Kimi K2.7). Per project memory the current synthetic benchmark is NOT a valid ranker, so that gate is not yet
  satisfiable — real blocker is standing up out-of-band/actuals grading (#26) first. Until then keep gpt-5.4-direct (128K+) as the large-context primary.
  8-concurrent-unit ceiling on Agent Standard is the one capacity caveat vs metered's unlimited parallelism.

### ClinePass context limit — CHECKED (this is the CLINE_PASS_API_KEY leg)
- ClinePass = **$9.99/mo** ($4.99 first month), 2-5x standard rate limits, 10 open coding models
  (DeepSeek V4 Pro/Flash, Qwen3.7 Max/Plus, Kimi K2.7 Code, GLM-5.2, MiniMax M3, MiMo V2.5 ...).
- Context: pricing table tiers on **"Qwen3.7 Plus (<=256K tokens)" vs "> 256K tokens"** -> ClinePass serves the models' FULL native window
  (256K+), **NOT a 32K truncation**. So ClinePass does NOT cap coding context the way Featherless Premium does — it is a viable large-context leg.
- Practical note: ClinePass is rate-limited (not flat-unlimited), so it fits as a cheap open-model TRIAL/secondary leg at 256K — a good way to
  vet open models against real coding load for ~$10/mo BEFORE committing to Featherless's $100/mo flat tier.

### Bottom line
- Featherless **Premium 32K = dealbreaker** for coding backbone. Fix = **Featherless Agent Standard $100/mo (256K)** OR keep **gpt-5.4-direct / any 128K+ provider** as the large-context primary until an open model is benchmark-proven.
- **ClinePass ($9.99, 256K)** is the cheap way to trial the open models at full context first; it does NOT truncate context.

Sources: featherless.ai/docs/plans, featherless.ai/docs/concurrency, featherless.ai/docs/model-compatibility; docs.cline.bot/getting-started/clinepass, cline.bot/cline-pass.
