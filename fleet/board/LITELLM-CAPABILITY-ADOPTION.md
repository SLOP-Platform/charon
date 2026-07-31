repo: charon
tier: frontier
difficulty: 4
work_class: design-review
priority: 0
branch: design/litellm-capability-adoption
depends_on:
owns: docs/adr/0021-litellm-capability-adoption.md, ADOPT-MAP.md, tests/test_litellm_capability_map.py
serial_justified: |
  ONE decision register: every unused Router capability must be dispositioned in a single pass
  against a single set of criteria. Splitting it produces inconsistent verdicts (one sub-ticket
  adopts fallbacks while another declines the routing_strategy that fallbacks depends on) and
  leaves no coherent record of WHY each capability was taken or declined.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  GLM and Kimi are OFFLINE (operator action #14). Verified-funded legs as of 2026-07-31:
  deepseek-v4-pro, minimax-m3-together, devstral-2512, gemini-2.5-pro. Own worktree.
source: |
  Operator, 2026-07-31: "is being fully wired in SG the same as fully using and implementing all
  its features/capabilities that made logical sense?" Answer: no. Measured gap below.
note: |
  ## THE MEASURED GAP (verified — confirm, do not re-derive)
  `litellm.Router.__init__` accepts **52 parameters**. `src/charon/litellm_plane/litellm_router.py`
  `make_router()` passes **five**: `model_list`, `cooldown_time`, `allowed_fails`, `num_retries`,
  `retry_after`.

  So even once GW-CUTOVER-LIVE-WIRE puts Router on the live path, we would run a maintained router
  in roughly the shape of the hand-rolled one it replaces. **Wired is not the same as used.**

  ## THIS IS NOT NEGLIGENCE — IT IS AN UNFINISHED STAGED ADOPTION
  `ADOPT-MAP.md:65` "Slice boundary" deliberately scoped slice 1 to default-OFF parity so the live
  money path stayed byte-identical, with fail-on-revert tests, an e2e, and a runnable dogfood. The
  deferrals were named, "documented, NOT silently dropped". They were then never scheduled. THIS
  TICKET IS THAT SCHEDULING. Do not treat the original slice as a mistake — treat it as stage 1.

  ## THE UNUSED CAPABILITIES MAP ONTO REAL OBSERVED FAILURES
  | Capability | Failure it addresses (all observed on this rig) |
  |---|---|
  | `fallbacks` / `default_fallbacks` / `max_fallbacks` | `glm-5.2` exists as SIX separate catalog entries (`-or`/`-nw`/`-ng`/`-cline`/`-hf`/`-go`) that routing cannot reach from one name |
  | `provider_budget_config` | the 402 "all providers exhausted" outage — budget-aware routing around a drained provider |
  | `routing_strategy` + `routing_strategy_args` | we hand-roll `cost_rank` ordering |
  | `context_window_fallbacks` | `deepseek-v4-flash` silent truncation at a 48-request session cap |
  | `enable_health_check_routing`, `health_check_*` | legs that pass a 1-shot probe then collapse under session load |
  | `enable_weighted_failover` | the SOLE-LEG GUARD case (199 hits in one log window) |
  | `enable_tag_filtering` | tier / capability routing |
  | `cache_responses`, `cache_kwargs` | direct cost reduction |
  | `retry_policy`, `model_group_retry_policy` | per-group retry instead of one global `num_retries` |

  ## WHAT TO PRODUCE — A DISPOSITION FOR EVERY ONE
  Enumerate ALL 52 params programmatically (`inspect.signature(litellm.Router.__init__)` — do not
  hand-copy this list, it will drift). For EACH, exactly one verdict:
  - **ADOPT** — with the config surface it maps to and the Charon behaviour it REPLACES (name the
    hand-rolled code that gets deleted)
  - **DECLINE** — with the concrete reason. A real example already exists and must be preserved:
    litellm does NOT model per-provider free-tier windows, so that stays Charon policy fed into the
    Router pre-order (`ADOPT-MAP.md` deferred section). Declines like this are CORRECT outcomes.
  - **DEFER** — with an explicit TRIGGER (what must become true). "Later" is not a trigger.

  **This is a DESIGN/DECISION pass, not an implementation.** Do NOT edit
  `src/charon/litellm_plane/litellm_router.py` — it is owned by LITELLM-ORDER-PRECALL and sits on
  the money path. Produce the ADR + the updated ADOPT-MAP; implementation is sequenced AFTER
  GW-CUTOVER-LIVE-WIRE lands.

  ## GUARDS
  - **Do not recommend adopting a capability you have not verified exists in the INSTALLED version.**
    Check the installed `litellm` signature, not the upstream docs — docs drift ahead of releases
    [[confirm-dont-trust-documentation]].
  - Adopting a Router capability must DELETE Charon code, not sit alongside it. If a capability
    would duplicate rather than replace, that is a DECLINE — say so.
  - Anything touching billing/spend is money-path: flag it for RED/GREEN/dogfood at implementation
    time and do not hand-wave the rollback.
  - Some Charon policy is genuinely ours (free-tier windows, funding-class ordering, grading). Do
    NOT recommend surrendering policy that encodes our differentiation.

  ## DONE CONTRACT
  - A table with all 52 params dispositioned, generated from the installed signature.
  - For every ADOPT: the Charon code it deletes, named by file:line.
  - For every DECLINE: the reason, grounded.
  - For every DEFER: the trigger.
  - `tests/test_litellm_capability_map.py` — asserts the ADR's param list matches the INSTALLED
    `Router.__init__` signature, so this decision register cannot silently drift when litellm
    upgrades. Watch it go RED (add a fake param / remove a real one), then GREEN. Paste both.

D&S — Deps & Sequence:
  - Depends on: nothing to DECIDE. Implementation of any ADOPT verdict is sequenced AFTER
    GW-CUTOVER-LIVE-WIRE (which itself needs LITELLM-ORDER-PRECALL).
  - Blocks: the value of the whole litellm adoption — the cutover alone lands parity, not benefit.
  - Runs in parallel with: ROUTER-SUBSTRATE-REEVAL (read-only, disjoint owns).
  - Sequence note: this ticket must land BEFORE ROUTER-SUBSTRATE-REEVAL's conclusions are acted on
    — evaluating alternatives while using 10% of the adopted tool is what produced the prior
    too-narrow verdicts.
