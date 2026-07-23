"""Verify-only litellm cost cross-check for the Router path (GW-BRIDGE-2).

ADR-0020 ACCEPTED verify-only: the litellm cost callback runs ALONGSIDE Charon's
authoritative accounting as a cross-check, NOT as the money source of record.

Charon's own cost computation REMAINS the source of record advancing
BalanceTracker + drain-then-park.  This module's ONLY job is to surface
divergence — it must NEVER override, correct, freeze, or reorder Charon's
authoritative spend / drain-then-park.

Non-token / energy metering is untouched — Charon's rule stays authoritative.
"""
from __future__ import annotations

import logging
from typing import Any

from charon.proxy import GatewayProxy

# USD tolerance — costs below this delta are treated as equal.
_COST_TOLERANCE = 0.001


def litellm_cost(response: Any) -> float:
    """Extract the cost litellm computed from a ModelResponse or dict response."""
    usage = getattr(response, "usage", None)
    if usage is not None:
        return float(getattr(usage, "cost", 0.0) or 0.0)
    if isinstance(response, dict):
        u = response.get("usage")
        if isinstance(u, dict):
            return float(u.get("cost", u.get("total_cost", 0.0)) or 0.0)
    return 0.0


def charon_cost(observation: Any) -> float:
    """Extract Charon's authoritative cost from a ProxyObservation."""
    if observation is None:
        return 0.0
    usage = getattr(observation, "usage", None)
    if usage is None:
        return 0.0
    return float(getattr(usage, "cost_usd", 0.0) or 0.0)


def check_divergence(
    litellm_usd: float,
    charon_usd: float,
    *,
    model: str = "",
    provider: str = "",
) -> float:
    """Compare litellm callback cost vs Charon authoritative cost.

    Pure observation — does NOT modify BalanceTracker or any money-path state.
    Returns the absolute delta.  Logs a WARNING when delta > tolerance.

    The caller chooses what costs to compare — this function has no side
    effects beyond logging.
    """
    delta = abs(litellm_usd - charon_usd)
    if delta > _COST_TOLERANCE:
        logging.warning(
            "COST DIVERGENCE: litellm=%.6f charon=%.6f delta=%.6f "
            "model=%s provider=%s",
            litellm_usd,
            charon_usd,
            delta,
            model or "-",
            provider or "-",
        )
    return delta


def crosscheck_observation(
    raw_response: Any,
    observation: Any,
    *,
    model: str = "",
    provider: str = "",
) -> float:
    """Given a litellm raw response and a Charon ProxyObservation, compare costs.

    A convenience wrapper around :func:`litellm_cost` + :func:`charon_cost` +
    :func:`check_divergence`.  Returns the absolute delta.  Never touches
    BalanceTracker.
    """
    lc = litellm_cost(raw_response)
    cc = charon_cost(observation)
    return check_divergence(lc, cc, model=model, provider=provider)


def crosscheck_response_dict(
    response_dict: dict,
    observation: Any,
    *,
    model: str = "",
    provider: str = "",
) -> float:
    """Given a response dict (e.g. from :func:`~charon.litellm_plane.litellm_router._to_dict`)
    and a Charon ProxyObservation, compare costs — useful when the raw
    litellm ModelResponse is not available.

    Returns the absolute delta.  Never touches BalanceTracker.
    """
    lc = litellm_cost(response_dict)
    cc = charon_cost(observation)
    return check_divergence(lc, cc, model=model, provider=provider)


def classify_and_crosscheck(
    router: Any,
    body: dict,
    *,
    timeout: float = 180.0,
    observer: GatewayProxy | None = None,
    provider_label: str = "",
) -> tuple[Any, dict, Any, float]:
    """Issue a Router completion, classify it, and cross-check costs.

    This is the main integration point for the verify-only cross-check.
    It:
      1. Issues ``router.completion(...)`` (one upstream call).
      2. Converts the response to a plain dict.
      3. Classifies it via ``GatewayProxy.classify`` (Charon's authoritative
         cost computation).
      4. Compares litellm's cost against Charon's cost.
      5. Returns ``(raw_response, response_dict, observation, delta)``.

    Pure observation — does NOT call ``record_spend``, ``record``, or any
    BalanceTracker mutation.  No money-path state is changed.
    """
    model = (body or {}).get("model", "")
    messages = body.get("messages") or []
    passthrough = {
        k: body[k]
        for k in ("temperature", "top_p", "max_tokens", "tools", "tool_choice",
                  "stop", "response_format")
        if k in body
    }
    raw = router.completion(
        model=model, messages=messages, timeout=timeout, **passthrough,
    )

    served = raw
    for attr in ("model_dump", "dict"):
        fn = getattr(served, attr, None)
        if callable(fn):
            served = fn()
            break
    else:
        served = dict(raw)

    obs = (observer or GatewayProxy()).classify(
        requested_model=model,
        status=200,
        headers=None,
        body=served,
    )

    delta = crosscheck_observation(
        raw, obs, model=model, provider=provider_label,
    )
    return raw, served, obs, delta
