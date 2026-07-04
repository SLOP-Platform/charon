"""Tests for response_normalizer module."""
from __future__ import annotations

from charon.response_normalizer import NormalizeMode, ResponseNormalizer


def test_none_passthrough() -> None:
    content = "Hello, world!"
    assert ResponseNormalizer.normalize(content, NormalizeMode.NONE) == content


def test_strip_boilerplate_opening() -> None:
    content = "Here is the answer:\nactual text"
    result = ResponseNormalizer.normalize(content, NormalizeMode.STRIP_BOILERPLATE)
    assert result == "actual text"


def test_strip_boilerplate_closing() -> None:
    content = "actual text\nLet me know if you need anything else!"
    result = ResponseNormalizer.normalize(content, NormalizeMode.STRIP_BOILERPLATE)
    assert result == "actual text"


def test_strip_boilerplate_mid_text_preserved() -> None:
    content = "some intro\nHere is the middle part\nsome outro"
    result = ResponseNormalizer.normalize(content, NormalizeMode.STRIP_BOILERPLATE)
    assert "Here is the middle part" in result


def test_fix_json_trailing_comma() -> None:
    result = ResponseNormalizer.normalize('{"a": 1,}', NormalizeMode.FIX_JSON)
    assert result == '{"a": 1}'


def test_fix_json_trailing_comma_in_array() -> None:
    result = ResponseNormalizer.normalize("[1, 2,]", NormalizeMode.FIX_JSON)
    assert result == "[1, 2]"


def test_fix_json_unbalanced_braces() -> None:
    result = ResponseNormalizer.normalize('{"a": {"b": 1}', NormalizeMode.FIX_JSON)
    assert result == '{"a": {"b": 1}}'


def test_fix_json_extract_from_fence() -> None:
    content = '```json\n{"a": 1}\n```'
    result = ResponseNormalizer.normalize(content, NormalizeMode.FIX_JSON)
    assert result == '{"a": 1}'


def test_fix_json_single_quoted_keys() -> None:
    result = ResponseNormalizer.normalize("{'a': 1}", NormalizeMode.FIX_JSON)
    assert result == '{"a": 1}'


def test_standardize_md_heading_space() -> None:
    result = ResponseNormalizer.normalize("##Title", NormalizeMode.STANDARDIZE_MD)
    assert result == "## Title"


def test_standardize_md_code_fence_lowercase() -> None:
    result = ResponseNormalizer.normalize("```JSON", NormalizeMode.STANDARDIZE_MD)
    assert result == "```json"


def test_standardize_md_excessive_blank_lines() -> None:
    content = "line1\n\n\n\n\nline2"
    result = ResponseNormalizer.normalize(content, NormalizeMode.STANDARDIZE_MD)
    assert "\n\n\n\n" not in result


def test_standardize_md_blank_line_before_list() -> None:
    content = "some text\n- item"
    result = ResponseNormalizer.normalize(content, NormalizeMode.STANDARDIZE_MD)
    assert result == "some text\n\n- item"


def test_mode_from_string() -> None:
    mode = NormalizeMode("strip_boilerplate")
    assert mode == NormalizeMode.STRIP_BOILERPLATE
