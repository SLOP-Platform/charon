# Path C — the dogfood-as-eval loop (design + slate + dry-run)

Date: 2026-07-13. Status: **harness built + full 6-candidate x 2-ticket ranking run.
2 INTEGRITY BUGS found in the harness itself and FIXED same day — see "CORRECTIONS"
at the end of this file. Corrected per-cell verdicts: `fleet/state/PATH-C-RANKING-
CORRECTED.md`.**

## Why this exists

A synthetic benchmark battery (`fleet/benchmark/run.sh` S0-S6, `fleet/benchmark/
preflight.sh` T1-T12 trap tasks) is at best a PRE-SCREEN (memory: `benchmark-not-a-valid-
ranker` — synthetic tasks are grader-readable + self-graded + show low discrimination).
**Path C is the real trust signal**: does a candidate model, run through the actual
gateway, actually complete a REAL small product ticket, end to end, cheaply, under a
latency budget, with the result objectively gradeable? Rank candidates by that outcome,
not by a synthetic score.

This design COMPOSES existing pieces — nothing here is a rebuild:

| Piece | Source | Reused as |
|---|---|---|
| Model driving + cross-provider failover + timeout/limit attribution | `fleet/charon-run.sh` | invoked UNMODIFIED per candidate; its own attribution lines are parsed, not re-derived |
| Worktree isolation | `git worktree` (repo-registry.sh convention: `/home/stack/code/charon-fleet-<label>`) | one fresh worktree per candidate off `origin/master`; never touches the primary checkout or master |
| Objective grader | `charon.cli gate` (`PYTHONPATH=src python3 -m charon.cli gate` — repo-registry.sh's `RR_GATE`) | run from inside the candidate's own worktree after the model's attempt |
| Ticket-specific accept check | the board ticket's own `accept:`/gate line | `DOGFOOD_TEST_CMD` env var |
| Monitoring/attribution discipline | memory `monitored-preflight-failure-attribution`, `latency-is-a-failure-class` | every result card carries wall-time, provider note, did-real-work, and a single failure-attribution bucket |

## Harness

`fleet/benchmark/dogfood-eval.sh <ticket-label> <ticket-brief-file> <model1> [model2 ...]`

For each candidate model:
1. Fresh `git worktree` of `/home/stack/code/charon` off `origin/master` at
   `/home/stack/code/charon-fleet-dogfood-<ticket>-<model>-<ts>`, on a **local-only**
   branch `dogfood-eval/<ticket>/<model>-<ts>` (never pushed).
2. Copies the ticket brief into the worktree, then runs
   `CHARON_RUN_TIMEOUT_S=<budget> fleet/charon-run.sh <worktree> <log> <brief> <model>`
   — a SINGLE model per invocation (no cross-MODEL failover here — that would mask a
   candidate's own result; the gateway's own cross-PROVIDER failover for that one model
   id still applies, which is what we want to measure).
3. Parses `charon-run.sh`'s own log lines to bucket the outcome into exactly one
   attribution: `ran-to-completion` / `too-slow(latency-budget-exceeded)` /
   `provider-degraded->retry(pool-exhausted-on-timeout)` /
   `provider-throttled->try-another(limit-hit | all-exhausted)` / `error-nonlimit`. A
   provider symptom never disqualifies the model.
4. Computes a REAL `git diff` (stronger than `charon-run.sh`'s own mtime-based proxy,
   since our worktree is a real git checkout) — empty diff + exit 0 is reclassified as
   `early-ditch/quality` (the model ran, exited clean, but did nothing — that IS a
   quality fail, not a provider symptom).
5. Grades objectively: `charon.cli gate` (11 checks) + the ticket's own `DOGFOOD_TEST_CMD`
   (accept: check), both run from inside the candidate's worktree.
6. Advisory scope-check (`DOGFOOD_EXPECT_FILES`) — flags if the diff touches files
   outside the ticket's `owns:`, never blocks.
7. Emits one result card (`fleet/state/dogfood-eval/results/<label>.card.md`) + saved
   diff (`.diff`) + gate/test logs, and appends one row to a combined
   `<ticket>-<ts>-SUMMARY.md` table.
8. **Never commits, pushes, or merges** the candidate's worktree/branch. The worktree is
   left in place (`DOGFOOD_KEEP_WORKTREE=1` default) for a human to `cd` in and read the
   diff themselves — pass/fail is a strong signal, not an auto-merge trigger.

## Candidate slate (code-confirmed 2026-07-13, live gateway probes — not from docs)

Probed directly against `http://10.0.1.60:8080/v1/chat/completions` with the real gateway
bearer token (from `~/.config/opencode/opencode.json`'s `provider.charon.options.apiKey`
— NOT the `CHARON_GATEWAY_TOKEN` env var, which is stale/wrong in this session's shell),
tiny `max_tokens` probe, "Reply with the single word: PONG":

| model | live now? | note |
|---|---|---|
| **minimax-m2.7** | **200 OK** (via nanogpt) | operator's stated MUST-PASS control; also matches `TOOLCALL-ROOTCAUSE.md`'s finding that minimax-m2.7-ng/-or work cleanly today. The standing `MODEL-PREFLIGHT` `.card` showing "detain" for minimax-m2.7 is from the UNRELATED synthetic T1-T12 trap battery and was a substrate bug (bench-grader `PermissionError`), not a live-routing signal — do not confuse the two systems. |
| **deepseek-v4-pro** | 200 OK | frontier default per `tier-models.tsv` |
| **deepseek-v4-flash** | 200 OK | economy default; NOTE — this is the `MODEL-PREFLIGHT` battery's MUST-FAIL control and has a documented fabrication history in `model-scorecard.tsv` ("confabulated false commit history when asked"). Keep it in the Path C slate anyway — a REAL-ticket run is exactly what should re-confirm or contradict that reputation, cheaply. |
| **glm-5.2** | 200 OK (routed via OpenRouter/StreamLake this probe) | frontier/strong default |
| **kimi-k2.6** | 200 OK (routed via OpenRouter/Decart this probe) | frontier default |
| **phi-4** (DeepInfra) | 200 OK, real "PONG" completion | DeepInfra was funded THIS SESSION (confirmed: `PROVIDER-WIRE-REPORT.md` shows 402 zero-balance on 2026-07-13 AM; live probe just now returns 200) |
| **glm-4.7** (DeepInfra) | 200 OK | same DeepInfra funding; reasoning-heavy reply truncated by the tiny probe's `max_tokens`, not an error |
| ~~gemini-2.5-pro~~ | **EXCLUDED** | empty/reset reply on live probe — confirms `PROVIDER-WIRE-REPORT.md`'s finding (Google AI Studio depleted prepaid credits + a real gateway bug in `proxy.py:316 classify()` that turns Google's list-shaped 429 body into a connection reset). Google AI Studio stays PARKED per operator directive; do not include in the ranking slate until re-funded AND the `classify()` bug is fixed. |
| openrouter-backed models generally | mixed | operator flagged openrouter as "drained — exclude/expect-roll"; `glm-5.2`/`kimi-k2.6` probes above happened to land on OpenRouter successfully just now, but the pool for each of these models spans multiple providers (`-ng -hf -nw -or -cline` etc per `PROVIDER-BEST-PER-MODEL.md`) so the gateway's own cheapest-provider-first router already rolls off a drained OpenRouter leg — no slate change needed, just don't read a single live probe as "openrouter is healthy again." |

**Slate used for this build/dry-run round:** `minimax-m2.7` (control), `deepseek-v4-pro`,
`deepseek-v4-flash`, `glm-5.2`, `kimi-k2.6`, `phi-4` — six candidates, all confirmed live
on the gateway moments before this doc was written. `glm-4.7` is a viable seventh (also
DeepInfra, also just confirmed live) if the operator wants a wider first pass.

## Chosen ticket

**`TOOL-REPAIR-MUTATING`** (`fleet/board/TOOL-REPAIR-MUTATING.md`, brief at
`prompts/tool-repair-mutating.md`).

Why this ticket:
- **difficulty: 1**, `work_class: bugfix` (not money-path) — low blast radius by the
  board's own classification.
- **`owns: src/charon/tool_repair.py, tests/test_tool_repair.py`** only — a genuine
  product-code ticket (so `charon.cli gate` is the natural, intended grader), but the
  module is **not yet wired into the proxy** (per the ticket: "MUST be fixed BEFORE
  tool_repair is wired into the proxy") — so a bad candidate attempt cannot touch any
  live request path. Confirmed by reading `src/charon/tool_repair.py` on
  `origin/master`: `repair_arguments`/`repair_tool_calls` are called only from tests
  today (`grep -rn "tool_repair" src/charon` outside `tool_repair.py` itself and its
  tests returns nothing on master).
- **Objectively gradeable**: the ticket brief itself specifies the exact gate:
  `PYTHONPATH=src python3 -m pytest tests/test_tool_repair.py -v -q ; ruff check ; mypy
  src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py` —
  this IS (a subset of) `charon.cli gate`'s own 11 checks. Used both: the full
  `charon.cli gate` (via `DOGFOOD_GATE_CMD`, the default) AND the ticket's own targeted
  pytest file (via `DOGFOOD_TEST_CMD`).
- **Confirmed the bug is real and reproducible on `origin/master`** (not already fixed):
  `repair_arguments`/`repair_tool_calls` accept an `allow_mutating: bool = False` kwarg,
  but the ordered rule table `_RULES` carries an unused third field
  (`_RULE_MUTATING_SAFE`) that the repair loop unpacks as `_m_safe` and **never reads**
  (`tool_repair.py:294`). The existing test `test_mutating_flag_passes_as_documented`
  (`tests/test_tool_repair.py:243-257`) currently ASSERTS the no-op behavior (both
  `allow_mutating=True` and `=False` repair identically) — so a correct fix must also
  change that test's expectation, not just add code elsewhere. This is exactly the kind
  of small-but-real, easy-to-verify, easy-to-fabricate-around ticket Path C should be
  discriminating on.
- **Not money-path, not safety-gated**: does not touch billing, balance, or the
  request-forwarding hot path.

`DOGFOOD_EXPECT_FILES="src/charon/tool_repair.py tests/test_tool_repair.py"` (advisory
scope-check — a candidate that "fixes" this by touching the proxy/forwarder or wiring
itself in early would be flagged, which is itself a useful signal: the ticket explicitly
says NOT to wire it in yet).

## Dry-run result (minimax-m2.7, MUST-PASS control)

Command run (from `charon-private/`):
```
DOGFOOD_TEST_CMD="PYTHONPATH=src python3 -m pytest tests/test_tool_repair.py -v -q" \
DOGFOOD_EXPECT_FILES="src/charon/tool_repair.py tests/test_tool_repair.py" \
DOGFOOD_LATENCY_BUDGET_S=900 \
fleet/benchmark/dogfood-eval.sh TOOL-REPAIR-MUTATING \
  prompts/tool-repair-mutating.md minimax-m2.7
```

| field | value |
|---|---|
| overall verdict | **REVIEW-READY** (candidate-for-merge; human must still read the diff) |
| failure attribution | `ran-to-completion` (no failure) |
| wall_time_s | **194** (budget 900 -> `within-budget`) |
| provider | best-effort unknown-clientside (gateway alias only — real per-provider attribution needs gateway-log correlation, see charon-run.sh's own caveat) |
| did-real-work | `real-diff(files=2)` (harness git-diff signal) |
| charon.cli gate | **pass** — all 12 checks (ruff, mypy, SLOP-boundary, version, gate-registry, public-clean, no-rig-import, check-arch, security-scan, test-patterns, workflow-policy, inert-code) |
| ticket accept: check | **pass** — `pytest tests/test_tool_repair.py` -> 29 passed in 0.09s |
| scope | `in-scope` — touched exactly `src/charon/tool_repair.py` + `tests/test_tool_repair.py`, matching the ticket's `owns:` |
| candidate's fix | genuine + correct: added a `_schema_is_mutating` helper + an `x-mutating:true` short-circuit in `repair_arguments` (skips repair when `allow_mutating=False`), and rewrote the stale no-op-asserting test into 3 real discriminating tests. Read the saved diff — not a fabrication. |

**Monitoring capture proven:** the harness captured wall-time (194s), the latency-budget
verdict (within-budget), the failure-attribution bucket (`ran-to-completion`), the
did-real-work signal (`real-diff(files=2)`), and BOTH objective grades (gate pass +
ticket-test pass) — end to end, with no merge. This confirms the pipe runs: fresh
worktree -> gateway-driven model attempt under a budget -> objective grade -> review
packet, never touching master.

**One validation finding (kept, not hidden):** `charon-run.sh`'s own mtime-based
did-real-work heuristic reported `files=36` (pycache/mypy-cache noise) for the SAME run
where the harness's `git diff` reported the true `files=2`. This confirms the design
choice to compute real-work from `git diff` in the worktree (a real git checkout) rather
than reuse charon-run.sh's mtime proxy — the git-diff signal is the load-bearing one and
should stay the harness's authority.

Artifacts (all under `fleet/state/dogfood-eval/results/`):
`dogfood-TOOL-REPAIR-MUTATING-minimax-m2.7-<ts>.card.md` (result card),
`.diff` (full saved diff for human audit), `.gate.log`, `.test.log`,
`.charon-run.log`, and the combined `TOOL-REPAIR-MUTATING-<ts>-SUMMARY.md`.

**Harness bug found + fixed during the dry-run:** the first run's result CARD dropped its
monitoring/grade lines because several `write_card` `printf` format strings began with a
literal `-` (printf parsed it as an option flag). Fixed to `printf --` before committing;
the SUMMARY row, verdict, gate, test, diff, and scope were all captured correctly
throughout (the bug was cosmetic-to-the-card only, never affected grading). Card
regenerated from the still-present worktree + logs.

## What blocks a full candidate ranking (report back to the operator)

1. **Cost/time**: a full ranking of the 6-7-candidate slate is ~6-7x this dry-run's
   wall-clock + gateway spend. Not run yet per the task's explicit instruction (dry-run
   only, no ranking this round).
2. **Provider attribution is best-effort only.** `charon-run.sh` itself documents (and
   this harness inherits) that the client side cannot see which upstream sub-provider
   served a request — only the gateway's own container logs can, correlated by
   timestamp+model. A real per-candidate "which provider actually served this" column
   needs a gateway-log-correlation step that does not exist yet (tracked already as a
   gap in `charon-run.sh`'s own comments; out of scope to build here).
3. **One ticket is a thin slice.** `TOOL-REPAIR-MUTATING` is intentionally small
   (difficulty 1) so the FIRST dry-run proves the pipe cheaply. A trustworthy ranking
   needs 2-3 tickets spanning at least `bugfix` + one other `work_class` (e.g. a small
   `refactor` or `tests` ticket) before treating any single-ticket result as a verdict on
   a model overall — one ticket discriminates "did this candidate do this ticket," not
   "is this candidate generally better."
4. **`deepseek-v4-flash`'s standing MUST-FAIL reputation is from a DIFFERENT battery**
   (`MODEL-PREFLIGHT`'s synthetic trap tasks) — Path C should independently re-confirm
   or contradict that on a REAL ticket rather than importing the synthetic verdict
   uncritically; this round does not yet include a `deepseek-v4-flash` run.
5. **Money-path safety gate**: per the task's own instruction, this ticket slate
   deliberately excludes anything money-path/high-risk. Ranking candidates for
   money-path-eligible work (e.g. `PROVIDER-CATALOG-REFRESH`-class tickets) needs a
   SEPARATE, more heavily-reviewed round — do not extrapolate a Path C pass on
   `TOOL-REPAIR-MUTATING` into "trusted for money-path work."

## Non-actions (explicit, per the task's constraints)

- No candidate's worktree/branch was committed to, pushed, or merged. Every worktree
  under `/home/stack/code/charon-fleet-dogfood-*` is local-only, left in place for
  human audit.
- The board ticket `TOOL-REPAIR-MUTATING` itself was NOT claimed/landed by this run —
  its `state/needs-push`/board-claim machinery was never touched; this is a read-only
  dogfood probe against a copy of the ticket's brief, not a real ticket execution.
- The harness script + this doc are committed on branch `feat/dogfood-eval` in
  `charon-private` only. Nothing was pushed.

## CORRECTIONS (2026-07-13, later same day — integrity audit of the full ranking run)

The full slate ran (`TOOL-REPAIR-MUTATING` bugfix + `PROVIDER-URL-HELPER` refactor x
minimax-m2.7/deepseek-v4-pro/deepseek-v4-flash/glm-5.2/kimi-k2.6/phi-4). Auditing the raw
`fleet/state/dogfood-eval/results/*.card.md` + `*.charon-run.log` against the model
transcripts found **2 real integrity bugs in `dogfood-eval.sh` itself** (not in any
candidate's work) that mislabeled otherwise-good runs. Both are FIXED on this branch.

**Bug 1 — attribution mislabel.** The old inline classifier (was ~lines 163-166) matched
`"ALL MODELS EXHAUSTED"` as a catch-all and stamped `provider-throttled`, but
`dogfood-eval.sh` always invokes `charon-run.sh` with exactly ONE candidate model, so that
banner fires for ANY nonzero exit — real rate-limit or not. Confirmed false for:
- **minimax-m2.7 / PROVIDER-URL-HELPER** (first attempt, `...T002000Z`): `charon-run.log`
  shows `Error: Unexpected error / database is locked` (rc=1) — a LOCAL sqlite lock in
  opencode's own session store, nothing to do with any provider. (The candidate's real,
  gradeable attempt is the rerun at `...T020402Z` — see below.)
- **phi-4, all 4 runs** (both tickets, both timestamps): every single one failed with an
  opaque gateway `{"name":"UnknownError", ...}` (rc=1) — see the DeepInfra funding probe
  below; this is NOT a rate-limit.
- **deepseek-v4-flash / kimi-k2.6 on TOOL-REPAIR-MUTATING**: both candidates' own
  transcripts show the fix landed and ALL gate checks (pytest/ruff/mypy/boundary/version)
  printed passing — THEN a single TRAILING post-completion call hit a real
  provider/session limit and `charon-run.sh` exited nonzero on that basis alone. The
  harness's own independent re-grade (gate pass + ticket pytest pass, real 2-file diff)
  proves the work was already done and correct before that trailing call.

**Fix**: extracted the classifier into `fleet/benchmark/lib/dogfood-attribution.sh`
(`classify_attribution` + `reclassify_trailing_success`), sourced by `dogfood-eval.sh`.
Local/opaque signatures (`database is locked`, `"name": "UnknownError"`) are now checked
BEFORE the generic all-exhausted catch-all and get their own `local-error(...)` bucket
(never silently folded into `provider-*`); a provider hiccup on a call made AFTER the real
diff already graded clean (gate pass + ticket-test pass) is reclassified so the overall
verdict still credits the work instead of a false `RETRY(provider-symptom)`. Fail-on-revert
selftest: `fleet/benchmark/selftest/test_dogfood_attribution.sh` (verified it reproduces
the original bug when the old check-order is restored, then verified green on the fix).

**Bug 2 — accept-grep self-match.** `PROVIDER-URL-HELPER`'s `DOGFOOD_TEST_CMD` "no leftover
inline duplication" check was a naive `grep -RnE '<pattern>' <files>`. It false-matched
**glm-5.2**'s own DOCSTRING text (a Sphinx-style `` ``code`` `` citation of the old inline
expression, left as documentation after glm-5.2 correctly deduplicated the real code),
producing a false `FIXES-NEEDED` for an otherwise-clean candidate.

**Fix**: new `fleet/benchmark/lib/grep-code-only.sh` — same pattern-match, but filters out
`` ` ``-quoted (docstring-cited) and `#`-commented mentions before deciding there's a real
leftover. Confirmed against the actual candidate worktrees still on disk
(`/home/stack/code/charon-fleet-dogfood-PROVIDER-URL-HELPER-*`): glm-5.2 now PASSES (was a
false fail); minimax-m2.7's genuine incomplete dedup (`discover.py:34`, real code, no
backticks) still correctly FAILS; kimi-k2.6 (already passing) is unaffected. `PATH-C-EVAL-
SET.md`'s canonical `DOGFOOD_TEST_CMD` one-liner updated to call the new helper. Fail-on-
revert selftest: `fleet/benchmark/selftest/test_grep_code_only.sh` (includes a control
assertion that the naive unfiltered grep DOES reproduce the false positive on the same
fixture, proving the filter is load-bearing).

Both selftests verified GREEN after the fix (`bash fleet/benchmark/selftest/test_dogfood_
attribution.sh` and `bash fleet/benchmark/selftest/test_grep_code_only.sh`).

**DeepInfra funding — probed directly, not inferred from docs (2026-07-13):** direct
`POST https://api.deepinfra.com/v1/openai/chat/completions` with the stored
`~/.config/opencode/secrets/deepinfra.key` and `model: microsoft/phi-4` returned **HTTP
200**, a real `"PONG"` completion, `estimated_cost: 1.47e-06` — DeepInfra is **FUNDED**, not
the 402-zero-balance state `PROVIDER-WIRE-REPORT.md` recorded that same morning. The
gateway itself (`http://10.0.1.60:8080/v1/chat/completions`, `model: "phi-4"`) also returned
200/PONG just now. **Conclusion: phi-4's 4/4 dogfood failures are NOT a funding/rate-limit
issue** — DeepInfra answers plain completions fine, direct and through the gateway; the
opaque `UnknownError` is specific to the AGENTIC/tool-use run path `charon-run.sh` drives
(`opencode run --model charon/phi-4`), root cause otherwise unresolved. Correctly bucketed
as `local-error(opaque-server-error...)` (needs human triage), never as a provider
rate-limit or as a model-quality fail.

**GAP found (reuse-check, not a bug): no mechanized test-quality gate exists for the
dogfood/real-ticket set.** Searched `fleet/board/*.md` (incl. `.parked`) + `fleet/tools/` +
`fleet/benchmark/` for a gate that evaluates AND improves a dogfood ticket's own tests when
they're buggy/too-easy/non-discriminating (the kind of thing the operator expected to
exist). Found only a DIFFERENT, unrelated system: `benchmark/promote.py` — a
provisional->active promotion gate scored by cross-model spread, scoped ONLY to
`benchmark/units.tsv` (the SYNTHETIC S0-S6 sections + T1-T12 trap-battery replays) — and
grader-discrimination selftests (`benchmark/selftest/run_selftests.py`,
`test_preflight_graders.py`) that check the SYNTHETIC graders themselves, not any dogfood
ticket. Neither touches `dogfood-eval.sh`'s real-ticket set at all. `PATH-C-EVAL-SET.md`'s
own "Rejected candidates" table documents curating out a non-discriminating ticket (SR-3,
"free pass") as a MANUAL human/session judgment call, not a mechanized check. Confirmed
live in this round's own data: `TOOL-REPAIR-MUTATING`'s stock pytest suite passes trivially
on an UNMODIFIED worktree (the stale test asserts the pre-fix no-op behavior), so a
candidate that does NOTHING would pass the ticket's own accept-check — the only thing
stopping that from reading as a false pass today is the harness's OWN diff-based
did-real-work override (`early-ditch` -> `DETAIN(quality)`), not any property of the
ticket's test. **Real gap, not a false alarm**: `TOOL-REPAIR-MUTATING` is confirmed TOO
EASY as a sole discriminator and needs either a harder/adversarial ticket added to the
slate or a mechanized "does this ticket's test actually discriminate a no-op from a real
fix" gate before its results are trusted alone. See `PATH-C-RANKING-CORRECTED.md`'s tier-
assignment note.
