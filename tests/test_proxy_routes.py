"""UpstreamRoute importability — direct import from proxy_routes.

Proves the extracted routes module (seam F) is independently importable
and its dataclass constructs correctly when called directly.
"""
from __future__ import annotations

from charon.proxy_routes import UpstreamRoute


def test_upstream_route_construct_and_label() -> None:
    """UpstreamRoute constructs directly from proxy_routes and label is safe."""
    r = UpstreamRoute("https://api.example.com/v1", api_key="sk-test",
                       provider="Example")
    assert r.label == "Example"
    assert r.upstream_base == "https://api.example.com/v1"


def test_upstream_route_label_no_provider() -> None:
    """When provider is None, label falls back to host:port from the base URL."""
    r = UpstreamRoute("https://api.example.com:8443/v1")
    assert r.label == "api.example.com:8443"
