# RFL-5 — extractive TF / reservoir context compaction (OPT-IN, OFF by default, EXPERIMENTAL)

## Dependencies & sequence
**depends_on: (none) — own module, ships independently.** Owns a NEW file
`src/charon/context_shaper.py` (+ `tests/test_context_shaper.py`) — disjoint from the proxy_server.py
single-writer chain, so it can build in PARALLEL with the SR/RFL proxy_server.py tickets (no shared
owns, no dep to justify). Concurrency-safe against RFL-1..RFL-4. The proxy_server.py request-path WIRING
that invokes this module (behind the opt-in flag) is a DELIBERATE FOLLOW-ON RIDER — folded into the next
proxy_server.py owner AFTER the design is settled + gated — NOT written here, so the design is proven and
off-by-default before any hot-path / message-mutation change lands.

## Why (and why cautious)
RelayFreeLLM comparison R5. Small-context free models 400/truncate on long chats. A stdlib extractive
term-frequency (TF) summarizer can compress old turns into a token-budgeted message so those models can
handle long chats — with NO extra LLM call (pure TF ranking), fitting Charon's stdlib-only constraint.
BUT this is the ONE recommendation that CONFLICTS with Charon's transparent-proxy design principle: it
MUTATES the user's messages, which surprises clients and complicates debugging/caching. So it is ranked
lowest and must be strictly gated.

## HARD CONSTRAINTS (non-negotiable — this is why it's the frontier/Claude pick)
- **OPT-IN, OFF BY DEFAULT.** Enabled only per-request or per-virtual-key; default behavior is the
  transparent passthrough — messages are NOT touched.
- **NEVER mutate user messages by default.** With the feature off, the messages array passes through
  byte-for-byte.
- **STATELESS.** Operate IN-REQUEST on the messages array; do NOT introduce a conversation store. Charon
  stays stateless (simpler, cacheable, no PII-at-rest).
- **DISCLOSE when applied** (e.g. a response header / marker) so a client can tell compaction happened.
- Stdlib only; no third-party imports.

## What to build (this ticket = the MODULE only)
`src/charon/context_shaper.py` — a self-contained, unit-tested compaction module:
- Input: a messages array + a token budget (the resolved model's `context_window`, already captured in
  metadata) + config (mode, reserved-turns N).
- **Extractive TF summarizer:** term-frequency sentence scoring + position bias, greedy to a token
  budget — no LLM call.
- **Reservoir mode:** keep the last N turns VERBATIM + summarize the older turns into a single budgeted
  system/context message.
- Invoked ONLY when enabled AND the request would exceed the model's `context_window`; otherwise returns
  the messages UNCHANGED.
- Pure function surface (messages in -> messages out) so it is trivially unit-testable with NO
  proxy_server.py dependency.
Leave a documented `## Wiring rider` note in the module/tests describing exactly where the future opt-in
call site goes in the proxy_server.py request path (behind the flag, with disclosure) — but do NOT edit
proxy_server.py here.

## Acceptance / tests (`tests/test_context_shaper.py`)
- With the feature OFF (default), messages pass through UNCHANGED (identity) — prove no mutation.
- When enabled AND over budget: output fits the token budget; the last N turns are preserved verbatim
  (reservoir); older turns are summarized (extractive), and the result is deterministic for a fixed input.
- When enabled but UNDER budget: messages pass through unchanged.
- TF scoring ranks higher-signal sentences above filler (a focused unit test on the ranker).
- Full suite green.

## Red-proof
Include a test that FAILS if the default path mutates messages (identity assertion) — the off-by-default
invariant must be gate-enforced.

## CONSTRAINTS
- **Owns:** `src/charon/context_shaper.py`, `tests/test_context_shaper.py` ONLY. Do NOT touch
  proxy_server.py (wiring is a follow-on rider).
- Stdlib only; provider/agent-agnostic; product-clean; no `/home/stack` paths or dev-meta.
- Mark the module clearly EXPERIMENTAL / OPT-IN in its docstring.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_context_shaper.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/context_shaper.py && mypy src/charon/context_shaper.py
```

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
