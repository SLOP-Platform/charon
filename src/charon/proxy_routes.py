"""Upstream routing dataclass for the gateway proxy (seam F).

``UpstreamRoute`` is extracted verbatim from proxy_server.py: it captures
where one agent-facing model id is forwarded (multi-provider pools).
Kept in its own module so routing data definitions can evolve independently
of the HTTP serving shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .providers import WIRE_OPENAI


@dataclass(frozen=True)
class UpstreamRoute:
    """Where one agent-facing model id is forwarded (multi-provider pools)."""

    upstream_base: str
    api_key: str | None = None
    upstream_model: str | None = None  # rewrite the body's model to this id upstream
    pool_id: str | None = None  # observe under this id (the router's pool id) if set
    provider: str | None = None  # display label for failover visibility (X-Charon-Provider)
    strip_v1: bool | None = None  # per-provider quirk; None → use the server default
    wire: str = WIRE_OPENAI  # upstream wire format (SR-6): WIRE_OPENAI | WIRE_ANTHROPIC
    adapter: str | None = None  # response-shape adapter key (response_adapters.py);
    model_id: str | None = None  # registry model id (for live meter lookup in R2)
    #                             None → IDENTITY passthrough (byte-identical relay)
    # R7 capability-engine: per-route hard limits (None = unknown / no limit)
    max_context: int | None = None       # max tokens this route admits
    max_concurrency: int | None = None   # max in-flight requests to this route

    @property
    def label(self) -> str:
        """Human-facing provider id for failover headers/logs — never a secret. Uses
        host[:port] (NOT netloc) so any ``user:pass@`` userinfo in a misconfigured
        base never surfaces in a header/console (P4 review)."""
        if self.provider:
            return self.provider
        parts = urlsplit(self.upstream_base)
        host = parts.hostname or self.upstream_base
        return f"{host}:{parts.port}" if parts.port else host
