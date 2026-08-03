# PR-AUTOMATION-EVAL — comparative evaluation of PR automation tooling

**Date:** 2026-08-01 (evaluated in-worktree `eval/pr-automation`, charon-private)
**Lane:** EVAL — measure and report. **Wired NOTHING.** This document is the long-form verdict;
registry rows are produced at the bottom and must be appended to `fleet/state/EVAL-REGISTRY.md`
by the manager (that file is outside this ticket's `owns:` — a registry edit belongs to the
registry's own maintenance, not a per-ticket append).

**Decision in one line:** **ADOPT (wrap)** The-PR-Agent/pr-agent as the diff→findings **engine**,
**retire** the engine slice of `fleet/review-pool.sh` (~250 of its 383 lines), and **keep** the
thin claim/queue + `reviewer != builder`-over-OUR-droid-ids shell (which no vendor bot can supply).
**REJECT** Aider-AI/aider for this problem (build client, not a reviewer; no gap vs `opencode`).
**REJECT** all SaaS-only candidates (CodeRabbit, Greptile, Reviewpad, Sourcery, Qodo-hosted) — they
fail the hard requirements (no arbitrary OpenAI-compatible base URL, no self-host, no control).

**The uncomfortable question, answered head-on:** yes — we hand-rolled ~834 lines of something an
adopted tool does better, and pr-agent does solve the engine-side blockers we had to fix by hand.
The measured state of the hand-roll is worse than the ticket believed, and the two blockers it does
NOT solve (B1/B3) are **still broken in the hand-roll today** (evidence below). Keeping the hand-roll
on sunk-cost grounds is not defensible. What survives is a thin wrapper, not the 834 lines.

---

## 1. Method — what was actually measured vs read

| Thing | How | Level |
|---|---|---|
| pr-agent source | shallow clone `the-pr-agent/pr-agent` @ `4a26c38d` (2026-08-01) | executed (source-read) |
| aider source | shallow clone `Aider-AI/aider` @ `5dc9490b` (2026-05-22) | executed (source-read) |
| `review-pool.sh` in-tree state | read all 383 lines + `review-pool.test.sh` 451 lines in this worktree | executed (source-read) |
| pool's real production run | forensics on `/home/stack/charon-private/fleet/state/review-{claims,done}-*`, `review-quarantine-saba/`, `review-queue.tsv` | **executed** |
| CI wiring (B3) | `grep -c review-pool fleet/checks/rig-ci-scope.sh` → **0** | **executed** |
| real PR author identities | `gh pr view <n> --json commits --jq '.commits[-1].authors[0].name'` on open PRs of BOTH repos | **executed** |
| LLM-backed trial (AP-12) | pr-agent/aider pointed at 3 real PRs, verdicts side-by-side | **NOT RUN** — no model key in this lane and the lane wires nothing. Deferred explicitly (see §7). |

Per registry convention (AP-12) the ADOPT verdict is therefore **not yet a runtime-tested verdict** —
it is a source+state+blocker-matrix verdict with the runtime trial explicitly deferred. This is
recorded, not hidden.

---

## 2. Candidate-by-candidate

### The-PR-Agent/pr-agent (primary candidate — direct overlap with review-pool.sh)
- **MCP server?** NO. `git ls-tree` of the whole tree shows no `mcp*` files. MCP-first preference is
  not satisfiable by ANY candidate in this space (see §2 table). CLI/GitHub-Action/app is the shape.
- **Arbitrary OpenAI-compatible base URL?** **YES — hard requirement met.** `[openai] api_base`
  (or `OPENAI__API_BASE=...`) points at any OpenAI-compatible endpoint; routing goes through LiteLLM.
  Provider list includes OpenAI/Anthropic/Gemini/DeepSeek/Mistral/Azure/Bedrock/Vertex/OpenRouter/
  Ollama/etc. `[litellm] extra_headers` supports auth-header passthrough for an API-management
  gateway. This is the mechanism that lets reviews route **through the Charon gateway** (`charon/<model>`)
  — the exact off-Claude path review-pool.sh hand-rolls. **This is the single most load-bearing fact.**
- **Self-hostable?** YES — MIT, `pip install pr-agent`, runs as CLI, GitHub Action, webhook app, or
  Docker. Gitea supported natively (a `gitea_app` server target + `gitea_provider.py`) — relevant,
  the fleet's primary is Gitea. Requires a GitHub/Gitea token; model traffic stays on our box.
- **Control direction:** LIBRARY — we CALL the CLI (agent- and provider-agnostic; we stay the orchestrator).
  The app/webhook mode is framework-shaped but optional.
- **Exit cost:** LOW — a `pip` package + one `.toml` config; the wrapper shell survives a swap.
- **Ops burden:** MODERATE — pip dep + config + a token on our runner; a webhook server only if we
  want event-driven instead of poll/claim.
- **What it FILLS vs review-pool.sh:** diff fetch, PR-compression (token-aware patch fitting),
  prompt construction, structured output parsing (Pydantic/YAML `$PRReview`), findings→comments,
  repo-context loading (`AGENTS.md` fed to /review /describe /improve by default since v0.39),
  agent skills (`SKILL.md`), ticket-context fetching, self-reflection, GitHub-Checks output target
  (v0.39) — i.e. **every non-rig-local line review-pool.sh hand-rolls**.
- **Liveness:** VERY active — v0.39 (2026-07-05), v0.40 (2026-07-25), v0.41 (2026-07-26); community-
  maintained legacy of Qodo (donated); first external maintainer; MIT.
- **What it does NOT fill:** reviewer!=builder over OUR droid ids (reviews as one bot identity);
  claim/queue integration with the fleet board; a BOUNCE *disposition* the Manager reads; anything
  that merges a PR.

### Aider-AI/aider (secondary candidate — BUILD client, not a reviewer; do NOT score as review tool)
- **MCP?** NO — no `mcp*` files in the tree (checked whole `git ls-tree`).
- **Arbitrary OpenAI-compatible base URL?** YES — `--openai-api-base` + LiteLLM routing (model-
  agnostic, incl. DeepSeek, local models).
- **Self-hostable?** YES — pure Python CLI, MIT.
- **Control direction:** LIBRARY (we call the CLI).
- **What it FILLS vs what we have:** it writes code in a git repo and auto-commits, with repomap +
  lint/test loop. **This is the BUILD path, which we already staff with `opencode` (which routes
  through our gateway via `opencode --model charon/*` and is an agentic harness with tool loops).**
  Aider adds no measured capability we lack; it does not review, does not merge, does not close PRs.
- **Verdict:** REJECT for this problem — not a review tool, and no gap on the build path vs opencode.
  (Do not conflate: the brief's scoring instruction is honored — scored on build path, where it loses
  to the incumbent with zero measured leverage.)

### Other candidates (brief is a floor, not a ceiling)
- **CodeRabbit** — proprietary SaaS; free for OSS; **no self-host, no arbitrary base URL** (its hosted
  models), no MCP. REJECT: fails the gateway-routing + control/exit-cost hard requirements. (Could be
  revisited ONLY if the operator accepts a fully-hosted vendor reviewer.)
- **Greptile** — proprietary SaaS (code-indexing; their hosted models); no self-host, no arbitrary
  base URL. REJECT.
- **Reviewpad** — open-source CLI (Apache) exists, but the AI review is hosted (their models/OpenAI);
  no arbitrary base URL on the AI path. REJECT.
- **Sourcery** — SaaS review bot + IDE plugin; proprietary. REJECT.
- **Qodo Merge (hosted, the pr-agent successor platform)** — SaaS; free for OSS; proprietary. REJECT
  for us (cannot route through our gateway), but RECORD as the "if we ever want fully-hosted" option.
- **Danger (JS/Ruby)** — open source, runs in CI, **no LLM** (rule/assertion bot). Cannot do adversarial
  semantic review. Already registry-SKIP (2026-07-21 row) for on-plan enforcement. REJECT for this scope.
- **GitHub Copilot code review / native PR review automation** — hosted, GitHub-only, models not
  ours; no arbitrary base URL. Not an adopt target under rule #5.

### Candidate summary table

| Candidate | MCP | arbitrary OpenAI-compatible base URL | self-hostable | control direction | exit cost | ops burden |
|---|---|---|---|---|---|---|
| **pr-agent** | NO | **YES** (openai api_base / litellm) | YES (MIT, CLI/action/app/Gitea) | library (we call) | low | moderate |
| aider | NO | YES (--openai-api-base) | YES (MIT CLI) | library | low | moderate |
| CodeRabbit | NO | NO | NO | framework (they call) | high | low |
| Greptile | NO | NO | NO | framework | high | low |
| Reviewpad | NO | NO (AI is hosted) | partial (CLI, AI hosted) | framework | mid | low |
| Sourcery | NO | NO | NO | framework | high | low |
| Qodo Merge | NO | NO | NO | framework | high | low |
| Danger | NO | n/a (no LLM) | YES | library | low | moderate |

---

## 3. The head-to-head: pr-agent vs `review-pool.sh`, blocker by blocker

The ticket's 4 hand-fixed blockers are the scoring grid. Evidence below is from source + the pool's
REAL production run today (not the mocks).

### B1 — reviewer != builder over OUR droid ids
- **review-pool.sh today:** the guard is `author_droid == CHARON_DROID_ID` where `author_droid` =
  `gh pr view --json commits --jq '.commits[-1].authors[0].name'` (line 90). Measured on the primary
  repo this CAN fire (charon-private commits carry per-droid ids, e.g. `strong-2841812` on #390/#389/
  #388). Measured on the SLOP-Platform/charon mirror it is a **structural no-op**: open PRs there are
  authored `charon-bot` (verified #216/#215) or `Nnyan` (#214) — a shared identity compared against a
  per-droid `CHARON_DROID_ID`: disjoint namespaces, guard never fires, **exactly the B1 defect the
  ticket says was fixed**. The B1 test fabricates matching values (`GH_MOCK_AUTHOR="strong-abc123"`
  == `CHARON_DROID_ID`), so it never exercises the real "charon-bot ≠ droid-id" path. The prescribed
  fix — capture the BUILDING droid's id at submit time as a per-PR author-droid marker — is **absent
  from review-pool.sh**.
- **pr-agent:** reviews as a single bot identity; it has no concept of a fleet droid id. It CANNOT
  express "this droid built it, so a DIFFERENT droid must review it." Native B1: NO.
- **Whichever engine wins, B1 lives in OUR wrapper** (queue/claim + per-PR author-droid marker at
  submit time). pr-agent is not worse than the hand-roll here — the hand-roll is currently inert on
  one of its two repos and untested on the real identity path. Adopting the engine does not lose B1;
  it makes B1 the wrapper's single job.

### B2 — fail-closed: inability to review must never APPROVE
- **review-pool.sh today:** explicit BOUNCE on diff-fetch/CG/parse failure. **Measured in production
  today:** all 17 quarantined verdicts are `BOUNCE` on "CG review engine failed (rc=3)" — fail-closed
  held. This part works.
- **pr-agent:** never emits an approval disposition at all — it produces findings. A model/API failure
  means no comment posted, exit non-zero, no false approval. B2 is trivially satisfied (there is no
  approve token to emit falsely). The BOUNCE *disposition artifact* the Manager reads is wrapper glue.
- **Result:** pr-agent ≥ review-pool.sh (both fail closed; pr-agent structurally cannot false-approve).

### B3 — real test, WIRED into CI
- **review-pool.sh today:** test file exists (451 lines) but `grep -c review-pool fleet/checks/
  rig-ci-scope.sh` = **0** — it is NOT in `CI_SUITES`, so per the allowlist it **never runs in CI**.
  And its B1 case tests fabricated values (see B1). **B3 is still not met.**
- **pr-agent:** brings its own test suite; whether OUR flow is CI-wired is OUR wiring decision, not a
  tool property. The wrapper (queue/claim + B1 marker + B2 disposition) still needs a wired test.
- **Result:** the hand-roll's B3 claim is measured-false; the wrap still has to ship a *wired* test for
  the wrapper — but the 451-line engine test (mock gh + mock charon-run) largely evaporates, because
  the engine is now a vendor binary under its own test regime.

### B4 — prompt-injection: a PR diff must not steer its own review
- **review-pool.sh today:** isolates the diff behind delimiters, explicitly tells the model the diff is
  untrusted, and parses ONLY the delimited verdict section. Has an injection test. This is the strongest
  part of the hand-roll, but its verdict IS an approval disposition (APPROVE-FOR-MERGE) — so a diff
  steering the verdict toward APPROVE is exactly the dangerous case.
- **pr-agent:** parses the model's structured YAML (Pydantic-typed `$PRReview`) — a robust parser.
  BUT the review system prompt I read contains NO "the diff is untrusted data" instruction, and the
  repo had a real credential-exposure bug on its docs tool (`/help_docs`, v0.36.1, issue #2445, now
  disabled). pr-agent has no injection test. However: pr-agent never emits APPROVE — it emits findings,
  and the disposition (APPROVE/NEEDS-REVISION/BOUNCE) is derived in OUR wrapper by policy (e.g. any
  HIGH-severity finding → NEEDS-REVISION). That **removes the "diff plants an APPROVE token" attack
  surface** that made B4 dangerous for review-pool.sh.
- **Result:** mixed-to-pr-agent — weaker prompt-side hardening than the hand-roll, but the approve-
  steering attack no longer exists because the model can't produce an approval. Wrap layer decides.

### Sharp-test row (the two questions the brief says are the sharpest)

| Incident | Would pr-agent catch? | Would review-pool.sh catch? |
|---|---|---|
| **#313 CI-SUITES-CANARY fixture-bypass** (`mk_canary_runner` with its own `CANARY_WINDOW_DAYS=14`; mutating the real file moves no test) | **Maybe** — pr-agent fetches repo context + AGENTS.md and its bug-focus prompt gives a reasoning model a real chance to flag "test re-implements the logic it claims to test." No deterministic guarantee; it is a model-capability catch, not a tool guarantee. | **Same chance** — identical model pool via our gateway, thinner prompt. No deterministic guarantee. |
| **#188 dead-no-op** (cooldown union reads a private attr, never fires) | **Maybe** — semantic "this guard can never fire" needs the model to understand the code; pr-agent with repo context is the better-equipped of the two. | Same chance. |

**Honest answer to "would either tool catch a fixture-bypass like this":** neither provides a
DETERMINISTIC guard for the self-referential-test class. Both are LLM-semantic catches whose odds
track the model + prompt + repo-context, not the scaffolding. The deterministic fix for the
#313-class is **mutation testing on the real file** (the rig already has the fixture-bypass /
gate-integrity machinery; #313 was caught by exactly that — a manager running a manual mutation).
A review tool is a complement, not a replacement, for that class. Every claim about catching #313/#188
must stay a "maybe with repo context" until the executed trial measures it — do not let a vendor
marketing page convert a maybe into a yes.

---

## 4. The measured bottleneck: does either tool reduce time-to-merge?

**No, not by itself — and this is the point of the ticket, so it gets said plainly.**

- The session's own evidence: 46 open PRs, many >370h old; the top-3 unblock levers are MERGES
  (SYNC-SCHEDULE, GITHUB-LIMITS-HARDENING, BENCH-OOB-GRADING, each unblocking 7); 13 of 14 hard-
  blocked tickets are gated on work already BUILT and sitting in open PRs.
- **Measured throughput of the hand-roll:** the pool RAN today (2026-08-01, `saba-rv-*`/`saba-reviewer-*`
  droids), claimed ~17 PRs across both repos (claim+done markers in `fleet/state/review-{claims,done}/`),
  and every verdict is a `BOUNCE` on "CG review engine failed (rc=3)" (17 verdict files quarantined at
  `fleet/state/review-quarantine-saba/`). **Zero usable verdicts in production to date.** The queue file
  is empty (0 bytes) at sample time, so "the queue has never been populated" is true at this instant but
  the pool is not inert — it ran and produced only infra-failure BOUNCEs.
- pr-agent (wrapped through our gateway) would not magically merge the 46 either. **Comment volume is
  not throughput.** A reviewer — hand-rolled or adopted — is a *precondition* for merge, not the merge.
  The lever that drains the backlog is a **merge policy**: auto-merge on required-checks green (or a
  batch-merge dispensation pass over the 13 built-and-blocked PRs). pr-agent CAN be wired as a required
  check (GitHub Checks output, v0.39) so a clean review gates merge — but gating ≠ merging. The single
  highest-leverage action remains the operator/manager batch-merge of the built-but-unmerged work.
- **Therefore:** adopt the review engine on review-quality merits, but do NOT sell it as the merge
  fix. NEXT (§7) separates the two.

---

## 5. Hard rules checklist

1. **ADOPT-FIRST** — satisfied: pr-agent is the off-the-shelf engine and this eval prefers it over the
   hand-roll. No sunk-cost argument is used to keep review-pool.sh.
2. **Verdicts → EVAL-REGISTRY rows** — produced in §6 for the manager to append (owns: boundary keeps
   the registry untouched by this ticket).
3. **Corrected lens** — filled: pr-agent fills the *engine* gap; size/stars/deps not used as rejection
   criteria; judged on liveness (active), fit-without-bending (Gitea + gateway routing), control
   direction (library), exit cost (low), ops burden (moderate).
4. **MCP-first** — checked; **no candidate ships an MCP server** (verified in source). The preferred
   integration shape is therefore CLI-under-our-claim-layer, not MCP.
5. **NO hardcoded provider/model** — pr-agent and aider both accept an arbitrary OpenAI-compatible base
   URL (verified in docs+source) and can route through the Charon gateway. SaaS candidates cannot and
   are rejected on that ground.
6. **Every leverage claim names a measured incident** — #313/#188 are the reference incidents; the
   only leverage claims made here are the measured ones (engine surface retirement; structured-output
   parse; never-approves; B1 stays wrapper-owned) and the #313/#188 catch is honestly marked "maybe,
   requires the executed trial", never as a yes.

---

## 6. EVAL-REGISTRY rows — to be appended by the manager

Rows below are ready to paste (registry is append-only; this ticket does not own the file). Cite this
file as evidence-link.

```
| The-PR-Agent/pr-agent (pr-agent, MIT) | PR review engine: diff→findings, replacing review-pool.sh's engine slice (diff fetch, prompt build, verdict parse, comment post) inside a kept claim/queue + reviewer!=builder shell | 2026-08-01 | **ADOPT (wrap)** — adopt the engine, retire review-pool.sh's engine slice; keep the thin claim/queue + per-PR author-droid-marker shell (which pr-agent cannot supply). Runtime trial (AP-12: 3 real PRs through our gateway) DEFERRED and required before wiring; this lane wires nothing. | aligned — verified against the 4 blockers on the real production state (B1 still inert on the charon mirror + B3 still unwired, measured); source-read + host forensics, runtime quality trial explicitly deferred and recorded. | fleet/state/PR-AUTOMATION-EVAL.md | prior UNEVALUATED qodo-merge/aider/CodeRabbit row (line 144) |
| Aider-AI/aider | PR/build client comparison vs `opencode` (the brief's build-path scoring instruction) | 2026-08-01 | REJECT for this problem | aligned | A build client (auto-commit editing loop), not a reviewer; it does not review or merge PRs, and on the build path it adds no measured capability over `opencode` (already agentic, already gateway-routed via charon/*). Do not score as a review tool. | fleet/state/PR-AUTOMATION-EVAL.md §2 | same UNEVALUATED row |
| CodeRabbit / Greptile / Reviewpad / Sourcery / Qodo-hosted | PR-review automation, SaaS | 2026-08-01 | REJECT | aligned | SaaS-only, no arbitrary OpenAI-compatible base URL, no self-host → fails the gateway-routing + control/exit-cost hard rules on fit, not capability. Qodo-hosted recorded as the "if we ever want fully-hosted" option. | fleet/state/PR-AUTOMATION-EVAL.md §2 | same UNEVALUATED row |
```

---

## 7. Recommendation

**ADOPT (wrap).** Specifically:
1. **Adopt pr-agent as the review engine** (MIT, self-hosted CLI, `[openai] api_base` = our gateway,
   model = `openai/charon/<model>`, Gitea support). This retires ~250 lines of review-pool.sh
   (do_review/build_review_prompt/_parse_verdict + the verdict-writing plumbing), leaving a thin shell
   (~80-100 lines) that owns what no vendor bot can: queue/claim, reviewer!=builder over OUR droid ids,
   and the BOUNCE/NEEDS-REVISION/APPROVE disposition the Manager reads.
2. **Ship the missing B1 fix as part of the wrap**: capture the BUILDING droid's `CHARON_DROID_ID` at
   submit time as a per-PR author-droid marker (the REVIEWER-TAB-POOL ticket already prescribes this);
   the current `gh`-commit-author read is inert on the charon mirror and untested on the real identity
   path.
3. **Keep** the queue/claim integration with the fleet board and the Manager-dispensation firewall
   (the pool never merges) — that is the genuinely rig-local slice.
4. **Required-before-wire (AP-12 trial, from REVIEWER-TAB-POOL's substrate-retest):** point pr-agent at
   3 real open PRs through the Charon gateway; confirm (a) the gateway routes pr-agent's chat-completions
   calls and (b) the wrap's author-droid marker makes reviewer!=builder fire on real identities. Record
   verdicts side-by-side against the pool's 17 BOUNCEs. Until then this row is aligned-but-not-runtime-tested.
5. **Do NOT sell the adoption as the merge fix.** The 46-PR backlog is a merge-policy problem
   (auto-merge on green / batch-merge pass), orthogonal to which reviewer runs.

**Then feed REVIEWER-TAB-POOL:** with the engine adopted, REVIEWER-TAB-POOL is re-scoped to the thin
wrapper (claim/queue + author-droid marker + disposition + wired B1/B2 test) and most of its 830-line
scope is retired — exactly the re-scope the ticket predicted.

---

## 8. Evidence links

- pr-agent source @ `4a26c38d` (2026-08-01): README (features/Gitea/model table), `pr_agent/settings/
  pr_reviewer_prompts.toml` (system prompt, structured YAML output, no untrusted-diff instruction),
  `docs/docs/installation/gitea.md` (self-hosted Gitea webhook app), `LICENSE` (MIT), releases v0.39-0.41.
- Changing-a-model docs (docs.pr-agent.ai): `[openai] api_base` / `OPENAI__API_BASE`, `[litellm] extra_headers`.
- aider source @ `5dc9490b`: `--openai-api-base` (args.py), LiteLLM routing (models.py), no mcp* in tree.
- review-pool.sh (this worktree): lines 88-91 (author_droid from gh commit author), 105-133 (claim/B1),
  135-294 (engine), 296-341 (loop).
- review-pool.test.sh: B1 fabricates `GH_MOCK_AUTHOR` values (lines 128/154/175/...).
- B3 measured: `grep -c review-pool fleet/checks/rig-ci-scope.sh` → 0.
- Production-run forensics: `/home/stack/charon-private/fleet/state/review-{claims,done}/`,
  `review-quarantine-saba/` (17 BOUNCE verdicts, all "CG review engine failed (rc=3)"),
  `review-queue.tsv` (0 bytes at sample time).
- Author identities: `gh pr view` on #388/#389/#390 (charon-private: `strong-2841812`),
  #214/#215/#216 (charon mirror: `Nnyan`/`charon-bot`).
- Prior registry state: `fleet/state/EVAL-REGISTRY.md` line 144 (qodo-merge/aider/CodeRabbit UNEVALUATED),
  line 57 (Danger SKIP), line 145-146 context; `fleet/board/REVIEWER-TAB-POOL.md` (B1-B4, substrate-
  retest); `fleet/board/CI-SUITES-CANARY.md` (#313); `fleet/board/FLOW-CANARY.md`/`GW-BRIDGE-4-PARK-COOLDOWN.md` (#188).
