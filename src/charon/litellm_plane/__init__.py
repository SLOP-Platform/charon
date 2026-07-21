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
    DEFAULT_ALLOWED_FAILS,
    DEFAULT_NUM_RETRIES,
    AdoptError,
    build_model_list,
    complete_via_router,
    make_router,
    no_redirect_client,
    resolve_route_key,
    routes_by_model,
)

__all__ = [
    "AdoptError",
    "DEFAULT_ALLOWED_FAILS",
    "DEFAULT_NUM_RETRIES",
    "build_model_list",
    "complete_via_router",
    "make_router",
    "no_redirect_client",
    "resolve_route_key",
    "routes_by_model",
]
