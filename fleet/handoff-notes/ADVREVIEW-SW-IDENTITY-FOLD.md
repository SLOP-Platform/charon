# Adv Review: SW-IDENTITY-FOLD — findings

**Reviewer:** cal-kestis (deepseek-v4-pro)
**Date:** 2026-07-26
**Change:** `46eab38` on `fix/sw-identity-fold`
**Verdict:** MERGE — no BLOCKING defect found.

## Severity breakdown

| Severity | Count |
|---|---|
| BLOCKING | 0 |
| SHOULD-FIX | 5 |
| NIT | 2 |

## What I verified by RUNNING

- `PYTHONPATH=src python3 -m pytest -q tests/test_model_identity_fold.py` — 3/3 GREEN.
- `PYTHONPATH=src python3 -c "..."` — traced 14 real catalog IDs through `_normalize_model_id`, confirmed expected behavior.
- Python interactive tracing of all 3 regexes against every live catalog ID containing `:` or a quant suffix to confirm no false matches.

## What I verified by READING

- Full `/home/stack/.charon/models.json` — 620-model live catalog (the committed gateway catalog).
- `src/charon/proxy.py:268-324` — the three regexes + while loop + `_normalize_model_id`.
- `tests/test_model_identity_fold.py` — all 38 corpus entries.
- `src/charon/routing_policy/catalog_refresh.py:61-68` — `_normalize()` delegates to `_normalize_model_id`, verifying this is a single-point-of-truth.
- `docs/adr/0011-the-switchboard-demand-routed-no-pools.md` — INV-SW1/2/3 invariants.

---

## Findings

### F1 — awq/gptq/w8a8 folding is untestable against live data (SHOULD-FIX)
**Location:** `src/charon/proxy.py:269`
**Scenario:** The live catalog (620 entries) contains ZERO models with `-awq`, `-gptq`, or `-w8a8` suffixes. These regex additions are dead code — untestable. The corpus tests (`deepseek-v3-awq`, `llama-3.3-70b-gptq`, `model-w8a8`) use synthetic IDs that don't exist. Since awq/gptq are quantization METHODS producing measurably different weight matrices (unlike simple precision casts `fp4→fp8`), folding them is a different risk profile from the rest of the quant family. Without a live specimen, nobody can prove the fold is safe.
**Fix:** Either (a) remove awq/gptq/w8a8 from the regex until a live instance appears and can be verified, or (b) document in the regex comment that these are included speculatively and the risk profile differs from precision-tag suffixes because awq/gptq use different weight-producing algorithms.

### F2 — `:free`/`:nitro`/`:online` folding is untestable against live data (SHOULD-FIX)
**Location:** `src/charon/proxy.py:285-286` (`_MODE_SUFFIX`)
**Scenario:** The live catalog contains ZERO models with `:free`, `:nitro`, or `:online` suffixes. The regex `:(?:free|nitro|online)$` matches nothing in the real corpus. When a `:free` model DOES appear (e.g., from Together, Groq, or another provider), the fold activates blind — nobody has tested whether a `:free` tier delivers the same quality as the paid variant. If `:free` has lower rate limits, reduced context, or a lower-quality underlying model version, folding means a paid request silently gets free-tier quality. This is a money-path risk.
**Fix:** Either (a) await a live `:free` specimen before folding, or (b) add a concrete failure-scenario test from the first live entry observed.

### F3 — `:low`/`:medium`/`:high`/`:max` colon suffixes are stranded (SHOULD-FIX)
**Location:** `src/charon/proxy.py:285-286` (`_MODE_SUFFIX`) and the builder's deliberate-exclusion comment (lines 282-284)
**Failure scenario:** 
- The live catalog contains `nanogpt/coding-router:low`, `:medium`, `:high`, `:max` — 4 real entries creating 4 separate pool IDs (`coding-router:low`, `coding-router:medium`, etc.) plus the bare `coding-router` pool. These are nanogpt's capacity/budget tiers — the same underlying coding-router model at different priority levels. They are functionally equivalent to `:free`/`:nitro`/`:online` (deployment/capacity tiers, not model-class changes) but use different label names. The builder's regex only matches `:free|:nitro|:online`, leaving these 4 live entries stranded in their own pools.
- The builder's comment (lines 282-284) documents `:thinking` and `:reasoning` as deliberate exclusions but says NOTHING about `:low`/`:medium`/`:high`/`:max`. They're neither folded nor documented. This is the INV-SW2 strand class in miniature: 4 separate pools for one model, silently splitting demand across pool boundaries.
**Fix:** Either add `:low|:medium|:high|:max` to `_MODE_SUFFIX` (fold them) or document them as deliberate non-folds in the code comment, stating WHY they differ from `:free`/`:nitro`/`:online`.

### F4 — Corpus does not test live `-thinking` (hyphen-form) preservation (SHOULD-FIX)
**Location:** `tests/test_model_identity_fold.py` corpus
**Failure scenario:** The live catalog has 5+ entries with hyphen-form `-thinking` suffix: `deepseek-ai/deepseek-v3.2-exp-thinking`, `gemini-2.5-flash-preview-04-17-thinking`, `gemini-2.5-flash-preview-09-2025-thinking`, etc. These are ALL treated as non-folds (correctly) because `-thinking` is not in any regex. But the corpus only tests `model:thinking` and `model:reasoning` — the colon forms. The hyphen form `-thinking` is preserved purely by regex silence. If someone adds `-thinking` to `_QUANT_SUFFIX` in a future edit (it starts with `-`, ends at the end of the string — pattern-fit to the quant regex), the corpus would stay GREEN and the non-fold would silently break. Example: `deepseek-ai/deepseek-v3.2-exp-thinking` → currently `deepseek-v3.2-exp-thinking`, but adding `-thinking` to QUANT would fold it to `deepseek-v3.2-exp` — a genuinely different model merged into the non-thinking pool.
**Fix:** Add `("deepseek-ai/deepseek-v3.2-exp-thinking", "deepseek-v3.2-exp-thinking", "hyphen-thinking NOT folded — different model variant")` to the corpus. Similarly add `("deepseek-ai/deepseek-v3.2-exp", "deepseek-v3.2-exp", "base model without thinking")` to confirm the pair stays separate.

### F5 — Claude thinking-budget colon suffixes (`:1024`/`:8192`/`:32768`/`:64000`/`:32000`) not in deliberate-exclusion comment (SHOULD-FIX)
**Location:** `src/charon/proxy.py:282-284`
**Scenario:** The live catalog has `claude-sonnet-4-thinking:1024`, `claude-opus-4-thinking:8192`, etc. — 18 real entries with numeric colon-suffixes representing thinking token budgets. These are correctly NOT folded (they're not in `_MODE_SUFFIX`), but the code comment only documents `:thinking`/`:reasoning` as deliberate exclusions. The numeric budget suffixes (`:1024`/`:8192` etc.) are excluded by regex silence, not by explicit decision. A future maintainer might add these numeric suffixes to `_MODE_SUFFIX` thinking they're deployment tiers, silently folding different thinking-budget variants together.
**Fix:** Extend the comment (lines 282-284) to list `:1024`/`:8192`/`:32768`/`:64000`/`:32000` as deliberate non-folds because they represent different thinking budgets (quality-affecting), distinct from `:free`/`:nitro`/`:online` (capacity-affecting).

### F6 — `:reasoning` non-fold is dead code (NIT)
**Location:** `tests/test_model_identity_fold.py` line 88
**Observation:** The live catalog contains ZERO `:reasoning`-suffixed entries. The corpus entry `("model:reasoning", "model:reasoning", ...)` tests behavior that has no live counterpart. This is not harmful (it's a defensive guard), but the documentation describes it as if it occurs in the wild.
**Fix:** Replace `model:reasoning` with a real catalog ID that exercises the same path, or add a note that this is speculative.

### F7 — Corpus is FP-centric but live catalog quant-suffix diversity is low (NIT)
**Location:** `tests/test_model_identity_fold.py` — the 13 quant-suffix corpus entries
**Observation:** The live catalog (620 models) has exactly 3 quant-suffixed entries: `FP4`, `FP8`, `BF16`. The corpus tests 13 quant forms (fp4, fp8, fp16, fp32, bf16, int8, int4, nvfp4, mxfp4, awq, gptq, w8a8, GGUF q4_k_m/q5_0/q8_0) — a 4:1 ratio of tested-to-real. The corpus is inflated with synthetic entries. The fail-on-revert property only defends against _removing_ items from the regex; it does not prove the items SHOULD be in the regex. A corpus that tests what the regex already does and nothing that the regex doesn't is weaker than it looks.
**Fix:** Add more real-catalog entries to the corpus that test the behavior the regex does NOT alter: the preserved `-thinking`, `:thinking`, `-latest`, `-preview` from actual live IDs. A more balanced ratio of fold-to-non-fold entries makes the corpus harder to subvert.

---

## Items where I looked hard and found NOTHING

### Over-folding two genuinely different models into one pool
Searched all 620 entries for pairs that would collide after normalization. The only collision found is the INTENDED one: `MiniMaxAI/MiniMax-M2.5-FP4` (baseten) and `minimax/minimax-m2.5` (nanogpt) both normalize to `minimax-m2.5`. The builder's design says FP4 is "same model, different precision" — defensible under the Switchboard model since cost-rank routing will use the cheaper leg. No unintended collision found.

### Order dependence in the while loop
Traced all cross-family stacking patterns: quant+mode (`model-fp8:free`), quant+marketing (`model-fp8-turbo`), triple (`model-fp4-instruct:free`). The while loop re-applies all three regexes each iteration. Since each regex matches at `$` (end of string), stripping one suffix exposes the next on the following iteration. Proved order-independent by tracing both `model-fp8:free` and `model:free-fp8` — both converge to `model`. No order-dependent failure found.

### False match on model-name segments
Verified that NO model in the live catalog has a name ending in a string that `_QUANT_SUFFIX` would incorrectly match. For example, no model ends in `-int8` as a genuine name segment (all live catalog entries ending in recognizable quant suffixes are actual quant variants).

### non-vacuous corpus and fail-on-revert
Running the test GREEN. Verified by reading that `test_corpus_non_vacuous` asserts `len(_CORPUS) > 0`. Verified by reading that `test_fp4_case_named_on_failure` would fail if `_QUANT_SUFFIX` omitted fp4. The corpus is non-vacuous (38 entries) and the fail-on-revert guard is correctly wired.

---

## Summary

| Attack vector | Result |
|---|---|
| awq/gptq/w8a8 fold | **Untestable** — 0 live entries. Dead code with theoretical quantum-method risk (F1). |
| `:free` fold | **Untestable** — 0 live entries (F2). |
| Non-fold `-latest`/`-hf` | **Defensible** — 16 `-latest` entries correctly not folded; 1 `-hf` entry correctly not folded. Safe: too-many-pools is safer than too-few. |
| Stranded families | **FOUND** — `:low`/`:medium`/`:high`/`:max` (4 entries) neither folded nor documented (F3). Numeric thinking-budget suffixes not documented (F5). |
| Order dependence | **CLEAN** — loop handles inter-family stacking correctly. |
| Over-folding | **CLEAN** — only the intended fp4 fold found; no unintended collisions. |
| Corpus honesty | **WEAK** — too many synthetic folds, too few live-preservation tests (F4, F6, F7). Ratio 13 quant-folded : 2 live-quant. The hard cases from the live catalog are the ones NOT folding, and the corpus under-tests them. |

**Single most dangerous finding:** F3 — `coding-router:low|:medium|:high|:max` are 4 live entries that form 4 separate orphan pools because the regex only covers `:free|:nitro|:online`. These are deployment-capacity tiers on the same underlying model, analogous to the suffixes the builder CHOSE to fold. The code comment explicitly documents `:thinking`/`:reasoning` as deliberate exclusions but is silent on these 4 — the strand is invisible.
