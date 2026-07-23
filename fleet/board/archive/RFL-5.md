repo: charon
tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: greenfield-feature
parked: true
note: PARKED for the off-Claude fleet — scope (below, L20-23) says "Reserve Claude; do NOT route to an open model". Off-Claude frontier tabs must SKIP this. Also a single net-new module (context_shaper.py + its test = one domain) so it is NOT parallelizable; the parallelizability-gate refusal was a false trigger. A Claude session / the operator builds this one.
branch: feat/rfl-5-context-compaction
depends_on:
owns: src/charon/context_shaper.py, tests/test_context_shaper.py
prompt: /home/stack/charon-private/prompts/rfl-5.md
scope: EXPERIMENTAL / OPT-IN, OFF BY DEFAULT (RelayFreeLLM comparison R5). Stdlib extractive
  term-frequency (TF) + reservoir context compaction for long chats on small-context free models: when
  a request would overflow the resolved model's `context_window`, compress OLD turns into a
  token-budgeted summary (TF sentence-ranking + position bias, greedy to budget — NO extra LLM call),
  "reservoir" = keep last N turns verbatim + summarize the rest. HARD CONSTRAINT: this conflicts with
  Charon's transparent-proxy design — it MUST be gated behind an explicit per-request/per-virtual-key
  opt-in, OFF by default, and MUST NOT mutate user messages by default. Operate IN-REQUEST on the
  messages array (no conversation store — stay stateless); disclose when applied. This ticket ships the
  self-contained, unit-tested `context_shaper.py` module ONLY; wiring it into the proxy_server.py
  request path is a deliberate FOLLOW-ON rider (behind the flag, folded into the next proxy_server.py
  owner) so the design is settled + gated before any hot-path/message-mutation change. Owns are disjoint
  (new module only) — no dep on the proxy_server.py chain; can build in parallel. Suggested agent:
  Claude Opus 4.8 (frontier tier) — WHY: the ONE genuinely tricky/design-heavy pick — it breaks the
  transparent-proxy invariant, mutates user content, and must be carefully gated + disclosed; wrong
  defaults here are actively harmful and must pass the adversarial gate. Reserve Claude; do NOT route to
  an open model. Prompt with the anti-overplanning / "simplest gated thing that works" snippet.
