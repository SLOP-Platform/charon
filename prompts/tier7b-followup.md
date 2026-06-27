# TIER7B-FOLLOWUP — stub prompt

This ticket was built via a **manager-driven sub-agent** (PR #59, merged), not through the
normal claim flow, so its work-spec was inlined directly in the sub-agent's prompt rather than
authored here.

Work delivered in PR #59:
- Multi-member within-tier ordering guard test (free-first / cost_rank selection through the
  per-tier warm-map path).
- Proxy-teardown-on-setup-error hardening in `src/charon/api.py`.

This stub exists only to satisfy `validate_board.sh` for the completed ticket — `board/TIER7B-FOLLOWUP.md`
references this path via its `prompt:` line, and the reference would otherwise dangle (RED
missing-prompt). The ticket is DONE (`state/done/TIER7B-FOLLOWUP`).
