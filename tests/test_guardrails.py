"""Tests for the Guardrails module."""
from __future__ import annotations

from charon.guardrails import (
    Guardrails,
    _extract_text_from_messages,
    _luhn_check,
)
from charon.types import GuardrailViolation


def test_luhn_valid():
    assert _luhn_check("4111111111111111") is True


def test_luhn_invalid():
    assert _luhn_check("1234567890123456") is False


def test_luhn_short():
    assert _luhn_check("4111") is False


def test_detects_email_pii():
    g = Guardrails()
    violations, _ = g.scan_request(
        [{"role": "user", "content": "Contact user@example.com for help"}]
    )
    assert violations == [
        GuardrailViolation(
            severity="WARN",
            pattern="email",
            location="body",
            message="Detected email pattern",
        )
    ]


def test_detects_ssn_pii():
    g = Guardrails()
    violations, _ = g.scan_request(
        [{"role": "user", "content": "My SSN is 123-45-6789"}]
    )
    assert violations == [
        GuardrailViolation(
            severity="WARN",
            pattern="ssn",
            location="body",
            message="Detected ssn pattern",
        )
    ]


def test_detects_credit_card_luhn_valid():
    g = Guardrails()
    violations, _ = g.scan_request(
        [{"role": "user", "content": "Card: 4111 1111 1111 1111"}]
    )
    assert any(v.pattern == "credit_card" for v in violations)


def test_rejects_fake_credit_card():
    g = Guardrails()
    violations, _ = g.scan_request(
        [{"role": "user", "content": "Card: 1234 5678 9012 3456"}]
    )
    assert not any(v.pattern == "credit_card" for v in violations)


def test_detects_phone_pii():
    g = Guardrails()
    violations, _ = g.scan_request(
        [{"role": "user", "content": "Call 555-123-4567"}]
    )
    assert any(v.pattern == "phone" for v in violations)


def test_detects_api_key():
    g = Guardrails()
    violations, _ = g.scan_request(
        [
            {
                "role": "user",
                "content": "Use key: sk-abcdef1234567890abcdef1234567890ab",
            }
        ]
    )
    assert any(v.pattern == "api_key" for v in violations)


def test_keyword_blocking():
    g = Guardrails({"keywords": ["badword1"]})
    violations, _ = g.scan_request(
        [{"role": "user", "content": "This contains badword1 in the text"}]
    )
    assert len(violations) >= 1
    assert violations[0].severity == "BLOCK"
    assert violations[0].pattern == "badword1"


def test_keyword_case_insensitive():
    g = Guardrails({"keywords": ["badword1"]})
    violations, _ = g.scan_request(
        [{"role": "user", "content": "This contains BADWORD1 in the text"}]
    )
    assert len(violations) >= 1
    assert violations[0].severity == "BLOCK"


def test_no_violations_clean_text():
    g = Guardrails()
    violations, _ = g.scan_request(
        [{"role": "user", "content": "Hello! How can I help you today?"}]
    )
    assert violations == []


def test_scan_request_extracts_text_from_messages():
    g = Guardrails()
    violations, _ = g.scan_request(
        [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "My email is test@example.com"},
        ]
    )
    assert any(v.pattern == "email" for v in violations)


def test_scan_request_extracts_multipart_content():
    g = Guardrails()
    violations, _ = g.scan_request(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Plain text without PII"},
                    {"type": "text", "text": "Then here is a SSN 987-65-4321"},
                ],
            }
        ]
    )
    assert any(v.pattern == "ssn" for v in violations)


def test_scan_response_pii_detection():
    g = Guardrails()
    violations = g.scan_response(
        "The response mentions user@example.com in the output"
    )
    assert len(violations) == 1
    assert violations[0].pattern == "email"


def test_hide_secrets_redacts():
    g = Guardrails({"hide_secrets": True})
    violations, cleaned = g.scan_request(
        [
            {
                "role": "user",
                "content": "Key: sk-abcdef1234567890abcdef1234567890ab",
            }
        ]
    )
    assert any(v.pattern == "api_key" for v in violations)
    assert cleaned is not None
    assert "sk-" not in cleaned
    assert "***" in cleaned


def test_hide_secrets_false_returns_none():
    g = Guardrails({"hide_secrets": False})
    violations, cleaned = g.scan_request(
        [
            {
                "role": "user",
                "content": "Key: sk-abcdef1234567890abcdef1234567890ab",
            }
        ]
    )
    assert cleaned is None


def test_severity_pii_is_warn():
    g = Guardrails()
    violations, _ = g.scan_request(
        [{"role": "user", "content": "test@example.com"}]
    )
    assert all(v.severity == "WARN" for v in violations)


def test_severity_keyword_is_block():
    g = Guardrails({"keywords": ["forbidden"]})
    violations, _ = g.scan_request(
        [{"role": "user", "content": "Say the word forbidden now"}]
    )
    assert any(v.severity == "BLOCK" for v in violations)


def test_extract_text_from_messages_string_content():
    text = _extract_text_from_messages(
        [
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there"},
        ]
    )
    assert "Hello world" in text
    assert "Hi there" in text


def test_extract_text_from_messages_missing_content():
    text = _extract_text_from_messages(
        [{"role": "user"}, {"role": "assistant", "content": "Hi"}]
    )
    assert text == "Hi"


def test_extract_text_from_messages_list_content():
    text = _extract_text_from_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Part one"},
                    {"type": "image_url", "image_url": {"url": "http://..."}},
                    {"type": "text", "text": "Part two"},
                ],
            }
        ]
    )
    assert "Part one" in text
    assert "Part two" in text


def test_disable_pii_skips_detection():
    g = Guardrails({"disable_pii": True})
    violations, _ = g.scan_request(
        [{"role": "user", "content": "test@example.com 123-45-6789"}]
    )
    assert violations == []
