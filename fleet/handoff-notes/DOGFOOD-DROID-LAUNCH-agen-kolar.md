# DOGFOOD-DROID-LAUNCH — substrate proof beneath the two known bugs

Date: 2026-07-24 · Agent: agen-kolar · Method: EXECUTION only (no fleet-droid.sh, no claims,
no worktrees, no branches, no script edits). All tokens redacted to sha256-prefix.

**VERDICT: GO** — once the in-flight fix supplies (a) PATH and (b) a token *derived from
opencode.json and exported OVER the stale env var*, a droid tab runs work end-to-end.
Nothing else is broken beneath the two known bugs. One correction to the fix's spec below
(§6) is load-bearing: "export a gateway token" is NOT sufficient — the operator's existing
`CHARON_GATEWAY_TOKEN` is one of the two proven failure modes.

---

## Step 1 — Token derivation via `fleet/env-registry.sh:bearer_token()`

Sourced the real helper (no reimplementation). `env-registry.sh` has **no `main` guard**, so
`source` executes its body; it is read-only, so this is safe, but it means callers must
redirect its stdout.

```
cd /home/stack/charon-private/fleet && bash -c '
  source ./env-registry.sh >/dev/null 2>&1
  tok="$(bearer_token)"; ...'
```

| Fact | Result |
|---|---|
| `source ./env-registry.sh` | rc=0 |
| `bearer_token` | **rc=0** |
| derived token length | 32 |
| derived sha256[:12] | `53eabaa7e5c6` |
| `CHARON_GATEWAY_TOKEN` set in shell? | yes, length 32 |
| env var sha256[:12] | `ed7a51b3b4bd` |
| **DRIFT** | **YES — env var ≠ opencode.json** |

Token derivation **WORKS**. Drift is **REAL and live**, exactly as
`env-registry.sh:54-56` documents.

`preflight.sh:detect_gateway_token_drift` uses the identical comparison (env var vs
`provider.charon.options.apiKey`); a full `bash preflight.sh` run exceeded a 60s timeout
(rc=143) because preflight runs the whole detector suite + access-check + foreman, so drift
was confirmed with that function's exact logic rather than by waiting it out. Not a defect —
just too heavy for a probe.

## Step 2 — Gateway readability (302/0-byte failure mode proven, not assumed)

`GET http://10.0.1.60:8080/charon/status`

| Auth used | HTTP | Body bytes | JSON parses? |
|---|---|---|---|
| **derived** token | **200** | 222,741 | **OK** |
| derived token → `/charon/config` | 200 | 106,795 | OK |
| **no** token | **302** | **0** | no — `json.loads("")` |
| **stale env** `CHARON_GATEWAY_TOKEN` | **302** | **0** | no — `json.loads("")` |

The Run-2 error string `Expecting value: line 1 column 1 (char 0)` is reproduced by BOTH the
missing-token case AND the stale-env-token case. They are indistinguishable at the error.

## Step 3 — `capability/availability.py` capped-exclusion, `strong` band chain

Chain: `minimax-m3-free deepseek-v4-flash glm-5.2 gpt-5.4-mini`

| Run | Env | stdout | rc |
|---|---|---|---|
| A | inherited shell (stale token) | *(empty)* + `CANNOT READ gateway /charon/status` | **8** |
| B | derived token exported over `CHARON_GATEWAY_TOKEN` | all 4 models | **0** |
| C | no token at all | *(empty)* + same error | **8** |

Run B note line:
`gateway http://10.0.1.60:8080: 4378 pooled model(s), 1 provider(s) parked/drained/cooled (huggingface)`

**Capped-exclusion DID run** (rc=0, positive snapshot). Per-model state:

| Model | State | Provider chain | Live providers remaining |
|---|---|---|---|
| minimax-m3-free | **available** | nvidia, nanogpt, openrouter, cline-pass | nvidia, nanogpt, cline-pass |
| deepseek-v4-flash | **available** | nvidia, nanogpt, huggingface, openrouter, deepseek, cline-pass | nvidia, nanogpt, deepseek, cline-pass |
| glm-5.2 | **available** | nanogpt, huggingface, openrouter, neuralwatt, cline-pass, deepinfra | nanogpt, neuralwatt, cline-pass, deepinfra |
| gpt-5.4-mini | **available** | nanogpt, openrouter | nanogpt |

**0 of 4 capped.** Parked/drained/cooled providers moved between probes minutes apart
(`huggingface` → `huggingface, openrouter`). I chased this as a suspected miss and it is
**correct**: `capped` requires EVERY provider in a model's chain to be down; each of the four
retains at least one live provider. Not a bug.

## Step 4 — Real completions

**(a) Raw gateway, same base URL opencode uses** (`http://10.0.1.60:8080/v1`, from
`opencode.json → provider.charon.options.baseURL`):

| Model requested | HTTP | Served as | Latency | Content | Cost (USD) |
|---|---|---|---|---|---|
| minimax-m3-free | 200 | `minimax/minimax-m3` | 0.75s | `"\n\nOK"` | 5.148e-05 |
| deepseek-v4-flash | 200 | `deepseek/deepseek-v4-flash` | 0.94s | `"OK"` | 6.188e-06 |

First attempt used `max_tokens:8` and returned `content: None` — **not** a gateway defect:
`completion_tokens_details.reasoning_tokens` consumed the entire budget (7 and 8). Re-ran at
`max_tokens:200` → `finish_reason: stop` and real text. Worth knowing: these are reasoning
models, so any droid preflight that probes with a tiny `max_tokens` will see empty content
and could misread it as a dead model.

**(b) The actual `charon-run.sh:114` invocation** — `opencode run --model charon/<M>`:

| Env | rc | Latency | Output |
|---|---|---|---|
| normal shell | **0** | 3s | `> build · deepseek-v4-flash` → `OK` |
| `env -i HOME=... PATH=~/.local/bin:...` (stripped) | **0** | 2s | `OK` |

`opencode` reads its own key from `opencode.json`, so it is **unaffected by the token drift**.
The drift only breaks the fleet-side Python/curl consumers (availability.py, preflight).

## Step 5 — PATH failure mode (Run 1) reproduced

| Shell | `command -v opencode` |
|---|---|
| this session | `/home/stack/.local/bin/opencode` (rc=0), v1.18.2 |
| `env -i bash -c` (non-login, non-interactive) | **rc=1**, `PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` |

`~/.local/bin/opencode` is a symlink → `../lib/node_modules/opencode-ai/bin/opencode.exe`.
Confirmed: a PowerShell-launched non-login bash has no `~/.local/bin`, hence rc=127 ×4 →
`ALL MODELS EXHAUSTED`.

---

## §6 — Findings that CHANGE the in-flight fix's spec

1. **`export`, do not `set-if-unset` (CRITICAL).** `availability.py:197` resolves its token as
   `next((os.environ[e] for e in GATEWAY_TOKEN_ENVS if os.environ.get(e)), None)` with
   `GATEWAY_TOKEN_ENVS = ("CHARON_GATEWAY_TOKEN", "CHARON_API_KEY", "OPENAI_API_KEY")`. The
   operator's shell HAS a (stale) `CHARON_GATEWAY_TOKEN`, so a conditional
   `[ -z "$CHARON_GATEWAY_TOKEN" ] && export ...` is a **no-op that leaves the bug fully
   intact**. The derived token must unconditionally overwrite it. Also consider unsetting
   `CHARON_API_KEY` / `OPENAI_API_KEY`, which are ahead of nothing but could shadow if set.
2. **`availability.py` has no opencode.json path of its own.** It is env-only. Either the
   launcher exports the derived value, or availability.py should learn `bearer_token()`'s
   derivation as a fallback. Today nothing bridges the two.
3. **`fleet-droid.sh:344`'s operator advice is actively misleading.** It says
   *"commonly a 401/missing CHARON_GATEWAY_TOKEN … Export a gateway token"*. An operator who
   follows that literally exports the stale profile value and reproduces the identical
   failure. It should say *re-derive from `~/.config/opencode/opencode.json`*. (Not changed —
   another sub owns this file.)
4. **Neither launcher sources `env-registry.sh`.** `grep` over `fleet-droid.sh` and
   `charon-run.sh` finds no `env-registry`, no `bearer_token`, no `PATH=`, and no
   `CHARON_GATEWAY_TOKEN` assignment — only the error text at line 344. Confirms the fix's
   premise.
5. **The gateway returns 302 (not 401) when unauthenticated.** Any preflight that checks
   `http_code == 401` to detect a bad token will miss this. Check "body parses as JSON" or
   `200`, not `401`.
6. **`-free` alias is billed.** `minimax-m3-free` served as `minimax/minimax-m3` with
   `cost: 5.148e-05`, `is_byok: false` — i.e. the free alias resolved to a **paid** route.
   Out of scope here and NOT part of the launch blockers, but it is a live money-path
   observation for whoever owns the free-tier routing lens.

## §7 — GO / NO-GO

**GO**, conditional on the fix doing exactly two things:

- put `~/.local/bin` on PATH (proved sufficient for the `opencode` leg — stripped-env run
  succeeded with PATH as the only addition), and
- **overwrite** `CHARON_GATEWAY_TOKEN` with `bearer_token()`'s derived value before any
  `availability.py` / gateway-curl call.

With both applied by hand in a stripped `env -i` shell, every leg of the droid path executed
green: token derived → `/charon/status` 200/JSON → capped-exclusion rc=0 with real per-model
state → `opencode run --model charon/…` rc=0 returning correct output in 2s. **No third
defect was found beneath the two known bugs** — the one anomaly investigated (openrouter
parked yet models un-capped) resolved as correct chain semantics.

Residual risk is confined to the fix itself: if it sets the token conditionally rather than
overwriting, Run 2 reproduces verbatim and every ticket is detained again.
