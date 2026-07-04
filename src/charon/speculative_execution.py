"""Speculative execution — race N providers, return fastest, cancel rest.

Opt-in per request via X-Charon-Speculative: true header.
Uses stdlib ThreadPoolExecutor to dispatch to N providers concurrently.
First 200 response wins; remaining threads are cancelled.
If all fail, falls back to sequential failover.
Reuses existing UpstreamRoute + GatewayProxyServer infrastructure.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SpecResult:
    provider: str = ""
    status: int = 0
    body: bytes = b""
    headers: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None


class SpeculativeExecutor:
    def __init__(self, max_providers: int = 3, timeout_ms: float = 30000.0,
                 enabled: bool = False):
        self.max_providers = max_providers
        self.timeout_s = timeout_ms / 1000.0
        self.enabled = enabled

    def _call_upstream(self, route: object, req: urllib.request.Request) -> SpecResult:
        start = time.monotonic()
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout_s)
            body = resp.read()
            result = SpecResult(
                provider=getattr(route, "label", "unknown"),
                status=resp.status,
                body=body,
                headers=dict(resp.headers),
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read()
            result = SpecResult(
                provider=getattr(route, "label", "unknown"),
                status=exc.code,
                body=body,
                headers=dict(exc.headers),
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as exc:
            logger.exception("speculative upstream call failed")
            result = SpecResult(
                provider=getattr(route, "label", "unknown"),
                error=str(exc),
                latency_ms=(time.monotonic() - start) * 1000,
            )
        return result

    def execute(self, routes: list[object],
                body: bytes, content_type: str = "application/json") -> SpecResult | None:
        if not self.enabled or not routes:
            return None
        providers = routes[:self.max_providers]
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures: dict[concurrent.futures.Future, object] = {}
            for route in providers:
                req = self._build_request(route, body, content_type)
                futures[pool.submit(self._call_upstream, route, req)] = route
            try:
                for future in concurrent.futures.as_completed(futures, timeout=self.timeout_s):
                    result = future.result()
                    if result.status == 200 and not result.error:
                        for f in futures:
                            f.cancel()
                        return result
            except concurrent.futures.TimeoutError:
                pass
            for f in futures:
                f.cancel()
        return None

    def _build_request(self, route: object, body: bytes,
                       content_type: str) -> urllib.request.Request:
        base = getattr(route, "upstream_base", "")
        model = getattr(route, "upstream_model", None)
        api_key = getattr(route, "api_key", None)
        strip = getattr(route, "strip_v1", True)
        url = base.rstrip("/")
        if strip:
            if not url.endswith("/v1"):
                url += "/v1"
        else:
            if not url.endswith("/v1/chat/completions"):
                url += "/v1/chat/completions" if "/chat" not in url else ""
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        data = body
        if model:
            try:
                parsed = json.loads(body)
                parsed["model"] = model
                data = json.dumps(parsed).encode()
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", content_type)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        return req
