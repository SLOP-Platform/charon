# preflight-tasks/canary/ — STAGE-1 leg canary task set

Driven by `fleet/benchmark/leg-preflight.sh`. Design of record:
`fleet/board/LEG-PREFLIGHT-CANARY.md`, reference impl
`fleet/state/leg-canary-prototype.py`, adversarial review
`fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md` (F6, F14).

This is the FAST (seconds) due-diligence gate, not the 8-minute honest-battery/
dogfood battery (`preflight-tasks/`, one level up). Its only job is to answer,
per (model, LEG): reachable? serves a real working model (not a stub/degraded/
wrong model)? how fast? — cheaply, before spending the expensive full test on
a dead leg (motivating incident: minimax-m2.7 burned ~24min on a dead leg with
no pre-check, 2026-07-15).

## Tasks (`manifest.tsv`)

- `bal-parens` (kind=exec): the balanced-parentheses coding one-liner from
  the prototype. The candidate's code is executed in a SANDBOXED subprocess
  (`exec_check.py`, F14) — never `exec()`'d in the preflight script's own
  process — with a CPU/address-space/no-fork resource ceiling and a wall-clock
  timeout, and a stripped environment.
- `lcm-bound` (kind=exact): a short arithmetic-reasoning question with one
  unique correct integer answer (smallest common multiple of 6 and 15 that
  is > 100 -> 120). Scored by exact string match after trimming, never by
  the model's own claim of correctness.

Both run at `temperature=0` with a small `max_tokens` budget so the whole
per-leg canary finishes in single-digit seconds against a healthy leg.

## Why these two tasks discriminate

A stub/degraded/heavily-quantized backend tends to fail in one of two
observable ways this pair is chosen to catch: (a) it emits code that doesn't
actually satisfy the balanced-parens contract (wrong logic, or malformed code
that fails to exec at all), or (b) it can't reliably follow "reply with ONLY
the integer" and/or gets the arithmetic wrong. Neither check trusts prose —
both are exec/exact-match, matching the ticket's "never trust the model's
word" rule (LEG-PREFLIGHT-CANARY.md line 30).

## Known-weak control

The task set is only trustworthy if it actually scores a weak backend low.
`fleet/tests/leg-preflight.test.sh` exercises this hermetically (a stubbed
leg that returns wrong/garbled content must rank DEGRADED-serves-wrong, never
HEALTHY). Operationally, when adding a new canary task, sanity-check it once
against a genuinely weak/tiny/quantized model id (not swept in CI — that
costs real provider credit) and confirm `canary_score` drops before trusting
the task as a discriminator.

## Non-Anthropic only

No task prompt, checkfile, or manifest row here references an Anthropic/
Claude model id (`sg-never-anthropic`); the roster of model-or-leg ids to
probe is supplied by the caller of `leg-preflight.sh`, which itself refuses
any `*claude*|*opus*|*sonnet*|*haiku*|*anthropic*` id (see that script's
`is_anthropic` guard).
