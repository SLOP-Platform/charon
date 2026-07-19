"""SPIKE adapter: make ``litellm.Router`` satisfy Charon's per-attempt contract.

THROWAWAY — not for adoption. Proves the survey's escape-hatch claim: that
``litellm.Router`` can sit UNDER Charon's existing policy layer as the mechanical
substrate for ONE provider attempt, while Charon keeps deciding order.

The contract Charon's ``forwarder.forward_with_failover`` loop consumes for a
single attempt (forwarder.py:559-573) is:

    given an UpstreamRoute + the request body,
      -> perform the OpenAI-compatible call,
      -> return (status:int, headers:dict, body:dict) in OpenAI shape,
      -> which srv.observer.classify(okey, status, headers, body, expected_model)
         turns into a ProxyObservation (usage.cost_usd, pseudo_success, exhausted...).

Today the substrate for that attempt is ``_build_upstream_req`` +
``urllib.request.urlopen`` + retry-once (forwarder.py:181-235, 563-651). This
adapter is a drop-in replacement for exactly that slice: litellm.Router does the
HTTP call, cost capture, and (optionally) retry/cooldown. Everything Charon's
policy layer needs — classify, quality_scorer, order_* — runs unchanged on the
dict this returns, because the dict is byte-shaped like any OpenAI response.
"""
from __future__ import annotations

from typing import Any

from litellm import Router


def _deployment_for_route(route: Any) -> dict:
    """One Charon UpstreamRoute -> one litellm.Router deployment.

    Charon has ALREADY chosen this provider (its funding-class / live-cost /
    quality ordering ran upstream). So the Router is given exactly ONE
    deployment: litellm is the mechanical caller for this single attempt, NOT
    the failover brain. num_retries=0 keeps Charon's outer failover loop
    authoritative — litellm must not silently retry a sibling Charon hasn't
    picked. ``openai/`` prefix = "speak OpenAI wire to this api_base"; api_base
    and api_key come straight off the route (same fields _build_upstream_req
    reads at forwarder.py:217/234).
    """
    upstream_model = route.upstream_model or route.model_id or "gpt-4o-mini"
    return {
        "model_name": route.label,
        "litellm_params": {
            "model": f"openai/{upstream_model}",
            "api_base": route.upstream_base,
            "api_key": route.api_key or "sk-none",
            "num_retries": 0,
        },
    }


def attempt(route: Any, messages: list[dict], requested_model: str,
            *, extra_body: dict | None = None) -> tuple[int, dict, dict]:
    """Run ONE provider attempt through litellm.Router; return Charon's
    ``(status, headers, body)`` contract for ``observer.classify``.

    On success: a real OpenAI-shaped dict carrying ``model`` (so classify can
    detect a silent downgrade) and ``usage`` with ``prompt_tokens`` /
    ``completion_tokens`` / ``cost`` (litellm's computed response_cost, mapped
    onto the ``cost`` key ``_gateway_usage`` reads at proxy.py:139). On failure:
    the litellm exception's status_code + an OpenAI-shaped error body, exactly
    what classify expects to see for a 429/402/503 so Charon's loop fails over.
    """
    router = Router(model_list=[_deployment_for_route(route)],
                    num_retries=0)
    try:
        resp = router.completion(
            model=route.label, messages=messages, **(extra_body or {}))
    except Exception as exc:  # noqa: BLE001 — map ANY litellm error to a status
        status = int(getattr(exc, "status_code", 0) or 502)
        headers = {}
        ra = getattr(exc, "retry_after", None)
        if ra is not None:
            headers["Retry-After"] = str(int(ra))
        # OpenAI-shaped error body so Charon's classify pattern-matches it
        # (exhausted / auth / unsupported) exactly as for a real upstream error.
        body = {"error": {"message": str(getattr(exc, "message", exc)),
                          "type": type(exc).__name__}}
        return status, headers, body

    body = resp.model_dump()  # OpenAI-shaped dict (choices/model/usage)
    # litellm carries the computed cost out-of-band; fold it onto the OpenAI
    # ``usage.cost`` key that Charon's _gateway_usage already reads. This is the
    # ONE translation the adapter does — everything else is native OpenAI shape.
    cost = (getattr(resp, "_hidden_params", {}) or {}).get("response_cost")
    if cost is not None and isinstance(body.get("usage"), dict):
        body["usage"]["cost"] = float(cost)
    return 200, {}, body
