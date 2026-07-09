# RFL-2 — chat playground page in the web console (`/chat`)

## Dependencies & sequence
**depends_on: RFL-3 — Wave RFL, on the proxy_server.py single-writer chain.** `proxy_server.py` is the
single-writer bottleneck (chain … SR-13 -> RFL-1 -> RFL-3). RFL-2 adds a new `/chat` route + embedded
HTML/JS to the SAME file that serves the `/charon` dashboard and `/charon/setup`, so it MUST rebase onto
RFL-3's file, never write it concurrently (`real-dep: RFL-3 build`, single-owner file). Transitively
ordered after the whole SR chain via RFL-3 -> RFL-1 -> SR-13. RFL-4 sequences after RFL-2.
Concurrency-safe vs RFL-5 (disjoint owns).

## Why
RelayFreeLLM comparison R2. Charon has an admin console + setup GUI but NO interactive chat page. Home
users need a zero-setup way to confirm "is my gateway working / who served this request?" without wiring
up a client. Cheap, high-perceived-value, great for the fresh-install experience (production-readiness
north-star).

## Shared context (grounding for a fresh session)
- The console is inline HTML/JS served from `proxy_server.py` (`do_GET` ~:377; the `/charon` dashboard
  and `/charon/setup` page ~:575). Routes are dispatched in `_handle` / `do_GET`.
- The console is token-gated (bearer via `?token=` for the read-only dashboard) — REUSE that gate.
- Charon exposes its own OpenAI-compatible `/v1/chat/completions` (SSE streaming supported).
- The served model / downgrade is surfaced via `X-Charon-*` response headers and the response `model`
  field — read that to attribute WHICH provider/model served the request.

## What to build (proxy_server.py)
A self-contained `/chat` page (inline static HTML + vanilla JS, NO framework, NO external/CDN assets —
keep it CSP-safe and stdlib-served):
- Prompt box + send; streams the response via SSE from Charon's OWN `/v1/chat/completions`.
- Shows WHICH provider/model actually served the request (from the response `model` id / `X-Charon-*`
  headers) — this is the headline value.
- A model picker (populated from `/v1/models` or the console's existing model list).
- Reuse the existing console token gate (same `?token=` / bearer mechanism).
- Optional: light/dark toggle. Image drag-drop is OPTIONAL and out of scope unless trivial.
Additive: a new route only; no change to `/v1/*` or existing console routes.

## Acceptance / tests (`tests/test_chat_playground.py` + regression)
- `GET /chat` (authorized) returns 200 `text/html` with the inline page; unauthorized is gated like the
  rest of the console.
- The page markup references Charon's own `/v1/chat/completions` and renders the served-model attribution
  (assert on the served-model element / header read in the returned HTML/JS).
- No external asset URLs in the page (self-contained — grep the response for `http`-scheme asset refs).
- Full suite green.

## Red-proof
Include a test that FAILS if the `/chat` route is not registered (404) so the gate proves the feature is
live.

## CONSTRAINTS
- **Owns:** `src/charon/proxy_server.py`, `tests/test_chat_playground.py` ONLY.
- Stdlib only; self-contained assets (no CDN/external fetch/fonts/images); provider/agent-agnostic;
  product-clean; no `/home/stack` paths or dev-meta.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_chat_playground.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/proxy_server.py && mypy src/charon/proxy_server.py
```
