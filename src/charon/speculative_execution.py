"""Speculative execution — race N providers, return fastest, cancel rest.

Opt-in per request via X-Charon-Speculative: true header.
Uses stdlib ThreadPoolExecutor to dispatch to N providers concurrently.
First 200 response wins; remaining threads are cancelled.
If all fail, falls back to sequential failover.
Reuses existing UpstreamRoute + GatewayProxyServer infrastructure.

Cross-provider failover (operator directive 2026-07-15, "no stiff single-provider
tools"): the per-provider upstream call is classified via the shared
``failover_loop`` vocabulary (OK / RETRY / FAILOVER), and a race where every
provider returns a provider-level fault (401/403/429/5xx / transport) is
routed through ``invoke_with_failover`` so the exhaustion message names every
candidate's failure and ends with an actionable recommendation — same contract
as the planner's adoption of the primitive, but composed: the race still picks
the first 200 (first-good-wins) and never issues the same request twice.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .failover_loop import (
    FAILOVER,
    OK,
    AttemptResult,
    invoke_with_failover,
)
from .netutil import BROWSER_UA

logger = logging.getLogger(__name__)


@dataclass
class SpecResult:
    provider: str = ""
    status: int = 0
    body: bytes = b""
    headers: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None


# HTTP statuses treated as a *provider-level* fault (auth / limit / infra) — the
# candidate cannot serve THIS request; the race's failover picks the next.
_PROVIDER_FAULT_STATUSES = frozenset({401, 403, 408, 425, 429, 500, 502, 503, 504})


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

    @staticmethod
    def _classify(result: SpecResult) -> tuple[str, str, str]:
        """Map a single upstream ``SpecResult`` to the failover_loop vocabulary.

        Returns ``(kind, feedback, attribution)``:

        * ``OK`` — a 200 (or any non-provider-fault upstream response, e.g. an
          upstream-issued 400). The race can return this immediately.
        * ``RETRY`` — reserved (no current caller has quality-level feedback
          to thread into a same-provider re-issue; speculative execution is
          fire-and-forget, so a re-issued POST would double the side-effects).
          Kept as a value for vocabulary completeness.
        * ``FAILOVER`` — a provider-level fault (auth/limit/infra/transport).
          The race's failover picks the next candidate.
        """
        if result.error and not result.status:
            return FAILOVER, "", f"transport: {result.error}"
        if result.status in _PROVIDER_FAULT_STATUSES:
            note = "auth (HTTP 401): dead key" if result.status == 401 else \
                "limit (HTTP 429): rate-limited" if result.status == 429 else \
                f"infra (HTTP {result.status})"
            return FAILOVER, "", note
        if result.status == 200:
            return OK, "", f"200 ok in {result.latency_ms:.1f}ms"
        # Any other non-empty response is a valid upstream verdict — return it
        # verbatim; do not double-issue (RETRY would POST again) or skip it
        # (FAILOVER would lose a 4xx the caller can act on).
        return OK, "", f"upstream HTTP {result.status}"

    def execute(self, routes: list[object],
                body: bytes, content_type: str = "application/json") -> SpecResult | None:
        if not self.enabled or not routes:
            return None
        providers = routes[:self.max_providers]
        completed: list[SpecResult] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures: dict[concurrent.futures.Future, object] = {}
            for route in providers:
                req = self._build_request(route, body, content_type)
                futures[pool.submit(self._call_upstream, route, req)] = route
            try:
                for future in concurrent.futures.as_completed(futures, timeout=self.timeout_s):
                    result = future.result()
                    completed.append(result)
                    kind, _, _ = self._classify(result)
                    if kind == OK:
                        for f in futures:
                            f.cancel()
                        return result
            except concurrent.futures.TimeoutError:
                pass
            for f in futures:
                f.cancel()

        # Race produced at least one OK already handled above. If the timeout
        # fired, drain whatever did complete (best effort) and continue.
        if not completed:
            return None

        # First-good-wins held for every OK. If at least one OK landed but the
        # race returned it, we'd have early-returned; the residual case is
        # "all completions were provider-level faults" (FAILOVER), or "OK
        # landed but a later OK won" — the former is what the ticket's
        # all-fail branch tests.
        ok_results = [r for r in completed if self._classify(r)[0] == OK]
        if ok_results:
            return ok_results[0]

        # Every completion was a provider-level fault. Run the ordered
        # candidate list through ``invoke_with_failover`` so the exhaustion
        # message names every candidate's failure and ends with an actionable
        # recommendation — same contract the planner uses. ``attempt`` returns
        # the already-collected, already-classified result; nothing is
        # re-issued, so the speculation never double-issues.
        def _attempt(route: object, _feedback: str) -> AttemptResult[SpecResult]:
            for r in completed:
                if getattr(route, "label", "unknown") == r.provider:
                    kind, feedback, attribution = self._classify(r)
                    if kind == OK:
                        return AttemptResult(kind=OK, value=r, attribution=attribution)
                    return AttemptResult(
                        kind=FAILOVER, attribution=attribution, feedback=feedback,
                    )
            return AttemptResult(
                kind=FAILOVER, attribution="no result collected (timed out)",
            )

        return invoke_with_failover(
            providers,
            _attempt,
            max_retries=0,
            describe=lambda r: getattr(r, "label", "unknown"),
            recommendation=(
                "speculative race exhausted — every provider returned a "
                "provider-level fault (auth/limit/infra); check keys, "
                "balances, and provider health"
            ),
            error=RuntimeError,
        )

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
        req.add_header("User-Agent", BROWSER_UA)  # P5: avoid CF-1010 on provider POST
        req.add_header("Content-Type", content_type)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        return req
