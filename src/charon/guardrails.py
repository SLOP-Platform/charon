"""Configurable guardrail scanner for PII and keyword deny-lists.

Operates on chat-message lists (requests) and plain-text strings (responses).
All checks are stdlib-only — no network, no external deps.
"""
from __future__ import annotations

import re
from typing import Any

from charon.types import GuardrailViolation

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_RE = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")
_API_KEY_RE = re.compile(
    r"\b(sk-[A-Za-z0-9]{32,}|api_key\s*=\s*['\"][^'\"]+['\"])"
)
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

_PII_CHECKS: list[tuple[str, re.Pattern[str]]] = [
    ("email", _EMAIL_RE),
    ("ssn", _SSN_RE),
    ("phone", _PHONE_RE),
    ("api_key", _API_KEY_RE),
]


def _luhn_check(s: str) -> bool:
    digits = [int(ch) for ch in s if ch.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _extract_text_from_messages(messages: list[dict]) -> str:
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content")
        if content is None:
            continue
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
    return " ".join(parts)


class Guardrails:
    def __init__(self, config: dict | None = None) -> None:
        cfg: dict[str, Any] = config or {}
        self._keywords: list[str] = list(cfg.get("keywords", []))
        self._hide_secrets: bool = bool(cfg.get("hide_secrets", False))
        self._pii_enabled: bool = not cfg.get("disable_pii", False)

    def _scan_text(self, text: str) -> tuple[list[GuardrailViolation], str]:
        violations: list[GuardrailViolation] = []

        if self._pii_enabled:
            for pattern_name, regex in _PII_CHECKS:
                for _ in regex.finditer(text):
                    violations.append(
                        GuardrailViolation(
                            severity="WARN",
                            pattern=pattern_name,
                            location="body",
                            message=f"Detected {pattern_name} pattern",
                        )
                    )

            for m in _CC_RE.finditer(text):
                candidate = m.group()
                if _luhn_check(candidate):
                    violations.append(
                        GuardrailViolation(
                            severity="WARN",
                            pattern="credit_card",
                            location="body",
                            message="Detected credit_card pattern",
                        )
                    )

        for kw in self._keywords:
            if re.search(re.escape(kw), text, re.IGNORECASE):
                violations.append(
                    GuardrailViolation(
                        severity="BLOCK",
                        pattern=kw,
                        location="body",
                        message=f"Blocked keyword: {kw}",
                    )
                )

        cleaned = text
        if self._hide_secrets:
            cleaned = _API_KEY_RE.sub("***", cleaned)

        return violations, cleaned

    def scan_request(
        self, messages: list[dict]
    ) -> tuple[list[GuardrailViolation], str | None]:
        text = _extract_text_from_messages(messages)
        violations, cleaned = self._scan_text(text)
        return violations, cleaned if self._hide_secrets else None

    def scan_response(self, content: str) -> list[GuardrailViolation]:
        violations, _ = self._scan_text(content)
        return violations
