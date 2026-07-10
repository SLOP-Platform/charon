# LongCat-2.0 add via OpenRouter — 4-LOM — STOPPED (not found)

Date: 2026-07-07
Refs: `fleet/POOLS-EDIT-PLAN.md` §5, `fleet/scratch/zen-remove-report.md`
Container: `charon-gateway-1` (never touched — task stopped before any write)

## Task

Add model `LongCat-2.0` (Meituan's LongCat family) to the live Charon gateway
via OpenRouter (already an integrated provider), using the same setup-API +
backup pattern as recent pool edits.

## Step 1 — catalog lookup (READ-ONLY, no writes made)

Queried the live OpenRouter catalog from the 4-LOM host (has confirmed
internet egress since it already proxies to OpenRouter in production):

```
ssh -i ~/.ssh/4lom stack@10.0.1.60 "curl -s 'https://openrouter.ai/api/v1/models'"
```

Result: **343 models returned**, response verified as a legitimate live
catalog (alphabetically sane range from `ai21/jamba-large-1.7` through
`~openai/gpt-mini-latest`, includes well-known families like
`anthropic/claude-*`, `z-ai/glm-*`, `moonshotai/kimi-*`, etc.).

Searched all 343 ids and names for:
- substring `longcat` (case-insensitive) — **0 matches**
- substring `meituan` (case-insensitive, id and name) — **0 matches**
- broad substring `cat` anywhere in any model id — **0 matches**

**Conclusion: LongCat-2.0 (Meituan) is NOT present on OpenRouter's current
catalog.** No id was fabricated or guessed.

## Outcome — STOP, per task instruction

Per the task brief: "If there is NO LongCat on OpenRouter, STOP and report
that (it may be HuggingFace-only, which would need HF activated first) —
do not guess/fabricate an id."

Stopping here. **No backup was taken and no config was written** — nothing
on `/data` was touched, container was not restarted, no setup-API calls
were made (Steps 2 and 3 of the task are inapplicable since Step 1 failed
its precondition).

## Next options for the operator

1. Confirm whether LongCat-2.0 is available via a different provider
   Charon could integrate (e.g. HuggingFace Inference, or Meituan's own
   API if it has one) — would need that provider activated/onboarded
   first, which is out of scope for this task.
2. Re-check OpenRouter later — LongCat may land on OpenRouter in the
   future; this lookup only reflects the catalog as of 2026-07-07.
3. If the operator has a different exact OpenRouter id in mind that isn't
   surfacing under these substrings, supply it directly and it can be
   verified with a single targeted lookup before any write.
