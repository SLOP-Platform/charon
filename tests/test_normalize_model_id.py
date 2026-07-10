"""NORMALIZE-CASE-QUANT-FIX — case/quant-insensitive model-id compare.

`_normalize_model_id` used to compare the final path segment verbatim, so a
provider echoing the SAME model with cosmetic case variance ("Kimi-K2.7-Code" vs
pool "kimi-k2.7-code") or a quantization tag ("GLM-5.2-FP8" vs "glm-5.2") diffed
from the expected id, false-flagged a `pseudo_success` and served a spurious
`X-Charon-Downgrade` on an honest 200 — recording a working provider as a quality
FAILURE (why NeuralWatt scored 0/4 while actually working). The fix lower-cases and
strips the trailing quant suffix on BOTH ids WITHOUT breaking the SR-1
final-segment (namespace) compare.
"""
from __future__ import annotations

import sys
from pathlib import Path

from charon.proxy import GatewayProxy, _normalize_model_id

# The detector lives under tools/ (a gate enforcer, not an importable package).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_catalog_case_quant import find_mismatches  # noqa: E402


# ── unit: normalization primitive ──────────────────────────────────────────────
def test_case_insensitive() -> None:
    assert _normalize_model_id("Kimi-K2.7-Code") == _normalize_model_id(
        "kimi-k2.7-code")


def test_quant_suffix_stripped() -> None:
    assert _normalize_model_id("GLM-5.2-FP8") == "glm-5.2"
    assert _normalize_model_id("glm-5.2-fp16") == "glm-5.2"
    assert _normalize_model_id("glm-5.2-bf16") == "glm-5.2"
    assert _normalize_model_id("glm-5.2-int8") == "glm-5.2"
    assert _normalize_model_id("glm-5.2-int4") == "glm-5.2"
    assert _normalize_model_id("qwen3-72b-q4_k_m") == "qwen3-72b"
    assert _normalize_model_id("qwen3-72b-q5_0") == "qwen3-72b"


def test_namespace_final_segment_still_stripped() -> None:
    # SR-1 invariant: fully-qualified id folds to its bare final segment.
    assert _normalize_model_id(
        "accounts/fireworks/models/deepseek-v4-pro") == "deepseek-v4-pro"


def test_case_and_quant_and_namespace_compose() -> None:
    assert _normalize_model_id(
        "OpenCode-Go/GLM-5.2-FP8") == _normalize_model_id("glm-5.2")


def test_non_quant_suffix_preserved() -> None:
    # "-code"/"-pro" are model-name segments, NOT quant tags — must NOT be stripped.
    assert _normalize_model_id("kimi-k2.7-code") == "kimi-k2.7-code"
    assert _normalize_model_id("deepseek-v4-pro") == "deepseek-v4-pro"


def test_empty_and_none() -> None:
    assert _normalize_model_id(None) == ""
    assert _normalize_model_id("") == ""


# ── FAIL-ON-REVERT: client-observable downgrade outcome ─────────────────────────
def test_quant_case_variant_is_not_downgrade() -> None:
    """RED today, GREEN with the fix, RED again on revert. Asserts a case/quant
    variant of the SAME model is a clean success — NO pseudo_success, so NO
    `X-Charon-Downgrade` is served to the client."""
    p = GatewayProxy()
    # case-only variance
    obs = p.classify("opencode-go/kimi-k2.7-code", 200,
                     body={"model": "Kimi-K2.7-Code",
                           "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
                     expected_model="kimi-k2.7-code")
    assert obs.pseudo_success is False and obs.failover is False
    # quant-tag variance
    obs2 = p.classify("opencode-go/glm-5.2", 200,
                      body={"model": "GLM-5.2-FP8",
                            "usage": {"prompt_tokens": 8}},
                      expected_model="glm-5.2")
    assert obs2.pseudo_success is False and obs2.failover is False


def test_genuine_family_difference_still_flags_downgrade() -> None:
    # Guard: the fix must NOT disable real downgrade detection. A different family
    # (opus → haiku) survives lower-case + quant-strip and still fails over.
    p = GatewayProxy()
    obs = p.classify("anthropic/opus", 200,
                     body={"model": "Anthropic/Haiku", "usage": {"prompt_tokens": 6}},
                     expected_model="opus")
    assert obs.pseudo_success is True and obs.failover is True


# ── detector: tools/check_catalog_case_quant.py ─────────────────────────────────
def test_detector_flags_seeded_case_and_quant_mismatch() -> None:
    # Seeded non-canonical ids: an upper-case id and a quant-tagged id.
    problems = find_mismatches(["kimi-k2.7-code", "Kimi-K2.8-Code", "glm-5.2-fp8"])
    assert len(problems) == 2
    assert any("Kimi-K2.8-Code" in m for m in problems)
    assert any("glm-5.2-fp8" in m for m in problems)


def test_detector_flags_normalization_collision() -> None:
    # Two surface ids folding to one model → duplicate the menu must not ship.
    problems = find_mismatches(["glm-5.2", "GLM-5.2-FP8"])
    assert any("collision" in m for m in problems)


def test_detector_clean_canonical_catalog() -> None:
    assert find_mismatches(["glm-5.2", "kimi-k2.7-code", "claude-opus-4-8"]) == []

