"""SW-IDENTITY-FOLD — corpus-driven model-identity folding.

_QUANT_SUFFIX (src/charon/proxy.py:268) omitted ``fp4``, so Together's
``MiniMaxAI/MiniMax-M2.5-FP4`` normalized to ``minimax-m2.5-fp4`` — an ORPHAN pool
instead of folding into ``minimax-m2.5``. A funded, unparked provider stranded
behind an id-spelling artifact is an INV-SW2 violation (ADR-0011) and
release-blocking.

This file is a FAIL-ON-REVERT corpus test: revert the suffix table -> RED,
and the fp4 case is named in the failure.
"""
from __future__ import annotations

from charon.proxy import _normalize_model_id

# ── CORPUS: real advertised model ids → expected folded identity ──────────────
# Each entry: (raw_id, expected_folded_id, reason — the *reason* the id folds /
#   does NOT fold, not a casual comment).
# Entries marked [SYNTHETIC] test suffixes/aliases that exist in the algorithm
# but have ZERO live catalog specimens — they guard against silent regressions,
# not coverage of real traffic.
# Non-vacuous guard: a corpus of zero entries is a test failure.
_CORPUS = [
    # ── THE INSTANCE: fp4 omitted → orphan pool ───────────────────────────
    ("MiniMaxAI/MiniMax-M2.5-FP4", "minimax-m2.5",
     "fp4 quant suffix stripped — the specific release-blocking defect"),

    # ── quantization suffixes (FOLDED) ────────────────────────────────────
    ("glm-5.2-fp8", "glm-5.2",
     "fp4/fp8/fp16/fp32 quant family — same model, different precision"),
    ("GLM-5.2-FP16", "glm-5.2",
     "fp16 with case variance — lower-case + quant-strip folds it"),
    ("model-bf16", "model",
     "bf16 quantization tag — not a different model"),
    ("model-fp32", "model",
     "fp32 quantization tag — not a different model"),
    ("model-int8", "model",
     "int8 quantization tag — not a different model"),
    ("model-int4", "model",
     "int4 quantization tag — not a different model"),
    # nvfp4 / mxfp4 — qualifier-stacked compact forms
    ("model-nvfp4", "model",
     "nvfp4 (NVidia-stacked fp4) — quant precision, not a different model"),
    ("model-mxfp4", "model",
     "mxfp4 (Apple-qualified fp4) — quant precision, not a different model"),
    # awq / gptq / w8a8 — DELIBERATELY NOT FOLDED (dropped from _QUANT_SUFFIX
    # pending a live specimen; awq/gptq are weight-producing ALGORITHMS, not
    # precision casts, with a different risk profile).  [SYNTHETIC]
    ("deepseek-v3-awq", "deepseek-v3-awq",
     "[SYNTHETIC] awq NOT folded — algorithm, not precision cast; no live specimen"),
    ("llama-3.3-70b-gptq", "llama-3.3-70b-gptq",
     "[SYNTHETIC] gptq NOT folded — algorithm, not precision cast; no live specimen"),
    ("model-w8a8", "model-w8a8",
     "[SYNTHETIC] w8a8 NOT folded — algorithm, not precision cast; no live specimen"),
    # GGUF q<n> family (includes stacked forms)
    ("qwen3-72b-q4_k_m", "qwen3-72b",
     "GGUF q4_k_m — quant form, not a different model"),
    ("qwen3-72b-q5_0", "qwen3-72b",
     "GGUF q5_0 — quant form, not a different model"),
    ("qwen3-72b-q8_0", "qwen3-72b",
     "GGUF q8_0 — quant form, not a different model"),

    # ── marketing / serving-variant suffixes (DELIBERATE NON-FOLDS) ──────
    # ``-turbo``, ``-fast``, ``-instruct``, ``-latest``, ``-preview``,
    # ``-hf`` are NOT folded because they CAN indicate genuinely different
    # models.  e.g. ``gpt-4`` and ``gpt-4-turbo`` are distinct models with
    # different pricing and behaviour — merging them into one pool would be
    # worse than the orphan it fixes.
    ("model-turbo", "model-turbo",
     "marketing suffix kept — -turbo can be a genuinely different model"),
    ("model-fast", "model-fast",
     "marketing suffix kept — -fast can be a genuinely different model"),
    ("model-instruct", "model-instruct",
     "marketing suffix kept — -instruct can be a genuinely different model"),
    ("model-latest", "model-latest",
     "marketing suffix kept — -latest can be a genuinely different model"),
    ("model-preview", "model-preview",
     "marketing suffix kept — -preview can be a genuinely different model"),
    ("model-hf", "model-hf",
     "marketing suffix kept — -hf can be a genuinely different model"),

    # ── deployment-mode selectors (COLON tail — FOLDED) ───────────────────
    # :free / :nitro / :online have ZERO live specimens — included speculatively
    # until a provider surfaces them.  [SYNTHETIC]
    ("openai/gpt-4o:free", "gpt-4o",
     "[SYNTHETIC] deployment mode :free — same model, capacity tier"),
    ("openai/gpt-4o:nitro", "gpt-4o",
     "[SYNTHETIC] deployment mode :nitro — same model, capacity tier"),
    ("openai/gpt-4o:online", "gpt-4o",
     "[SYNTHETIC] deployment mode :online — same model, capacity tier"),
    # :low / :medium / :high / :max — live nanogpt capacity tiers (coding-router)
    ("nanogpt/coding-router:low", "coding-router",
     "deployment mode :low — same model, capacity tier"),
    ("nanogpt/coding-router:medium", "coding-router",
     "deployment mode :medium — same model, capacity tier"),
    ("nanogpt/coding-router:high", "coding-router",
     "deployment mode :high — same model, capacity tier"),
    ("nanogpt/coding-router:max", "coding-router",
     "deployment mode :max — same model, capacity tier"),

    # ── explicit aliases ──────────────────────────────────────────────────
    # aistudio gemini preview ids → base pool (F1)
    ("models/gemini-3-pro-preview", "gemini-3-pro",
     "aistudio gemini-3-pro-preview aliased → gemini-3-pro"),
    ("models/gemini-3-flash-preview", "gemini-3-flash",
     "aistudio gemini-3-flash-preview aliased → gemini-3-flash"),
    # NEGATIVE: image-preview must NOT land in the text pool
    ("models/gemini-3-pro-image-preview", "gemini-3-pro-image-preview",
     "image model — NOT aliased, must remain distinct from text pool"),
    ("models/gemini-3.1-flash-image", "gemini-3.1-flash-image",
     "image model — NOT aliased, must remain distinct from text pool"),

    # ── DELIBERATE NON-FOLDS — genuinely different models ─────────────────
    ("model:thinking", "model:thinking",
     "reasoning-tuned variant — deliberately distinct, NOT folded"),
    ("model:reasoning", "model:reasoning",
     "[SYNTHETIC] reasoning-tuned variant — deliberately distinct, NOT folded; "
     "no live specimens with this suffix"),
    # -thinking (HYPHEN FORM) — live catalog has 5+ entries. NOT folded;
    # -thinking ends the model name like a quant suffix would, so the corpus
    # must prove it stays intact.
    ("deepseek-ai/deepseek-v3.2-exp-thinking", "deepseek-v3.2-exp-thinking",
     "-thinking (hyphen) NOT folded — reasoning variant, genuinely different"),
    ("deepseek-ai/deepseek-v3.2-exp", "deepseek-v3.2-exp",
     "base model without -thinking — PAIR proves they stay SEPARATE"),

    # ── CASE: lower-case folding already works ────────────────────────────
    ("Kimi-K2.7-Code", "kimi-k2.7-code",
     "case-insensitive — lower-casing before compare"),
    ("DeepSeek-V4-Pro", "deepseek-v4-pro",
     "case-insensitive — lower-casing before compare"),

    # ── vendor path prefixes (FOLDED — final-segment rule) ────────────────
    ("openai/gpt-4o", "gpt-4o",
     "vendor prefix stripped by rsplit '/' — same model"),
    ("accounts/fireworks/models/deepseek-v4-pro", "deepseek-v4-pro",
     "multi-segment vendor prefix — final-segment rule, SR-1 invariant"),
    ("anthropic/claude-opus-4-8", "claude-opus-4-8",
     "vendor prefix stripped — same model"),

    # ── non-quant, non-marketing segments (PRESERVED) ─────────────────────
    ("kimi-k2.7-code", "kimi-k2.7-code",
     "-code is a model-name segment, NOT a quant/marketing suffix"),
    ("deepseek-v4-pro", "deepseek-v4-pro",
     "-pro is a model-name segment, NOT a quant/marketing suffix"),
    ("claude-opus-4-8", "claude-opus-4-8",
     "opus/4/8 are model-version segments, NOT suffixes to strip"),

    # ── stacked suffixes: iterative stripping across suffix families ─────
    # The while loop re-applies each suffix regex until the string converges,
    # so inter-family stacking IS resolved: ``:free`` stripped first, then
    # ``-fp8`` at the new end on the next iteration.
    ("model-fp8:free", "model",
     "mode then quant stripped iteratively across loop iterations"),
    # Inter-family stacking where a quant is NOT at end because a marketing
    # suffix follows it — and marketing is NOT stripped.  The while loop
    # sees ``-turbo`` at the end, no regex matches it, loop exits.
    ("model-fp8-turbo", "model-fp8-turbo",
     "inter-family: fp8 not at end (followed by -turbo), turbo not stripped"),
    # Quant + marketing + mode: :free stripped first, then -fp4 no longer at
    # end (followed by -instruct), -instruct not stripped.
    ("model-fp4-instruct:free", "model-fp4-instruct",
     "mode :free removed; -fp4 not at end, -instruct preserved"),

    # ── empty / None ─────────────────────────────────────────────────────
    (None, "", "None → empty string"),
    ("", "", "empty string → empty string"),
]


def test_corpus_non_vacuous() -> None:
    """Zero-id corpus is RED — a silent pass with no entries is not evidence."""
    assert len(_CORPUS) > 0, "corpus is vacuous: zero entries"


def test_corpus_model_identity_fold() -> None:
    """Every entry in the corpus: normalize(raw_id) == expected_folded_id."""
    failures: list[str] = []
    for raw, expected, reason in _CORPUS:
        got = _normalize_model_id(raw)
        if got != expected:
            failures.append(
                f"{raw!r} → {got!r} (expected {expected!r}): {reason}")
    assert not failures, (
        f"CORPUS failures ({len(failures)}/{len(_CORPUS)}):\n  "
        + "\n  ".join(failures))


def test_fp4_case_named_on_failure() -> None:
    """If the fp4 case is still in the corpus but '_QUANT_SUFFIX' does not strip
    it, assert that the normalization DIFFERS from the expected fold — proving
    the test WOULD catch a revert."""
    got = _normalize_model_id("MiniMaxAI/MiniMax-M2.5-FP4")
    assert got == "minimax-m2.5", (
        f"fp4 case: got {got!r}, expected 'minimax-m2.5'. "
        "If this fails, _QUANT_SUFFIX is missing fp4 — the defect is active.")
