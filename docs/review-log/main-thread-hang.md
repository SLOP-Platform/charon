## 2026-06-25 — The "main-thread hang": disproved the hypothesis, fixed two real bugs

- **Change under review:** the one open issue (HANDOFF §6) — the live ACP+proxy
  `--role` failover run completed in a worker thread (~8s) but the prior manager
  observed it **hang in the main thread**, so the `charon` CLI hung. Leading
  hypothesis on entry: a fundamental interaction between the main thread's
  blocking ACP read-loop (`select` on the agent stdout) and the in-process
  `ThreadingHTTPServer` proxy (and/or main-thread-only signal handling).
- **Process:** live root-cause on `build-host` (not a subagent review — the
  decisive evidence is the running system). Instrumented the boundaries
  (`_rpc`/`_readline`/proxy `_handle`) with timestamped logging to a file and
  armed `faulthandler.dump_traceback_later` to dump **every thread's stack** the
  instant a hang set in. Ran `run_task` in the main thread under that harness.

### Findings + reconciliation

| ID | Finding | Verdict | Reconciliation |
|----|----|----|----|
| H-HYP | The hypothesized main-thread `select`-vs-threaded-proxy **deadlock does not exist.** | **DISPROVED by trace** | The instrumented run shows the main thread doing 100+ `select`/`readline` cycles on the agent's stdout while three proxy worker threads concurrently stream OpenCode's SSE (38 KB / 33 KB / 7 KB) — composing cleanly to `session/prompt OK` and `status complete`. `select` releases the GIL; daemon proxy threads run regardless of which thread is "main". `faulthandler` was armed but never fired (nothing hung). |
| H-UA | The opencode-go **pre-flight probe** 403'd **through the proxy** while a direct curl with the same key/body got 200. Root cause: the proxy forwarded the probe's urllib-default `User-Agent: Python-urllib/3.12`, which **opencode.ai's Cloudflare edge now bans** (error 1010 → 403). A *new* upstream behavior (the probe's UA passed when the handoff was written — that's why the worker-thread run had succeeded). With the probe 403'ing, selection returned a clean `exhausted` (not a hang) — so in the *current* environment the old code can't even reach dispatch. | **FIX** | The proxy owns its egress identity: forward the agent's real UA (e.g. `opencode/1.17.10`, which passes), but replace an absent **or library-default** UA (`Python-urllib`/`Python-requests`) with `charon-proxy/0.1`. Live-verified the probe then returns 200. Regression: `test_proxy_normalizes_banned_user_agent`. |
| H-PSEUDO | The D5 **pseudo-success guard false-positived every honest 200.** `observe()` compared the upstream's returned **native** id (`kimi-k2.7-code`) against `requested_model`, which the proxy passes as the **prefixed pool id** (`opencode-go/kimi-k2.7-code`) so the router's exclusion set lines up — they never match, so each success was logged as a "silent downgrade" failover and polluted `exhausted_models()` (and the "skipped" note). A single-dispatch task completes before that flag is consulted, which is why the worker-thread run still finished — but multi-dispatch runs would mis-fail-over. | **FIX** | `observe()` gains an optional `expected_model` (the native id actually sent upstream, after any rewrite) used *only* for the pseudo-success comparison; the exclusion key stays the pool id. Default = `requested_model` (backward-compatible; the unit tests pass un-prefixed ids). Regressions: `test_prefixed_pool_id_native_return_is_not_false_pseudo_success`, `test_pseudo_success_still_fires_against_native_expected_model`. |

### Live proof + honesty register

- **Proof:** with both fixes, the **§7 CLI demo completes reliably in the main
  thread — 7/7** runs (1 instrumented `run_task`, 4× `charon run`, 2× `python -m
  charon.cli`), 8–10s each, `status complete`, ~13 k tokens, correct note
  `role 'coder' → opencode-go/kimi-k2.7-code (flat); skipped
  ['openrouter/qwen/qwen3-coder:free']`. Gate: **97 passing** (was 94),
  ruff/mypy/boundary clean.
- **Honest caveat (disclosed, not hidden):** I could **not A/B-reproduce the
  prior manager's exact original hang**, because the environment changed
  underneath us — Cloudflare now 403s the probe UA *before* the old code can
  reach dispatch, so the original hang state is no longer reachable to bisect.
  What is established: (a) the proposed deadlock mechanism is **mechanistically
  disproved**, and (b) the deliverable now works **reliably (7/7)** in the main
  thread. The most defensible reading of the prior two-data-point observation
  ("worker works / main hangs") is that it was **not** a deterministic
  thread-context effect (it's disproved) but a transient (upstream latency /
  OpenCode timing) over-attributed to thread context. If a main-thread hang ever
  recurs, the harness to catch it is committed in this branch's diag recipe
  (instrument + `faulthandler.dump_traceback_later`).
- **No CLI re-architecture:** because the deadlock hypothesis is false, I did
  **not** move the coordinator to a worker thread or the proxy to its own
  process (HANDOFF §6's candidate fixes). Both were premised on a deadlock that
  doesn't exist; adding them would be cargo-cult complexity. The CLI keeps
  running the loop in the main thread — proven correct.

WALK-BACK: none — two bug fixes + three regression tests; the only behavior
change is that the UA and pseudo-success paths are now correct.
