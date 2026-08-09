"""Adopted commodity plane for the gateway (ADR-0017): litellm.Router as a LIBRARY.
"""
from __future__ import annotations

from .litellm_router import (
    ATTEMPTS_META_KEY,
    DEFAULT_ALLOWED_FAILS,
    DEFAULT_NUM_RETRIES,
    DOWNGRADE_HEADER,
    AdoptError,
    AttemptRecord,
    GuardedResponse,
    build_fallbacks,
    build_model_list,
    complete_via_router,
    complete_via_router_guarded,
    complete_via_router_tracked,
    make_router,
    no_redirect_client,
    resolve_route_key,
    routes_by_model,
)

__all__ = [
    "AdoptError",
    "ATTEMPTS_META_KEY",
    "AttemptRecord",
    "DEFAULT_ALLOWED_FAILS",
    "DEFAULT_NUM_RETRIES",
    "DOWNGRADE_HEADER",
    "GuardedResponse",
    "build_fallbacks",
    "build_model_list",
    "complete_via_router",
    "complete_via_router_guarded",
    "complete_via_router_tracked",
    "make_router",
    "no_redirect_client",
    "resolve_route_key",
    "routes_by_model",
]
