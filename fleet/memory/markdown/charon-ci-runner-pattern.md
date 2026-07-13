---
description: CI runner is chosen via the CI_RUNNER repo variable (A-Clean) — forks auto-fall back to hosted; upstream uses self-hosted self-hosted-runner
metadata: 
name: charon-ci-runner-pattern
node_type: memory
originSessionId: dbc15100-af3f-415f-ae56-66e13a77d57e
type: reference
tags: [charon, ci]
last_referenced: 2026-07-13
---
DECISION (operator-approved 2026-06-27): Charon CI workflows pick their runner via a **repo
variable**, not a hardcoded `[self-hosted, self-hosted-runner]` pin (which left forking contributors with no
CI — audit NIT-1). Pattern ("A-Clean"):

```yaml
runs-on: ${{ fromJSON(vars.CI_RUNNER || '"ubuntu-latest"') }}   # CI_RUNNER set in repo Settings → Variables
```

- Upstream sets `CI_RUNNER = ["self-hosted","self-hosted-runner"]` once in repo Settings → Variables.
- **Forks don't inherit repo variables**, so they automatically fall back to `ubuntu-latest`
  (free hosted) → forkers get working CI. No fork-check logic in the YAML.

GOTCHA / why this memory exists: if `CI_RUNNER` is ever unset/deleted, **upstream silently
reverts to hosted** (loses the fast self-hosted-runner runner) with no error — so the variable's existence +
purpose must stay documented (inline YAML comment + a DECISIONS.md row + a CONTRIBUTING note).
Chosen over "A-Conditional" (per-workflow fork check) for maintainability: swap/rename runners or
go all-hosted by flipping ONE variable, no code edit. A plain `pipx install` user is unaffected —
this is contributor-CI only. Relates to [[charon-production-readiness-mindset]],
[[charon-hosting-and-runner]].
