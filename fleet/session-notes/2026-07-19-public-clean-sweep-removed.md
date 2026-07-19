
## docs/adr/0016-demand-driven-capability-match.md

Private rig paths dropped from the public ADR (meaning kept inline as neutral prose;
recorded here so the pointers are not lost):

- `fleet/state/POOL-INVESTIGATION.md` — live-config facts + interim edits
  (disable dead providers, drop `opencode-go` fallback); cited in §Context for the
  `deepseek-v4-pro` cost_rank rot evidence. Now reads "internal live-pool investigation".
- `fleet/state/PRICING-TOOLS-EVAL.md` — evidence for the ADOPT-not-build call on the
  price source (LiteLLM `model_prices_and_context_window.json` + OpenRouter `/api/v1/models`
  + changedetection.io). Now reads "the internal pricing-tools evaluation".
- `fleet/board/R46-BALANCE-WIRE.md`, `fleet/board/DRAIN-THEN-PARK.md.parked`,
  `fleet/board/COST-RANK-AUTO.md.parked`, `fleet/board/PRICING-LIMITS-CHECKER.md`,
  `fleet/state/EXHAUSTION-PARK-TICKETS.md` — the §References ticket list. Now reads
  "tracked in the external dev harness's work tracker as R46-BALANCE-WIRE, DRAIN-THEN-PARK
  (parked), COST-RANK-AUTO (parked), PRICING-LIMITS-CHECKER, and the exhaustion-park
  ticket set."

## docs/adr/0010-native-work-engine-substrate.md

- `charon-private/fleet/` (board/claim/done/fleet-droid) + the `[[droid-robot-mode-harness]]`
  memory wikilink in D1. Replaced with "the external bash dev harness (board / claim / done /
  worker-launch)"; the "reference implementation, not the engine of record" point is preserved.
