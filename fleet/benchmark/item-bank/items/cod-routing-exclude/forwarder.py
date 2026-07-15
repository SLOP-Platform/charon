"""forwarder.py — minimal failover loop the model must edit."""

from chain_types import (
    MODEL_META,
    NoRouteError,
    RequestInspector,
    UpstreamRoute,
)


def chain_for(requested: str) -> list[UpstreamRoute]:
    """Stub: pretend we have a deterministic failover chain for any model id."""
    pool = {
        "gpt": [UpstreamRoute("gpt-vision", "openai"), UpstreamRoute("gpt-text", "azure")],
        "claude": [UpstreamRoute("claude-opus", "anthropic"), UpstreamRoute("claude-haiku", "anthropic")],
        "llama": [UpstreamRoute("llama-3", "together")],
    }
    for k, v in pool.items():
        if k in requested:
            return v
    raise NoRouteError(f"no chain for {requested!r}")


def _soft_exclude_for_reasoning(chain: list[UpstreamRoute]) -> list[UpstreamRoute]:
    """Pre-existing softer reasoning-capability exclusion. The model must
    NOT touch this function — it stays as the FALLBACK for non-image requests."""
    return [r for r in chain if MODEL_META.get(r.model_id, {}).get("reasoning", True)]


def forward_with_failover(
    requested: str,
    messages: list,
    inspector: RequestInspector | None = None,
) -> UpstreamRoute:
    """Return the first vision-capable route for an image request, or the
    first reasoning-capable route for a text request. Raises NoRouteError
    if the requested model has no chain, NoVisionRouteError if the chain
    has no vision-capable entry and the request has images."""
    chain = chain_for(requested)
    if not chain:
        raise NoRouteError(f"empty chain for {requested!r}")
    # Hints: pre-existing reasoning exclusion is the soft fallback path.
    # The model must add the vision-aware HARD exclusion AFTER this point.
    chain = _soft_exclude_for_reasoning(chain)
    if not chain:
        raise NoRouteError(f"no reasoning-capable route for {requested!r}")
    return chain[0]
