"""Adopted commodity plane for the gateway (ADR-0017): ``litellm.Router`` as a LIBRARY.

A cohesive subpackage for the adopted commodity plane (the same shape as ``service/`` for
fastapi/uvicorn): the third-party ``litellm`` import and its Charon config→Router mapping live
here, behind the opt-in path, so the live money-path stays untouched. ``litellm`` is imported
LAZILY inside the functions that use it, so importing this package never requires litellm to
be installed.

See ``ADOPT-MAP.md`` at the repo root for the current-behavior → litellm mapping, the slice
boundary (delivered vs deferred), and the egress.py reconciliation.
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