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
    # awq / gptq / w8a8
    ("deepseek-v3-awq", "deepseek-v3",
     "awq quantization — not a different model"),
    ("llama-3.3-70b-gptq", "llama-3.3-70b",
     "gptq quantization — not a different model"),
    ("model-w8a8", "model",
     "w8a8 quantization — not a different model"),
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
    ("openai/gpt-4o:free", "gpt-4o",
     "deployment mode :free — same model, capacity tier"),
    ("openai/gpt-4o:nitro", "gpt-4o",
     "deployment mode :nitro — same model, capacity tier"),
    ("openai/gpt-4o:online", "gpt-4o",
     "deployment mode :online — same model, capacity tier"),

    # ── DELIBERATE NON-FOLDS — genuinely different models ─────────────────
    ("model:thinking", "model:thinking",
     "reasoning-tuned variant — deliberately distinct, NOT folded"),
    ("model:reasoning", "model:reasoning",
     "reasoning-tuned variant — deliberately distinct, NOT folded"),

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
