"""The web entrypoint's bind guard (ADR-0004 D7): a non-loopback bind must be
refused unless CHARON_SERVICE_TOKEN is set. Pure stdlib — runs in the core gate
(the uvicorn import happens only after the guard, on the success path)."""
from __future__ import annotations

from charon.service.__main__ import _is_loopback, main


def test_loopback_classification() -> None:
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("::1")
    assert _is_loopback("localhost")
    # all-interfaces binds are EXPOSED, not loopback (the set-but-empty hole)
    assert not _is_loopback("")
    assert not _is_loopback("0.0.0.0")
    assert not _is_loopback("::")
    assert not _is_loopback("203.0.113.10")
    assert not _is_loopback("example.com")


def test_non_loopback_without_token_is_refused(monkeypatch) -> None:
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("CHARON_SERVICE_HOST", "0.0.0.0")
    assert main() == 2  # refused before ever importing/binding uvicorn


def test_empty_host_without_token_is_refused(monkeypatch) -> None:
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("CHARON_SERVICE_HOST", "")  # binds all interfaces
    assert main() == 2
