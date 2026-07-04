"""Response normalizer for LLM output content.

Operates on choices[0].message.content (or choices[0].delta.content for streaming)
strings.  All operations are stdlib string ops — no network, no external deps.
Each mode is self-contained and deterministic.
"""
from __future__ import annotations

import enum
import re


class NormalizeMode(enum.Enum):
    NONE = "none"
    STRIP_BOILERPLATE = "strip_boilerplate"
    FIX_JSON = "fix_json"
    STANDARDIZE_MD = "standardize_md"


# ---------------------------------------------------------------------------
# Boilerplate patterns (STRIP_BOILERPLATE)
# ---------------------------------------------------------------------------

_OPENING_PATTERNS = re.compile(
    r"^(here is|here are|certainly|i hope this|let me know if|i'd be happy|feel free to)\b",
    re.IGNORECASE,
)

_CLOSING_SENTENCES = [
    "let me know if you need anything else!",
    "let me know if you need anything else.",
    "let me know if you have any questions!",
    "let me know if you have any questions.",
    "is there anything else i can help with?",
    "is there anything else i can help you with?",
    "i hope this helps!",
    "i hope this helps.",
    "feel free to ask if you have questions.",
    "feel free to ask if you have questions!",
    "happy to help with anything else!",
    "happy to help with anything else.",
    "let me know if there's anything else.",
    "let me know if there's anything else!",
    "please let me know if you need further assistance.",
    "please let me know if you need further assistance!",
    "hope this helps!",
    "hope this helps.",
    "if you have any other questions,",
    "if you need further clarification,",
]


def _is_closing(sentence: str) -> bool:
    lower = sentence.strip().lower()
    for pattern in _CLOSING_SENTENCES:
        if lower.startswith(pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# JSON fix helpers (FIX_JSON)
# ---------------------------------------------------------------------------

_SINGLE_QUOTED_KEY_RE = re.compile(r"(^|\{|\,)\s*'([^']+)'\s*:")


def _extract_from_code_fence(content: str) -> str:
    """Extract JSON from a markdown ```json ... ``` fence, returning inner content."""
    start = content.find("```json")
    if start == -1:
        start = content.find("```JSON")
    if start == -1:
        return content
    inner_start = content.index("\n", start)
    end = content.rfind("```")
    if end == -1 or end <= inner_start:
        return content
    extracted = content[inner_start + 1 : end]
    return extracted.strip()


def _remove_trailing_commas(content: str) -> str:
    """Remove trailing commas before } or ]."""
    content = re.sub(r",\s*(\}|\])", r"\1", content)
    return content


def _balance_brackets(content: str) -> str:
    """Append missing closing brackets if unbalanced."""
    braces = content.count("{") - content.count("}")
    brackets = content.count("[") - content.count("]")
    if braces > 0:
        content += "}" * braces
    if brackets > 0:
        content += "]" * brackets
    return content


def _fix_single_quoted_keys(content: str) -> str:
    """Convert single-quoted JSON keys to double-quoted."""

    def _replacer(m: re.Match[str]) -> str:
        prefix = m.group(1)
        key = m.group(2)
        return f'{prefix}"{key}":'

    return _SINGLE_QUOTED_KEY_RE.sub(_replacer, content)


def _fix_truncation(content: str) -> str:
    """Remove '...' line continuations that indicate truncated content."""
    return re.sub(r"\.\.\.\s*\n?", "", content)


# ---------------------------------------------------------------------------
# Markdown normalize helpers (STANDARDIZE_MD)
# ---------------------------------------------------------------------------

_HEADING_NO_SPACE_RE = re.compile(r"^(#{1,6})([^#\s])", re.MULTILINE)
_FENCE_TAG_RE = re.compile(r"^(```)([A-Z]+)$", re.MULTILINE)


def _fix_heading_spaces(content: str) -> str:
    """Ensure headings have a space after # characters."""
    return _HEADING_NO_SPACE_RE.sub(r"\1 \2", content)


def _lowercase_fence_tags(content: str) -> str:
    """Lowercase code-fence language tags."""
    return _FENCE_TAG_RE.sub(lambda m: f"{m.group(1)}{m.group(2).lower()}", content)


def _normalize_blank_lines(content: str) -> str:
    """Reduce 3+ consecutive blank lines to 2 max."""
    return re.sub(r"\n{4,}", "\n\n\n", content)


def _ensure_blank_before_lists(content: str) -> str:
    """Insert a blank line before a list item when the preceding line is non-blank,
    non-list text."""
    lines = content.split("\n")
    result: list[str] = []
    for _i, line in enumerate(lines):
        stripped = line.lstrip()
        is_list = bool(stripped) and (
            stripped.startswith("- ") or stripped.startswith("* ")
        )
        if is_list and result and result[-1].strip() != "":
            prev_stripped = result[-1].lstrip()
            prev_is_list = prev_stripped.startswith("- ") or prev_stripped.startswith("* ")
            prev_is_heading = prev_stripped.startswith("#")
            if not prev_is_list and not prev_is_heading:
                result.append("")
        result.append(line)
    return "\n".join(result)


def _ensure_blank_before_after_fences(content: str) -> str:
    """Ensure blank line before and after code fences."""
    lines = content.split("\n")
    result: list[str] = []
    for _i, line in enumerate(lines):
        stripped = line.strip()
        is_fence = stripped.startswith("```")
        if is_fence and result and result[-1].strip() != "":
            result.append("")
        result.append(line)
        if is_fence:
            # After a fence opening, ensure next non-blank has blank line before
            pass
    return "\n".join(result)


def _ensure_blank_after_fences(content: str) -> str:
    """Ensure blank line after a closing code fence."""
    lines = content.split("\n")
    in_fence = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") and not in_fence:
            in_fence = True
        elif stripped.startswith("```") and in_fence:
            in_fence = False
            if i + 1 < len(lines) and lines[i + 1].strip() != "":
                lines.insert(i + 1, "")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ResponseNormalizer:
    @staticmethod
    def normalize(content: str, mode: NormalizeMode) -> str:
        if mode == NormalizeMode.NONE:
            return content

        if mode == NormalizeMode.STRIP_BOILERPLATE:
            return ResponseNormalizer._strip_boilerplate(content)

        if mode == NormalizeMode.FIX_JSON:
            return ResponseNormalizer._fix_json(content)

        if mode == NormalizeMode.STANDARDIZE_MD:
            return ResponseNormalizer._standardize_md(content)

        return content

    @staticmethod
    def _strip_boilerplate(content: str) -> str:
        # Split into sentences by treating each line-cluster ending in .?! as a sentence.
        # For the opening check, look at the first sentence only.
        # For the closing check, look at the last sentence only.
        paragraphs = content.split("\n")

        # Find first non-empty line
        first_idx = None
        last_idx = None
        for i, p in enumerate(paragraphs):
            if p.strip():
                if first_idx is None:
                    first_idx = i
                last_idx = i

        if first_idx is None:
            return content

        # Check and strip opening boilerplate
        if first_idx is not None:
            first_line = paragraphs[first_idx].strip()
            if _OPENING_PATTERNS.match(first_line):
                paragraphs[first_idx] = ""

        # Check and strip closing boilerplate
        if last_idx is not None and last_idx != first_idx:
            last_line = paragraphs[last_idx].strip()
            if _is_closing(last_line):
                paragraphs[last_idx] = ""

        result = "\n".join(paragraphs).strip()
        return result

    @staticmethod
    def _fix_json(content: str) -> str:
        result = content
        result = _extract_from_code_fence(result)
        result = _fix_single_quoted_keys(result)
        result = _remove_trailing_commas(result)
        result = _fix_truncation(result)
        result = _balance_brackets(result)
        return result

    @staticmethod
    def _standardize_md(content: str) -> str:
        result = content
        result = _fix_heading_spaces(result)
        result = _lowercase_fence_tags(result)
        result = _normalize_blank_lines(result)
        result = _ensure_blank_before_lists(result)
        result = _ensure_blank_before_after_fences(result)
        result = _ensure_blank_after_fences(result)
        return result
