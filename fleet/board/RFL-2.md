tier: strong
branch: feat/rfl-2-chat-playground
depends_on: RFL-3
real-dep: RFL-3 build (single-owner file src/charon/proxy_server.py) — proxy_server.py is the
  single-writer bottleneck (chain … SR-13 -> RFL-1 -> RFL-3). RFL-2 adds a new `/chat` route +
  embedded HTML/JS to the SAME file that serves the console/setup pages, so it rebases onto RFL-3's
  file, never a concurrent second writer. Shared-file sequencing, JUSTIFIED (not merge-order).
  Transitively orders RFL-2 after the whole SR chain via RFL-3 -> RFL-1 -> SR-13.
owns: src/charon/proxy_server.py, tests/test_chat_playground.py
prompt: /home/stack/charon-private/prompts/rfl-2.md
scope: RelayFreeLLM comparison R2 — a `/chat` playground page served by the existing console. Inline
  static HTML+JS (no framework, no external assets — CSP/stdlib clean), served from proxy_server.py like
  the existing `/charon` dashboard + `/charon/setup`: prompt box, SSE streaming output, a model picker,
  and — the headline — WHICH provider/model actually served the request (read the X-Charon-* / served
  model id). Calls Charon's OWN `/v1/chat/completions`. Reuse the token-gate already on the console.
  Zero-setup way for a fresh-install user to confirm "is my gateway working / who served this?" without
  wiring a client — aligns with the production-readiness north-star. Suggested agent: DeepSeek V4-Pro
  (strong tier) — WHY: self-contained inline HTML/JS + one GET route, well-specced UX with a low blast
  radius (console only); no security/concurrency subtlety — save Claude for design-heavy work. Stdlib +
  self-contained-assets guardrail (no CDN/external fetch); CI gate is the backstop.
