# Test-gap audit — why green tests missed the cline-envelope defect (and its class)

Read-only investigation for the Charon fleet manager · 2026-07-09 · product tree `/home/stack/code/charon`.
Scope: test-quality / observability audit of the proxy response path. No code/tests edited.

---

## Q1 — Coverage gap (the blind spot, file:line)

**Root cause: every mocked upstream in the suite returns a canonical OpenAI body, so the shape
assumption the product makes is never challenged.** The tests mirror the production code's
expectation instead of an adversarial provider — self-fulfilling by construction.

- `tests/conftest.py:54-60` — the shared `mock_upstream` fixture ALWAYS emits
  `{"id","object":"chat.completion","model","choices":[{message:{content}}]}`. This is the single
  most-reused upstream in the suite; it can never produce a non-OpenAI envelope.
- Every inline mock handler does the same canonical shape:
  `tests/test_proxy_server.py:43,147,222,246,487,595,986`; `tests/test_gateway.py:55`;
  `tests/test_gateway_failover.py:34,200`; `tests/test_fallback_provider.py:259`;
  `tests/test_agent_launch_routing.py:47`; `tests/test_tier_lifecycle.py:53`;
  `tests/test_run_task_routing.py:47`; `tests/test_console_provider_mgmt.py:52`.
- All client-side assertions read `body["choices"][0]["message"]["content"]`
  (`test_proxy_server.py:82,279,451,515,546`, `test_gateway.py:183`, `test_gateway_failover.py:120`,
  `test_fallback_provider.py:307`, …). They assert the content INSIDE choices — never that a
  top-level `choices` key exists at all given a hostile upstream body. Because the mock always
  supplies choices, the assertion passes trivially.

**Where the product actually relays / interprets the body (all shape-naive, all untested for non-OpenAI shape):**
- `src/charon/forwarder.py:265` (non-200 relay), `:271-317` (200 non-stream: `_drain` then
  `handler._write(body_bytes)` VERBATIM), `:367-397` (200 stream relay). The forwarder writes the
  upstream bytes back with zero envelope adaptation — this is the exact line the cline bug rides.
- `src/charon/proxy_response.py:18-49` (`_extract`) reads only TOP-LEVEL `model`/`usage` from JSON.
- `src/charon/proxy.py:316` `returned = (body or {}).get("model")` and `:326`
  `_gateway_usage(body)` → `proxy.py:120` `(body or {}).get("usage")`. Both read top-level.

**Consequence on a cline `{"data":{...},"success":true}` body (the real defect):**
1. `forwarder` relays it verbatim → client sees no top-level `choices` (breakage).
2. `classify` sees `model=None` → downgrade detection blind; `usage=None` → `cost_usd=0` recorded →
   spend-limiter + METER **undercount to zero** for every non-stream cline completion. This quiet
   metering half is arguably worse than the visible breakage.

**Specific blind spots (providers exercised end-to-end vs. only via self-mirroring mocks):**
- OpenAI-shape JSON non-stream: covered (but only the happy shape).
- SSE/streaming OpenAI-shape: covered (`test_proxy_server.py:306,396`, `test_gateway_failover.py:200`).
- **Non-OpenAI envelope (cline `data/success`): ZERO coverage — anywhere.**
- **Anthropic-wire / any `wire != openai` RESPONSE body shape: no end-to-end shape test** (request-side
  translate is tested; the response relay is not shape-checked).
- **The `response_normalizer` post-hook is fed the WHOLE body JSON string**
  (`forwarder.py:296-300` passes `body_bytes.decode()`), yet `response_normalizer.py`'s docstring
  says it operates on `choices[0].message.content`. STANDARDIZE_MD runs regex over the entire JSON
  blob. Latent secondary bug, also untested (bonus finding, ticket-worthy).

---

## Q2 — Systemic pattern (from the 6+ reviews of record)

Categorizing what ADVERSARIAL REVIEW caught that green pytest did not:

| Defect class | Examples (reviews) | Why tests missed it |
|---|---|---|
| **Shape/contract at a boundary the mock owns** | cline envelope (this session); response-normalizer whole-body | The test supplies the mock that also defines the contract → self-fulfilling |
| **Auth-surface / boundary bypass** | sr13 F1: `charon_sess` cookie reaches the billed forwarder via unmatched `/charon/*` | No test drove a `/charon/*` path that falls THROUGH both routers to the money path |
| **Untested new subsystem** | bench-reground "re-grounding is UNTESTED"; ticket-assign n=1 collapse | Feature shipped with no test exercising its core transform at all |
| **Latent-until-config edge** | pff-p1 P5: probe paths still send banned UA; cline latent until a non-stream client | Tests only exercise the configured happy path, never the "fires when X provider/flag" edge |
| **Cost/metering correctness** | cline usage→0 undercount; sr6/v2-scoring cost & ranking bugs | No test asserts the CLIENT/METER-observable cost given a hostile/edge body |
| **CI-base rot** | sr6: master base was CI-RED (F821 forward-refs) while "green" was assumed | Green was asserted, not verified against the merge base |

**Recurring reason green ≠ correct here:** the suite validates the product against *mocks the product
authors*, so any assumption shared by code and mock (envelope shape, top-level keys, the happy path
being the only path) is invisible. Tests assert on values *inside* a structure the mock guarantees,
never on the *existence of the client-observable contract* under an adversarial input. Reverting the
(future) adapter changes nothing a test sees, because no test presents a body the adapter would need
to fix. This is precisely the doctrine trigger: **a test that still passes when the change is reverted
proves nothing.**

---

## Q3 — Fail-on-revert regression-test proposals (prioritized)

All assert on the **client-observable contract** (top-level `choices`/`usage`), fed by a mock that
returns a NON-canonical body — so each one is RED today / RED on adapter revert, GREEN only with the fix.

**P0 — directly catch the cline defect:**
1. `test_response_adapter_cline_envelope_yields_top_level_choices`
   (new `tests/test_response_adapters.py`). Unit: `ClineAdapter().normalize_response({"data": <openai obj>, "success": True})`
   returns a dict with top-level `choices` (list) AND top-level `usage` (dict), and the content
   matches the inner object. Idempotent on already-canonical input (call twice == once). FAILS on
   revert because passthrough leaves `data`/`success` and no top-level `choices`.
2. `test_proxy_nonstream_cline_shaped_upstream_returns_openai_body`
   (in `test_proxy_server.py`, or new `test_forwarder_shape.py`). END-TO-END: mock upstream returns
   `{"data":{"model":"glm-5.2","choices":[{"message":{"content":"ok"}}],"usage":{...}},"success":true}`,
   provider preset wired `adapter="cline"`. Assert the CLIENT gets `body["choices"][0]["message"]["content"]=="ok"`.
   This is the test the conftest mock structurally cannot express today. FAILS on revert (client sees
   `data`/`success`, KeyError on `choices`).
3. `test_cline_nonstream_usage_is_metered_not_zero`
   Same upstream as #2 with a real `usage`. Assert `note_request`/ledger records `cost_usd > 0` (or the
   observed `usage` is non-empty) — locks the silent-undercount half. FAILS on revert (`_extract`/`classify`
   read top-level usage → 0).

**P1 — harden the classes from Q2:**
4. `test_cline_streaming_stays_clean` — SSE cline body is already OpenAI-shaped; assert the adapter is a
   no-op on the stream path (guards against the adapter corrupting the working streaming leg).
5. `test_charon_unmatched_path_with_session_cookie_is_rejected` (auth-surface, sr13 class) — POST
   `/charon/<not-a-real-endpoint>` with only `charon_sess` cookie → 401, never reaches the forwarder.
   FAILS on the pre-sr13 fall-through.
6. `test_probe_paths_send_browser_ua` (pff-p1 P5 class) — assert `validate_provider_key` /
   speculative_execution / routing_proxy egress carries `BROWSER_UA`, not `python-urllib`/`charon-proxy`.
7. `test_response_normalizer_receives_content_not_whole_body` — assert the post-hook only touches
   `choices[0].message.content`, not the JSON envelope (locks the secondary latent bug).

Emphasis: proposals 2, 3, 5 assert on what a real client / meter observes, not on an internal mock —
they are the ones that structurally cannot pass while the bug exists.

---

## Q4 — Mechanization (cheap gate that kills the whole class)

**Contract test: "every wired provider must produce OpenAI-shaped output through the proxy."**
Add `tests/test_provider_response_contract.py` that is parametrized over every `ProviderPreset` in
`providers.py`. For each preset, spin the proxy against a mock upstream that returns THAT preset's known
raw shape (canonical for identity providers; the wrapped `data/success` shape for `adapter="cline"`, etc.),
POST a non-stream completion, and assert the CLIENT response has a top-level `choices` list and a
top-level `usage` dict. New provider or new adapter with no declared shape fixture → the parametrization
fails loudly, forcing the author to declare (and thereby test) the envelope.

Pair it with a tiny structural lint (extends the existing `check_test_patterns` gate): flag any proxy/
forwarder test whose upstream mock body is authored inline AND whose assertion only reads *inside*
`choices` — i.e. detect self-mirroring mocks — nudging toward the contract fixture instead. Cheap,
stdlib, runs in the existing `charon.cli gate`.

This turns "does the proxy speak OpenAI to the client?" from an assumption into a per-provider invariant
that a revert or a new mis-shaped provider cannot pass.

---

## Ticket recommendations

- **TICKET (P0):** `response_adapters.py` + `ClineAdapter` + tests #1–#4 — implements ADR-UNIVERSAL-RESPONSE-ADAPTER; ships with fail-on-revert tests. (Supersedes parked CLINE-UNWRAP-SHIM.)
- **TICKET (P0-mech):** parametrized provider response-contract test (Q4) + self-mirroring-mock lint in `check_test_patterns`.
- **TICKET (P2):** fix + test the `response_normalizer` whole-body feed bug (`forwarder.py:296-300`) — proposal #7.
- **Already-closed cross-checks (verify, don't rebuild):** sr13 F1 auth fall-through (#5) and pff-p1 P5 UA (#6) — add the named regression tests if their fixes lack fail-on-revert coverage.
