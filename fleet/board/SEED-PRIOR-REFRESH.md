repo: charon
tier: strong
difficulty: 3
work_class: rig-meta
priority: 1
branch: feat/seed-prior-refresh
depends_on: WIRE-GRADING-PRIOR-LIVE
real-dep: WIRE-GRADING-PRIOR-LIVE — TRUE build prereq, not merge order. Until it lands, `SEED_PRIOR`
  has ZERO production consumers (the gateway builds a bare empty `CapabilityMatrix()`), so a
  refresher would keep a DEAD table fresh — motion without effect, and the most likely way this whole
  line of work gets quietly abandoned as pointless. Operator decision 32: wire first, refresh second.
dep-kind: build
owns: src/charon/capability/seed_prior_data.json, src/charon/capability/seed_refresh.py, tests/test_seed_refresh.py
serial_justified: |
  ONE data file plus the refresher that maintains it. Splitting them ships either a data file nobody
  updates (today's defect, in a new location) or a fetcher with nothing to write.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample.
  One checkout, one agent — its OWN worktree.
source: |
  Operator decision 30 + 32, 2026-07-26. Full evidence:
  fleet/handoff-notes/RESEARCH-SEED-PRIOR-SOURCES-2026-07-26.md (470 lines) — read it before starting.
note: |
  ## WHEN — the trigger, so this cannot be forgotten OR started too early
  Start the moment this is true:
  ```
  ls /home/stack/charon-private/fleet/state/done/WIRE-GRADING-PRIOR-LIVE && echo GO || echo WAIT
  ```
  Not "later", not "when someone remembers" — a command whose output decides. Until it prints GO,
  this ticket is correctly idle and should be left alone.

  ## THE PROBLEM
  `src/charon/capability/grades_import.py` holds `SEED_PRIOR` as a HARDCODED Python literal —
  43 entries, 9 models, 6 work classes. Refreshing it means editing Python, so it rots. It is the
  same disease as the 175 hand-pinned legs and the 36-model client list: hand-typed data that decays
  silently while looking authoritative.
  Worse, 19 of the 43 entries claim provenance (`models-dev`, `aider-polyglot`) that the source data
  CANNOT support — aider-polyglot has been FROZEN since 2025-10-03 and grades none of our current
  models. Some of what is there today is not merely stale, it is unfounded.

  ## THE SOURCES (verified by research — licence is the blocking axis)
  * **#1 ADOPT: LMArena `lmarena-ai/leaderboard-dataset`** — **CC-BY-4.0 (licence VERIFIED via HF
    API)**, the only broad-coverage source we may legally vendor into a PUBLIC repo. 373 models,
    covers 11 of 12 routed families at `category='coding'`, published 2026-07-21. Stdlib-parseable
    JSON REST, no API key, NO SCRAPING. Its `agent` config (38 rows, ~7 KB, same licence) scores real
    AGENTIC task work — a closer match to our workload than chat-Elo; prefer it where it covers.
  * **#2: Terminal-Bench 2.1** — Apache-2.0, current, model- AND agent-keyed in separate fields,
    carries cost/latency/reward-hack signals. Use as a second provenance.
  * **LICENCE-BLOCKED, do not vendor:** LiveBench (best per-category fit but has NO LICENSE file at
    all), SWE-bench (CC BY-NC), SWE-bench-Live (unlicensed), Artificial Analysis (attribution but no
    redistribution). SWE-rebench has the best OSS coverage but is a 13 MB RSC scrape — rejected.
  * **DEAD ENDS (do not re-investigate):** aider-polyglot (frozen 2025-10-03), LiteLLM's
    `model_prices_and_context_window.json` (2,954 entries, ZERO quality fields), LiveCodeBench,
    BigCodeBench, EvalPlus, HF-Open-LLM — all dead or quality-free.

  ## DO NOT BUILD A NEW FETCHER
  `src/charon/routing_policy/catalog_refresh.py` already implements the exact pattern — TTL poll ->
  local cache -> LAST-GOOD / stale-but-usable -> off the hot path. Reuse it. The research hit repeated
  HF 504s during validation, which is precisely the argument for its retry/last-good path rather than
  a fresh fetcher. A second refresher is accretion.

  ## HARD CONSTRAINTS
  * Product is PUBLIC and must work OFFLINE on a fresh install -> a checked-in default data file is
    REQUIRED; the refresher must be OPT-IN. (Note: `catalog_refresh` does NOT gate on
    `{"enabled": true}` — its real gate is `maybe_start()` + presence of `providers.json`. Mirror the
    actual mechanism, not the myth.)
  * The prior must stay PROVISIONAL and DECAYING: confidence < 1.0, coarse A-F bands, and ALWAYS
    superseded by a real graded outcome. That property is what bounds the blast radius of trusting
    external data at all — do not weaken it for precision.
  * **The percentile -> A-F banding scheme is PROPOSED, NOT VALIDATED.** Validating it is part of this
    ticket, not an assumption of it. State how you validated, or say plainly that you could not.
  * **devstral is graded ONLY by NC-licensed sources** — it stays manual. Say so in the data file
    rather than silently omitting it.
accept: |
  DONE-CONTRACT (observable, by EXECUTION):
  - `SEED_PRIOR` is no longer a Python literal: the data lives in a checked-in file, and a documented
    command regenerates it. Show the command and its output.
  - Fresh-install offline behaviour proven: with the network unavailable, the gateway still starts and
    the prior still loads from the checked-in file. Demonstrate it.
  - LICENCE PROVENANCE per entry — every row records which source and licence it came from. The 19
    existing unfounded-provenance entries are corrected or removed; say which and why.
  - A DRIFT CHECK exists (a generator nobody re-runs rots exactly like the hand-written list did).
  - RED-PROOF BY EXECUTION: break the refresher -> the drift check goes RED naming the stale entry.
    Report BOTH exit codes.
  - NON-VACUOUS: a drift check that passes against an empty/absent dataset is RED.
  - A real graded outcome still SUPERSEDES the prior after refresh — prove the decay property survives.
  - No new fetcher: show the reuse of `catalog_refresh`'s poll/last-good path.

## Dependencies & sequence

- **Depends on: WIRE-GRADING-PRIOR-LIVE** (build prereq — see `real-dep`). Trigger command above.
- **Blocks:** nothing. But without it the prior is hand-maintained forever, and it is already
  demonstrably wrong (19/43 unfounded entries).
- **Concurrency safety:** owns TWO NEW product files + a test. Does NOT own `gateway.py`,
  `grades_import.py` or `catalog_refresh.py` — if the change appears to need them, STOP and report.
- **Wave:** parallel lane, P1, gated.
