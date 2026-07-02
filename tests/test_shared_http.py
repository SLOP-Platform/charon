"""Smoke tests for the shared HTTP test fixtures in conftest.py."""

from __future__ import annotations


def test_mock_upstream_responds_to_post(mock_upstream, _post):
    url, srv, captured = mock_upstream
    status, resp = _post(url, {
        "model": "test-model",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert status == 200
    assert resp["model"] == "test-model"
    assert resp["choices"][0]["message"]["content"] == "hello"


def test_mock_upstream_captures_request_metadata(mock_upstream, _post):
    url, srv, captured = mock_upstream
    _post(url, {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert captured["model"] == "gpt-4"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]


def test_mock_upstream_isolation(mock_upstream, _post):
    """Each test function gets a fresh server on its own port."""
    url, srv, _ = mock_upstream
    host, port = srv.server_address[:2]
    assert port > 0
    assert "http://" in url
    status, _resp = _post(url, {
        "model": "x",
        "messages": [{"role": "user", "content": "y"}],
    })
    assert status == 200
