## 2026-06-26 — Gateway P2 failover independent review — reconciled

Verdict: **sound to keep** — the two subtle pillars verified correct: R10a cost
accounting (discarded attempts never billed; served billed exactly once, incl. the
streaming path) and R1 streaming transparency (no client bytes before the downgrade
decision; head prepended intact; no hang when no `model` within the 64 KiB cap).
Two MED + two LOW gaps fixed:

- **[MED] Streaming `resp.read` loops were not exception-guarded** — an interrupted/
  malformed upstream stream would crash `_handle` with no client response and no
  failover. **Fixed:** the head loop is wrapped — a pre-commit stream error is treated
  like a failed attempt and fails over (or 502s if terminal); the commit loop swallows
  read errors (headers already sent → partial is unavoidable).
- **[MED] The streaming path had ZERO test coverage.** **Fixed:** added an SSE mock +
  tests — streaming served (usage billed once), streaming pre-commit downgrade failover
  (A's bytes never reach the client; only B billed — R10a for streams), a stream with
  no `model` is served not hung, and the 402/404 failover buckets.
- **[LOW] Upstream responses weren't explicitly closed** → fd reliance on GC.
  **Fixed:** per-attempt `try/finally: resp.close()`.
- **[LOW] A 404 cooled the whole provider** (contradicting "drop the model, not the
  provider"). **Fixed:** cooldown is set only for `exhausted` (429/402/503), not
  `dropped` (404).
- **[LOW, noted not fixed] Exact-match downgrade detection** false-positives when a
  provider honestly answers a versioned id (`gpt-4` → `gpt-4-0613`). Pre-existing in
  the observer; recorded in ADR-0005 R10 as a P3+ refinement (prefix/normalized
  compare) — low risk while pools are explicit.
- **Gate after fixes:** 136 passed, ruff clean, mypy clean (29 files), boundary OK.
