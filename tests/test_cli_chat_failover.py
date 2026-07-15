from __future__ import annotations

from unittest.mock import patch

from charon.cli import _probe_keys


class _Preset:
    def __init__(self, base_url: str = "https://api.example.com/v1"):
        self.base_url = base_url


class TestProbeKeysFailover:
    """_probe_keys must fail over across candidates (DESTIFF-CLI-CHAT)."""

    def test_first_401_second_succeeds(self) -> None:
        """When the first candidate 401s and the second responds, failover
        picks the second — the function returns None (success)."""
        call_count: list[int] = []

        def _fake_probe(base_url: str, api_key: str) -> str | None:
            call_count.append(len(call_count))
            if len(call_count) == 1:
                return "key rejected (HTTP 401)"
            return None

        candidates = [
            (_Preset("https://first.example.com/v1"), "key-a"),
            (_Preset("https://second.example.com/v1"), "key-b"),
        ]

        with patch("charon.cli._do_probe", _fake_probe):
            result = _probe_keys(candidates)

        assert result is None, f"expected None (success), got {result!r}"
        assert len(call_count) == 2

    def test_all_fail_exhaustion(self) -> None:
        """When every candidate fails, the result contains 'pool exhausted'."""
        def _always_fail(base_url: str, api_key: str) -> str | None:
            return "key rejected (HTTP 401)"

        candidates = [
            (_Preset("https://first.example.com/v1"), "key-a"),
            (_Preset("https://second.example.com/v1"), "key-b"),
        ]

        with patch("charon.cli._do_probe", _always_fail):
            result = _probe_keys(candidates)

        assert result is not None
        assert "pool exhausted" in result

    def test_empty_candidates_returns_none(self) -> None:
        """An empty candidate list returns None (nothing to probe)."""
        assert _probe_keys([]) is None

    def test_scheme_validation_skips_bad_url_then_fails_over(self) -> None:
        """A candidate with a non-http(s) base_url is skipped (failover)."""
        call_count: list[int] = []

        def _fake_probe(base_url: str, api_key: str) -> str | None:
            call_count.append(len(call_count))
            return None

        candidates = [
            (_Preset("ftp://bad.example.com"), "key-bad"),
            (_Preset("https://good.example.com/v1"), "key-good"),
        ]

        with patch("charon.cli._do_probe", _fake_probe):
            result = _probe_keys(candidates)

        assert result is None
        assert len(call_count) == 1

    def test_first_succeeds_no_second_call(self) -> None:
        """When the first candidate succeeds, the second is never called."""
        call_count: list[int] = []

        def _fake_probe(base_url: str, api_key: str) -> str | None:
            call_count.append(len(call_count))
            return None

        candidates = [
            (_Preset("https://first.example.com/v1"), "key-a"),
            (_Preset("https://second.example.com/v1"), "key-b"),
        ]

        with patch("charon.cli._do_probe", _fake_probe):
            result = _probe_keys(candidates)

        assert result is None
        assert len(call_count) == 1
