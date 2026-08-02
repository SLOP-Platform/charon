# COST-PER-TASK-REPLAY review log

## Decision record

- **Metric**: cost per accepted task = total spend / tasks passing adversarial review with no changes required
- **Quality floor**: "no changes required" is load-bearing — without it, cheap degenerates into fails cheaply (6 of 8 PRs bounced in one review round)
- **Provider identity**: quantization, hardware, hidden prompts make provider part of the model identity for cost
- **No synthetic suite**: selection is over real landed tickets, not synthetic S0-S6 which was ruled "benchmark is NOT a valid ranker"
- **Ledger as source of truth**: Checkpoint.usage.cost_usd is authoritative, not metering callback

## Scope notes

- Owned files: the state design doc and this review log only
- No code changes — P0 is design only (ADR-style spec)
- Feeds GRADE-MODEL-PROVIDER-PAIR and routing sort key
- SPEND-METRIC-TRUSTWORTHY per-provider attribution consumed when available
