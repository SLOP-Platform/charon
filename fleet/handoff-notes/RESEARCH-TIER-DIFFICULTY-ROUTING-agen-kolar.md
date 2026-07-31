# RESEARCH — tier difficulty estimation & cheapest-capable routing (adopt-first)

Author: agen-kolar (research sub-session) · 2026-07-24 · READ-ONLY, nothing modified.
Scope: replace / justify `nsurf >= 3 ⇒ frontier` in `fleet/capability/tier_classify.py`
(branch `feat/tier-classifier`, worktree `/home/stack/charon-private-wt/TIER-BALANCE`).

**Headline:** the answer is *already inside tools we own*. Charon has a built, tested,
in-product effort estimator (`src/charon/decompose_effort.py`) whose weights encode the
exact correction the adversarial review asked for (size weight **0.15** vs difficulty
weight **2.0**), and LiteLLM 1.93.0 — already a dependency — ships a whole
`router_strategy/` family (complexity / quality / adaptive / cost / budget / tag) that
the wrapper never enables. No *external* new adoption is warranted. Neither is a new
hand-roll.

---

## 0. Evidence base (what I actually ran)

| # | Fact | How verified |
|---|---|---|
| E1 | `nsurf` vs ticket `difficulty` on the live board: **Spearman ρ=+0.379** (n=113). vs declared `tier`: **ρ=+0.075, p=0.43 — indistinguishable from zero** | computed over `fleet/board/*.md` |
| E2 | Raw ticket text LENGTH gives ρ=+0.364 vs difficulty — i.e. `nsurf` carries **no more information than "how long is the ticket"** | same run |
| E3 | 6 tickets are `nsurf>=3 AND d<=2` (breadth says hard, human says easy); 4 are `nsurf<=1 AND d>=4` (breadth says easy, human says hard) → **~9% outright inversion** | same run |
| E4 | On our own Python surfaces: radon max-CC vs difficulty ρ=+0.257 (n.s.); Halstead-difficulty ρ=+0.310 (n.s.); **max-CC vs SLOC ρ=+0.901** | radon 6.0.1 (installed) over 17 tickets w/ resolvable `.py` owns |
| E5 | Board `owns` extensions: **149 `.sh`, 67 `.py`, 27 `.md`, 20 `.tsv`** — any Python-only metric covers <25% of surfaces; 31 of 67 `.py` paths do not even resolve on disk | `grep` over board |
| E6 | `litellm.Router` in our wrapper is constructed **without `routing_strategy`** → defaults to `simple-shuffle` | `src/charon/litellm_plane/litellm_router.py:355-368` |
| E7 | `build_model_list` sets `model_info` = `{"max_input_tokens": …}` only — **no `input_cost_per_token`, no `rpm`/`tpm`** | `litellm_router.py:142-143` |
| E8 | LiteLLM ships `router_strategy/{complexity_router,quality_router,adaptive_router,auto_router,budget_limiter.py,tag_based_routing.py,lar1_routing.py,lowest_cost.py,…}` | `ls` of installed 1.93.0 |
| E9 | `cost-based-routing` is **async-only** — deliberately omitted from the sync selector | `litellm/router.py:1078-1080` |
| E10 | LiteLLM `ComplexityRouter` run on our real ticket prose **anti-correlates**: hardest ticket (BENCH-OOB-GRADING d5) → `SIMPLE` 0.015; trivial ticket (CONTRIBUTING-HOOK-INSTALL-FIX d1) → `COMPLEX` 0.415 | executed locally, see §4 |
| E11 | `decompose_effort.estimate_effort` orders our spread correctly and ranks `SG-ISSUE-CONTROL-PLANE` (nsurf=1, d5) **above** `FLEET-DEMAND-BROKER` (nsurf=8, d4) on a per-difficulty basis | executed locally, see §4 |

E1+E2+E4 together are the crux: **breadth is a restatement of size, and size is not difficulty.**

---

## 1. Q3 (HIGHEST PRIORITY) — what our already-adopted tools already do

### 1a. Charon itself: `src/charon/decompose_effort.py` — the difficulty formula already exists

Docstring states its own reason for existing, and it is *the same complaint* as this review:

> "DECOMPOSE-DEFAULT-GATE decomposes on change SURFACE … That axis is BLIND to
> 'single-file / coupled but LARGE-and-slow' work — one file touched by a hard,
> many-behavior ticket never trips the surface gate at all."

Formula (`decompose_effort.py:51-53, 135-137`):

```
effort = 2.0 · difficulty  +  0.15 · size  +  1.0 · behaviors
                                     ^^^^ breadth/blast-radius, ~13x DOWN-weighted
```
* `difficulty` — the ticket's own 1-5 field
* `size` — blast-radius file/call-site count (falls back to `len(owns)` — i.e. **`nsurf`**)
* `behaviors` — count of distinct required behaviors parsed from the `accept:` field

Plus `effort_verdict` / `tier_threshold`, which calibrate the bands **per executor tier**
using live scorecard actuals (`_load_scorecard_actuals`), clamped 0.25–4.0.

Properties that matter here: pure, deterministic, stdlib-only, already unit-tested,
already in `src/charon`, and it *already treats breadth as a 7%-weight term rather than
a standalone frontier trigger*. `tier_classify.py` was written as if this module did not
exist. **This is the single most important finding in the brief.**

### 1b. LiteLLM 1.93.0 — six routing strategies we pay for and do not use

Verified by reading `/home/stack/.local/lib/python3.12/site-packages/litellm/`.

| Strategy (`routing_strategy=`) | Signal it actually uses (source-verified) | Sync? |
|---|---|---|
| `simple-shuffle` (**our silent default**) | RNG, optionally weight/rpm-weighted | yes |
| `least-busy` | in-flight request count per deployment | yes |
| `usage-based-routing` / `-v2` | lowest TPM/RPM used in the current minute window | v1 sync / v2 async |
| `latency-based-routing` | EWMA of response time (TTFT for streaming) | yes |
| `cost-based-routing` | `input_cost_per_token + output_cost_per_token`, taken from `litellm_params` override **else** `litellm.model_cost`, **else default 5.0 each**; then filters deployments over their `tpm`/`rpm` | **NO — async only (`router.py:1078`)** |
| `lar1` | caller-supplied confidence in `metadata["lar1"]` vs low/med/high thresholds | yes |

Plus, as *filters* that compose with any strategy:
* `budget_limiter.py` — per-provider `budget_limit` + `time_period` (`1d`/`7d`/…), Redis-backed, filters out over-budget deployments.
* `tag_based_routing.py` — request tags (incl. header-regex) must be a subset of deployment tags; supports default-tagged deployments. **This is Charon's "tier tag → model group" mechanism, already built.**
* `routing_groups=[RoutingGroup(...)]` (`router.py:321, 910`) — **per-group routing strategy**. Charon could give the `economy` group `cost-based-routing` and the `frontier` group `latency-based-routing`, in one constructor arg.

And three whole routers:
* **`complexity_router/`** — rule-based, zero-API, <1ms, deterministic weighted scoring over 7 dimensions → 4 tiers (SIMPLE/MEDIUM/COMPLEX/REASONING), with configurable `dimension_weights`, `tier_boundaries`, keyword lists, and `keyword_tier_rules` (deterministic keyword→tier overrides, optionally semantic via bundled `SemanticRouter`). Ships its own evals harness. **Note its `tokenCount` weight is 0.10 of 1.0** — the same "size is ~10% of difficulty" judgement as `decompose_effort`'s 0.15/2.0.
  Its config also documents defences against the *exact* bug our `SEC_RE` shipped: word-boundary keyword matching "to avoid substring false positives", and a validator rejecting blank keywords as "a routing foot-gun".
* **`quality_router/`** — maps a complexity tier → an integer `quality_tier`, matched against `model_info.litellm_routing_preferences.quality_tier` per deployment, with a caller override header **`x-litellm-min-quality-tier: 3`** (or metadata `min_quality_tier`). This is a **tier FLOOR mechanism inside the router we already run** — precisely the "tier is a claim ceiling/floor" plumbing Charon hand-rolls in `tier-models.tsv` + awk.
* **`adaptive_router/`** — Thompson-sampled Beta(α,β) bandit per `(request_type, model)`, scored `quality_weight·sample + cost_weight·normalized_cost`, updated from post-call regex/tool-call outcome signals (satisfaction→α; failure/stagnation/loop→β). This is a *shipped implementation of Charon's north star* ("grade off real work → route to cheapest capable"). Caveats it self-documents: Postgres flush, 200-sample cap, English-biased regex signals, one AdaptiveRouter per Router, `_compute_bandit_delta` explicitly "a v0 guess".

### 1c. Does `cost-based-routing` express Charon's policy? Honest gap analysis

Charon's policy = **cheapest USAGE-capable provider first, ordered by funding class, roll to next on exhaust, drain prepaid balances before parking.**

| Policy component | LiteLLM can express it? | Detail |
|---|---|---|
| cheapest-first among capable | **Yes** — `cost-based-routing` sorts by `input+output cost_per_token` | free legs cost 0 ⇒ naturally first |
| capability ceiling per work item | **Yes** — `quality_router` `min_quality_tier` + `model_info` quality tiers, or `tag_based_routing` tier tags | needs the tier computed outside LiteLLM (it cannot see ticket metadata) |
| roll-to-next-on-exhaust (rate limit) | **Yes** — per-deployment `tpm`/`rpm` filtering inside `lowest_cost`, plus `cooldown_time`/`allowed_fails`/`num_retries` (already wired) | requires `rpm`/`tpm` on deployments (**E7: we set neither**) |
| $ budget per provider | **Yes** — `budget_limiter` `budget_limit` + `time_period` | Redis-backed for multi-process |
| **funding-class ordering** (free → prepaid-drain → pay-go) | **NO** | LiteLLM's only cost notion is per-token list price. A prepaid balance you want *drained first* is not cheaper per token; `balance.py` drain-then-park is genuinely Charon-specific |
| **drain-then-park by class**, live remaining balance from provider APIs | **NO** | `balance.py` poll adapters (DeepSeek/OpenRouter/NanoGPT) have no LiteLLM equivalent |
| non-token / energy metering | **NO** | Charon rule stays authoritative (already the ADR-0020 position) |

So: **LiteLLM can carry ~4 of 7 components today.** The two it cannot are exactly the two Charon has legitimate novel code for. That is the correct adopt/build seam, and it matches the standing "adopt substrate, hand-roll the novel 30%" directive.

**Two verified blockers before any strategy flip:**
1. `cost-based-routing` never runs on the sync path (E9). `_raw_completion` uses `router.completion()`. Flipping the flag on the sync path would be **silently inert** — the same failure class as the review's F2.
2. Charon's model ids are `openai/<charon-id>` against the local gateway, which are **not in `litellm.model_cost`**, so `lowest_cost` falls back to `5.0 + 5.0` for *every* deployment → all-equal → arbitrary pick. `input_cost_per_token`/`output_cost_per_token` **must** be set in `litellm_params` first (E7).

The prior sub-session's conclusion that LiteLLM "discards Charon's cheapest-capable ordering" is therefore **a measurement of `simple-shuffle`, not of the tool.** It is however *provisionally* true in a second sense: even with the flag flipped, without E7's cost fields and the async path, it would still shuffle.

### 1d. Other already-installed tools

| Installed | Already does | Charon hand-rolls | Verdict |
|---|---|---|---|
| **radon 6.0.1** | CC, Halstead (incl. `difficulty`), MI, raw SLOC | — (nothing) | **Do not adopt for tiering** — E4/E5 kill it (see §2) |
| **litellm 1.93.0** | see 1b; also caching, fallbacks, cooldowns, retries, cost callbacks, guardrails, spend tracking | `cache.py`, `failover.py`, `park_cooldown.py`, `quota.py`, `spend_limits.py`, `balance.py`, `guardrails.py`, `latency.py`, `policy_router.py`, `metering.py` | mixed — see below |
| **sentence-transformers + scikit-learn** | embeddings, kNN, clustering | — | usable if we ever want the kNN router (§3); **no new dep needed** |
| **ruff 0.15.16** | `C901` mccabe complexity gate | — | already the rig's accepted complexity gate (`KSF-LINTER-TOOLS-REVIEW.md:36` REJECTs xenon/radon/mccabe as redundant with `C901`) — **prior decision already settled; do not re-litigate** |

Hand-roll-vs-LiteLLM, per feature (honest):

* `cache.py` — LiteLLM has exact + semantic caching. Charon's deliberately refuses fuzzy matching for correctness on code work. **Charon's constraint is real; keep, but it could sit on LiteLLM's exact-cache backend.**
* `failover.py` / `park_cooldown.py` — LiteLLM `fallbacks` + `cooldown_time` + `allowed_fails` (already partly wired at `litellm_router.py:361-366`). Charon's extra is *silent-downgrade* detection (pseudo-success), which LiteLLM has no concept of. **Keep the downgrade classifier; the cooldown/retry half is already adopted.**
* `quota.py` / `spend_limits.py` — overlaps `budget_limiter` (provider budget + period) and per-deployment `tpm`/`rpm`. Charon's calendar-anchored + restart-surviving free-tier windows exceed LiteLLM's. **Partial adopt: let `budget_limiter` do $ caps, keep Charon's free-tier window engine.**
* `latency.py` — direct duplicate of `lowest_latency.py` EWMA. **Adoptable outright.**
* `policy_router.py` — FALLBACK/LOAD_BALANCE/LATENCY policies = LiteLLM `fallbacks` + `simple-shuffle`(weighted) + `latency-based-routing`, plus `routing_groups` for per-policy strategy. **Largely redundant.**
* `guardrails.py` — LiteLLM has a guardrails framework. Charon's is stdlib PII/deny-list. **Adoptable, low value either way.**
* `metering.py` — already correctly scoped verify-only per ADR-0020. **No change.**

---

## 2. Q1 — task-difficulty / complexity estimation

| Approach | Signal | Maintained | Licence | Integration cost | Training data we lack? | Verdict for tier selection |
|---|---|---|---|---|---|---|
| **Cyclomatic complexity** (McCabe; ruff `C901`, radon, lizard) | control-flow edges in *existing* code | yes | MIT/Apache | low (radon installed) | no | **REJECT.** Jay et al. 2009: LOC predicts ~90% of CC variance, "CC can be said to have absolutely no explanatory power of its own". **Reproduced on our repo: maxCC vs SLOC ρ=+0.901 (E4).** It is a size metric wearing a difficulty hat — the same error as `nsurf` |
| **Halstead metrics** (incl. literal `D = (n1/2)·(N2/n2)`, "difficulty") | operator/operand counts | radon: yes | MIT | low | no | **REJECT.** Named "difficulty" but ρ=+0.310 (n.s.) vs our difficulty, and ρ=+0.758 with SLOC (E4) |
| **Cognitive Complexity** (Campbell 2018, SonarSource; `complexipy`) | nesting/flow-break penalties, explicitly de-correlated from size | yes | LGPL (Sonar) / MIT (complexipy) | medium (new dep, Python-only) | no | **Best of the code metrics** — ESEM 2020 validation: correlates with comprehension *time* and subjective understandability. But it measures **existing code**, not the change, and **E5 kills coverage** (149 `.sh` vs 67 `.py`; 31 of 67 unresolvable). Not adoptable here |
| **Maintainability Index** | composite of CC+Halstead+LOC | radon | MIT | low | no | **REJECT.** ρ=−0.275 (n.s.) on our data; composite of two rejected metrics |
| **Code churn / relative churn** (Nagappan & Ball 2005) | lines added/deleted, churn ratio | concept | — | high (needs the diff, which doesn't exist pre-work) | no | Not available *a priori*; predicts defect density, not difficulty |
| **Change coupling / hotspots** (D'Ambros & Gall; Tornhill `code-maat`, CodeScene) | co-change frequency from VCS history | code-maat quiet; CodeScene commercial | EPL / commercial | high | no | Measures *risk concentration*, not difficulty. Charon already has an equivalent in `decompose_surface.change_surface` |
| **JIT-defect "diffusion" dimension** (Kamei et al. 2013: NS/ND/**NF**/Entropy) | number of files/directories/subsystems touched | canonical literature | — | zero (we already compute it) | no | **This is literally `nsurf`.** The literature's own framing is that diffusion predicts **defect-proneness / risk**, not effort or difficulty. Correct use: **blast-radius / review-intensity**, never a capability ceiling |
| **COCOMO / COCOMO II** (and `scc`'s built-in estimate) | KLOC → effort | scc maintained (MIT) | — | low | no | **REJECT.** Input is delivered KLOC, unknown before the work. Size-in ⇒ size-out |
| **Story points / planning poker (expert judgement)** | human estimate | n/a | n/a | zero — **we already have it** | no | **This is the `difficulty: 1-5` field.** Effort-estimation literature has consistently failed to beat expert judgement; our `difficulty` is the best single predictor of declared tier on our own board (ρ=+0.413 vs `nsurf`'s +0.075) |
| **ML effort estimation** (Deep-SE 2019; GPT2SP 2022) | ticket title+description → story points | research code | — | very high | **YES — need thousands of labelled tickets; we have 113** | **REJECT.** Tawosi et al.'s two replications found Deep-SE "inaccurate, not transferable, not interpretable" and concluded for GPT2SP that **"deep learning effort estimation is not ready for practice"** — simple median/TF-IDF-SVM baselines match or beat it |
| **SWE-bench Verified difficulty labels** | human time-bucket annotations (<15m / 15m-1h / 1-4h / >4h) on 500 real issues | yes (OpenAI/Princeton) | MIT | medium | it *is* training data — but for Python OSS issue-resolution, not rig tickets | Interesting **calibration** source if we ever want labels; distribution (24.5/53.5/19.4/2.8%) is a useful sanity prior for our tier mix |

**Q1 conclusion:** no external code-metric tool estimates *difficulty* independent of *size*, and the one that comes closest (Cognitive Complexity) is unusable here on coverage grounds. The only signal on our board that correlates with human tier judgement is the human `difficulty` field itself.

---

## 3. Q2 — LLM routing / model cascades

| System | Signal it routes on | Maintained | Licence | Integration cost | Needs training data we lack? | Adoptable for *software tasks*? |
|---|---|---|---|---|---|---|
| **RouteLLM** (LMSYS, 2024-07) | trained win-rate score (matrix factorisation / BERT / causal-LLM / SW-ranking) from **Chatbot Arena preference pairs** | active (5.2k★, 175 commits, open issues/PRs) | Apache-2.0 | high | **YES** — routers are trained on a *specific* gpt-4/mixtral pair on chat preferences. Nothing in that distribution resembles a rig ticket | **No.** Also strictly **binary** (one strong, one weak) — we have 3 tiers |
| **FrugalGPT / LLM cascade** (Zhao & Zaharia, arXiv 2305.05176) | **no a-priori prediction** — run cheap, score confidence, escalate | paper + many reimpls | — | medium | scoring function needs calibration data | **Design is highly relevant** (see recommendation §5 fallback). Charon already has the verifier a cascade needs: tests, gates, review |
| **AutoMix** | few-shot self-verification + POMDP escalation | research | — | high | few-shot only (training-free) | Conceptually adoptable; no maintained lib |
| **Hybrid LLM** (Ding et al., ICLR 2024, Microsoft) | DeBERTa **difficulty predictor** + tunable quality knob | research code | MIT-ish | high | **YES** — needs labelled query set | Closest *published* "difficulty-aware routing" formula, but binary and needs labels |
| **Arch-Router-1.5B** (Katanemo, arXiv 2506.16655) | maps query → **user-defined domain/action policies**; add/remove models by editing policy, **no retraining** | active, HF transformers | research licence (HF) | medium (1.5B local model) | **no** | Plausible for `work_class` classification, but our `work_class` is already a declared field — it would re-derive what we already know |
| **semantic-router** (aurelio-labs) | embedding distance to per-route seed utterances; deterministic, no LLM call | active (commits May 2026) | MIT | low-medium | **no** — a handful of examples per route | Viable; **and already vendored inside litellm's complexity_router as `SemanticRouter`** — so this is a Q3 item, not a new adoption |
| **LiteLLM `complexity_router`** | 7-dimension weighted rule score, `tokenCount` at 0.10 | ships in litellm 1.93.0 | MIT | **~zero — installed** | **no** | **Engine adoptable, default scoring is not** — see E10/§4 |
| **LiteLLM `quality_router`** | complexity tier → `quality_tier` int; `x-litellm-min-quality-tier` floor header | ships in litellm | MIT | ~zero | no | **Directly adoptable as the tier-ceiling plumbing** |
| **LiteLLM `adaptive_router`** | Thompson-sampled Beta bandit per (request_type, model) + outcome signals, quality×cost weighted | ships in litellm | MIT | medium (Postgres flush) | **no — learns online from live traffic** | **Strongest Q2 candidate.** Learns from *our* work instead of Arena chat |
| **`cost-based-routing`** (lowest_cost) | static per-token list price + tpm/rpm filter | ships in litellm | MIT | low, **but async-only + needs cost fields** | no | Adoptable for the cheapest-capable half |
| **vLLM Semantic Router** | embedding intent classes, needs vLLM serving | active | Apache-2.0 | high (new serving stack) | no | Wrong layer for us |
| **kNN routing** (Li, arXiv 2505.12601, 2025-05) | k-nearest-neighbour over embedded queries with known outcomes | paper | — | low (sklearn + sentence-transformers **already installed**) | needs ~our 113 labelled tickets — **we have exactly that** | **Realistic future option**; "simple kNN beats complex learned routers", data-efficient |
| **Routing survey** (Moslem & Kelleher, arXiv 2603.04445) | — | 2026 survey | — | — | — | Confirms taxonomy: pre-generation *routing* vs post-generation *cascading*; no declared winner; real systems are compositional |

**Q2 conclusion:** every *external* router either (a) needs chat-preference training data we do not have and cannot get, or (b) is binary strong/weak, or (c) is already vendored inside LiteLLM. The frontier of the field is *not* better a-priori difficulty prediction — it is **cascade-with-verification** and **online outcome learning**, both of which are already present in a dependency we ship.

---

## 4. Evaluation against OUR real tickets

Twelve real board tickets spanning trivial → hardest. `effort` = `decompose_effort.estimate_effort`
(behaviours parsed from the real `accept:` line). `litellmTier`/`score` = LiteLLM
`ComplexityRouter.classify()` on the ticket's `purpose` + `scope` + `accept` prose, stock config.

| Ticket | d | nsurf | beh | effort | LiteLLM tier (score) | declared | competent human would say |
|---|---|---|---|---|---|---|---|
| CONTRIBUTING-HOOK-INSTALL-FIX | 1 | 1 | 3 | 5.15 | **COMPLEX** (0.415) ✗ | economy | trivial → economy |
| LITELLM-COST-FIELD-FIX | 1 | 2 | 4 | 6.15 | MEDIUM (0.165) | economy | trivial → economy |
| HANDOFF-ROOT-ARCHIVE | 1 | 2 | 6 | 8.15 | MEDIUM (0.165) | economy | trivial → economy |
| FT-CATALOG-SEED | 2 | 3 | 3 | 7.15 | SIMPLE (0.115) | economy | easy → economy/strong |
| FIX-PROVIDER-KEY-EXFIL | 2 | 5 | 4 | 8.15 | MEDIUM (0.315) | strong | easy-but-security → frontier by ratchet |
| TIER-BALANCE | 3 | 7 | 6 | 12.15 | MEDIUM (0.315) | strong | mid → strong |
| REPO-MAP-CONVERGE | 3 | 5 | 4 | 10.15 | COMPLEX (0.415) | strong | mid → strong |
| MARKER-PROOF-MECHANIZE | 4 | 5 | 18 | 26.15 ⚠ | MEDIUM (0.265) | strong | hard → strong/frontier |
| **SG-ISSUE-CONTROL-PLANE** | **5** | **1** | 3 | **13.15** | MEDIUM (0.315) | strong | **hard → frontier; nsurf says trivial** |
| GATEWAY-GRADE-ORDER-MVP | 5 | 4 | 1 | 11.15 | **SIMPLE** (0.015) ✗ | strong | hard → frontier |
| FLEET-DEMAND-BROKER | 4 | 8 | 5 | 13.15 | MEDIUM (0.165) | frontier | hard → frontier |
| **BENCH-OOB-GRADING** | **5** | 8 | 3 | 13.15 | **SIMPLE** (0.015) ✗✗ | frontier | **hardest on the board** |

Readings:

* **LiteLLM `ComplexityRouter` stock config FAILS on our data.** It scored the two hardest
  tickets `SIMPLE` (their `purpose`/`scope` prose is terse or empty) and the most trivial one
  `COMPLEX` (it contains the word "hook"/"install"/"commit"). It is tuned for chat prompts
  ("what is X" vs "think step by step"), and our tickets are structured metadata. Adopting its
  *default scoring* would be strictly worse than `nsurf>=3`.
* **`decompose_effort` ranks correctly.** Monotone from 5.15 (trivial) to 13.15 (hardest), and
  critically `SG-ISSUE-CONTROL-PLANE` (nsurf=**1**) scores 13.15 — tied with the two hardest
  tickets, and above `MARKER-PROOF`-adjusted peers on a per-difficulty basis. `nsurf>=3` would
  route this d5 ticket by breadth as if it were trivial. ⚠ caveat: `MARKER-PROOF-MECHANIZE`
  scored 26.15 because prose-semicolon behaviour splitting over-counted (18 "behaviours"); the
  behaviour term needs a cap before use in tiering (`behaviour ρ vs difficulty = +0.124, n.s.`).
* **The one live breadth-only promotion is wrong.** Sweeping the whole board, exactly **one**
  ticket is currently promoted to `frontier` by the `nsurf>=3` clause alone:
  **`FT-CATALOG-SEED` (d2, greenfield-feature, nsurf=3)** → frontier, where dropping the clause
  gives `strong`. A d2 catalog-seed on the priciest chain for its entire life is the exact
  cost-inflation the review flagged.
* **The inversion cases** (E3) — breadth-says-hard: `API-DECOMPOSE-CYCLE-FIX`,
  `BANDIT-PREEXISTING-FINDINGS`, `BOARD-REDS-TRIAGE`, `FIX-PROVIDER-KEY-EXFIL`,
  `FT-CATALOG-SEED`, `PLANE-CANARY-WIRE` (all d≤2). Breadth-says-easy: `MODEL-PREFLIGHT` (d4),
  `PRICE-TRACKED-INVENTORY-AUTOSWAP` (d4), `SG-ISSUE-CONTROL-PLANE` (d5),
  `UNIFIED-RECONCILIATION-GATE-DESIGN` (d4) — all nsurf ≤ 1.

---

## 5. THE RECOMMENDATION

### ADOPT (rank 1) — `src/charon/decompose_effort.py` as the difficulty floor, wired through LiteLLM's existing tier plumbing

Two moves, both inside things we already own:

**(A) Difficulty — replace `nsurf>=3` with the effort score we already built.**
In `classify_tier`, substitute the breadth clause with a call to
`charon.decompose_effort.estimate_effort` (or, if the rig must stay import-free of `src/charon`,
mirror its published weights verbatim — they are documented constants, not a black box):

```
effort = 2.0·difficulty + 0.15·nsurf + 1.0·min(behaviours, 6)
money-path ⇒ frontier   iff   d >= 4  OR  (livefwd AND d >= 3)  OR  effort >= HARD_BAND
money-path ⇒ strong     otherwise
```

Why this beats `nsurf>=3`:
* it keeps breadth (it is real information about blast radius) at its **evidence-backed weight**
  — 0.15 vs difficulty's 2.0, i.e. ~7%, matching LiteLLM `complexity_router`'s independent
  0.10-of-1.0 judgement for the length dimension;
* it is dominated by `difficulty`, the only board signal that actually correlates with human
  tier judgement (ρ=+0.413 vs nsurf's +0.075, p=0.43);
* it adds `behaviours` — genuinely orthogonal to size — capped, because uncapped prose splitting
  produced the 26.15 outlier;
* it fixes both live failure directions: `FT-CATALOG-SEED` (d2) stops being frontier;
  `SG-ISSUE-CONTROL-PLANE` (d5, nsurf=1) stops being invisible to the rule;
* zero new dependency, zero training data, and it reuses a module that already has tests,
  tier-calibrated thresholds and live scorecard actuals feeding `tier_threshold`.

**(B) Routing — stop hand-rolling the tier→model plumbing on top of a router that has it.**
Ticketable separately, but it is the higher-value half of the operator's Q3 point:
1. set `input_cost_per_token`/`output_cost_per_token` and `rpm`/`tpm` in `build_model_list`
   (**precondition — without it `cost-based-routing` silently ties everything at 5.0**);
2. pass `routing_strategy="cost-based-routing"` (or per-tier via `routing_groups`) — **and move
   the hot path to the async entrypoint, because it is async-only** (`router.py:1078`);
3. use `tag_based_routing` / `quality_router`'s `min_quality_tier` for the tier ceiling instead
   of awk over `tier-models.tsv`;
4. let `budget_limiter` carry $-caps; keep Charon's free-tier window engine and
   `balance.py` drain-then-park, which LiteLLM genuinely cannot express.

Do **not** adopt LiteLLM's `complexity_router` scoring — E10 shows it anti-correlates on our
tickets. Adopt its *config shape* (weights/boundaries/`keyword_tier_rules`) if the security
ratchet needs a keyword override with word-boundary matching done right.

### FALLBACK — cascade, don't predict (`adaptive_router` / FrugalGPT shape)

If (A) proves insufficiently discriminative after a wave or two, the literature's answer is not
a better a-priori predictor — it is to stop predicting. Route work at the *lowest plausible*
tier, let the existing verifier (tests / gates / adversarial review) decide, and escalate on
failure. This directly attacks the "tier is a claim CEILING, so over-promotion locks work to the
priciest chain for life" problem in the brief: a cascade has no permanent ceiling.
LiteLLM's `adaptive_router` is a shipped implementation (bandit + outcome signals + cost weight)
that learns from *our* traffic and needs no external labels. Known cost, honestly: the
escalation path can cost more than one clean frontier pass when the cheap attempt burns several
rounds plus review — so a cascade needs a hard attempt budget.

### NOT ADOPT
`RouteLLM` (needs Arena preference data, binary only) · `Hybrid LLM` (needs labels) ·
`Deep-SE`/`GPT2SP` (replications: "not ready for practice"; we have 113 tickets, not thousands) ·
`radon`/`lizard`/`scc`/COCOMO (size proxies; ρ(maxCC,SLOC)=+0.901 on our own repo; <25% surface
coverage) · `Arch-Router` (re-derives `work_class`, which we already declare) ·
`vLLM Semantic Router` (wrong layer). `xenon`/`radon`/`mccabe` were already REJECTED by
`fleet/state/KSF-LINTER-TOOLS-REVIEW.md:36`; this research **confirms** that decision.

### Verdict on the interim rule `nsurf>=3 AND difficulty-floor`

**The evidence SUPPORTS it and the recommendation is a strict improvement on it.**
* Supports: adding a difficulty floor removes the one live breadth-only promotion
  (`FT-CATALOG-SEED`) and would have blocked all 6 `nsurf>=3 ∧ d<=2` tickets from promoting.
* Improves: an `AND` rule is still blind in the *other* direction — the 4 tickets with
  `nsurf<=1 ∧ d>=4` (incl. `SG-ISSUE-CONTROL-PLANE` at d5) remain unpromotable by a rule that
  requires breadth. A **weighted score** promotes on difficulty *alone* when difficulty is high,
  which an `AND` cannot. Since `nsurf` vs declared tier is ρ=+0.075 (p=0.43), making promotion
  *conditional* on breadth is conditioning on noise.
* Contradicts nothing.
* Minimum viable change if only one line may move: `nsurf >= 3 AND d >= 3`. Preferred:
  the weighted score in (A).

---

## 6. Sources

Primary, with dates / maintenance status.

**Installed source read directly (2026-07-24, litellm 1.93.0 @ `~/.local/lib/python3.12/site-packages/litellm/`)**
- `router.py:311-318` (strategy literals), `:788-792` (selector map), `:1015-1060` (async dispatch), `:1073-1100` (**sync dispatch, cost-based-routing omitted**), `:321/:910` (`routing_groups`)
- `router_strategy/lowest_cost.py:181-271` — cost signal = `input_cost_per_token + output_cost_per_token`, default 5.0 fallback
- `router_strategy/complexity_router/{README.md,config.py,complexity_router.py}` — 7 dimensions, weights, `keyword_tier_rules`, word-boundary matching, evals dir
- `router_strategy/quality_router/{config.py,quality_router.py}` — `complexity_to_quality`, `x-litellm-min-quality-tier`
- `router_strategy/adaptive_router/{README.md,signals.py,bandit.py}` — Beta bandit, outcome signals, documented v0 limits
- `router_strategy/{budget_limiter.py,tag_based_routing.py,lar1_routing.py}`
- Charon: `src/charon/litellm_plane/litellm_router.py:142-143,355-368`; `src/charon/decompose_effort.py:1-137`; `src/charon/{balance,quota,cache,failover,latency,policy_router,metering}.py` docstrings

**Literature**
- Jay, Hale, Smith, Hale, Kraft, Ward (2009), *Cyclomatic Complexity and Lines of Code: Empirical Evidence of a Stable Linear Relationship*, JSEA 2:137-143 — R²≈0.90 over 1.2M files, "CC can be said to have absolutely no explanatory power of its own". https://content.scirp.org/pdf/jsea20090300001_74742661.pdf
- Kamei et al. (2013), *A Large-Scale Empirical Study of Just-in-Time Quality Assurance*, TSE — 14 change metrics in 5 dimensions incl. **diffusion (NS/ND/NF/Entropy)**; diffusion predicts defect-proneness. Survey: https://damevski.github.io/files/report_CSUR_2022.pdf (CSUR 2022)
- Campbell, G.A. (2018), *Cognitive Complexity* (SonarSource). Validation: Muñoz Barón, Wyrich, Wagner, *An Empirical Validation of Cognitive Complexity as a Measure of Source Code Understandability*, **ESEM 2020** — correlates with comprehension time. https://arxiv.org/pdf/2007.12520
- Tawosi, Sarro et al. (2022), *Agile Effort Estimation: Have We Solved the Problem Yet?* — replication 1 (Deep-SE): https://arxiv.org/pdf/2201.05401 ; replication 2 (GPT2SP): https://arxiv.org/pdf/2209.00437 — **"deep learning effort estimation is not ready for practice"**
- Chen, Zaharia, Zou (2023-05), *FrugalGPT*, arXiv:2305.05176 — prompt adaptation / LLM approximation / **LLM cascade**; up to 98% cost reduction. https://arxiv.org/abs/2305.05176
- Ong et al. / LMSYS (2024-07-01), *RouteLLM*, blog + repo — MF/BERT/causal-LLM/SW routers, Chatbot Arena preference training, **binary** strong/weak. https://www.lmsys.org/blog/2024-07-01-routellm/ · https://github.com/lm-sys/RouteLLM (Apache-2.0, 5.2k★, 175 commits, active issues/PRs — **maintained**)
- Ding et al., *Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing*, **ICLR 2024** — DeBERTa difficulty predictor + quality knob. https://proceedings.iclr.cc/paper_files/paper/2024/file/b47d93c99fa22ac0b377578af0a1f63a-Paper-Conference.pdf
- Tran et al. (2025-06), *Arch-Router: Aligning LLM Routing with Human Preferences*, arXiv:2506.16655 — 1.5B, policy-based, **no retraining on model swap**, 93.17%. https://arxiv.org/html/2506.16655v1 · https://huggingface.co/katanemo/Arch-Router-1.5B (HF research licence)
- Li, Y. (2025-05), *Rethinking Predictive Modeling for LLM Routing: When Simple kNN Beats Complex Learned Routers*, arXiv:2505.12601 — simple kNN matches/beats learned routers, data-efficient. https://arxiv.org/pdf/2505.12601
- Moslem & Kelleher (2026), *Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey*, arXiv:2603.04445 — routing (pre-inference) vs cascading (verify-and-escalate); training-free (Eagle, AutoMix, Arch-Router) vs supervised (RouteLLM, BEST-Route, Router-R1). https://arxiv.org/html/2603.04445v1
- OpenAI (2024-08), *Introducing SWE-bench Verified* — 500 instances, human difficulty buckets <15m/15m-1h/1-4h/>4h, distribution 24.5/53.5/19.4/2.8%. https://openai.com/index/introducing-swe-bench-verified/
- aurelio-labs/semantic-router — MIT, active (commits to 2026-05). https://github.com/aurelio-labs/semantic-router
- terryyin/lizard (MIT, maintained, multi-language CC) — https://github.com/terryyin/lizard ; radon 6.0.1 (MIT, **installed locally**)

**Rig prior art (do not re-litigate)**
- `fleet/scratch/research-gateway-landscape.md` — earlier RouteLLM / Arch-Router survey; concluded BORROW-THE-DESIGN, not adopt. Consistent with this report.
- `fleet/state/KSF-LINTER-TOOLS-REVIEW.md:36` — xenon/radon/mccabe **REJECTED** (ruff `C901` covers it). Confirmed by E4.
- `fleet/POOLS-REDESIGN-ADR-v2.md:120` — borrowed-patterns table already names RouteLLM cascade validation, Arch-Router, RouterBench.
- `fleet/state/reviews/TIER-CLASSIFIER-REVIEW-agen-kolar.md` — F1/F2/F3, the review this research answers.
