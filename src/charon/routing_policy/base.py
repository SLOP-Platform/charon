from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from charon.proxy_server import UpstreamRoute


class Policy(abc.ABC):
    """Routing-policy base: one decision per request.

    Subclasses MUST override :meth:`select` — this is the extension point for
    Wave-2 policy implementations (cost-rank, drain, pools, spill, etc.).
    """

    name: str = ""

    @abc.abstractmethod
    def select(
        self,
        *,
        model_id: str,
        work_class: str | None = None,
        routes: dict[str, UpstreamRoute] | None = None,
        pools: dict[str, list[UpstreamRoute]] | None = None,
    ) -> list[UpstreamRoute]:
        """Return an ordered list of candidate routes for *model_id*.

        The returned list may be empty (policy not applicable) or contain one or
        more :class:`UpstreamRoute` candidates. The gateway walks the list in
        order, with its built-in failover providing transparent retries.
        """
        ...


class DefaultPolicy(Policy):
    """Passthrough policy: returns the single route for *model_id* verbatim.

    This is the backward-compatible default — routes and pools are resolved
    exactly as they were before the policy engine existed. Policy-aware code
    can replace this with a registry lookup later.
    """

    name = "default"

    def select(
        self,
        *,
        model_id: str,
        work_class: str | None = None,
        routes: dict[str, UpstreamRoute] | None = None,
        pools: dict[str, list[UpstreamRoute]] | None = None,
    ) -> list[UpstreamRoute]:
        routes = routes or {}
        pools = pools or {}
        if model_id in pools:
            return list(pools[model_id])
        if model_id in routes:
            return [routes[model_id]]
        return []
