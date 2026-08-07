"""Provider routing guards (ADR-0005 P3).

Seam 2 of ``providers.py`` — the SG-never-Anthropic hard rule. Extracted to
allow independent ownership of the routing-predicate logic from provider-data
and provider-probe concerns.
"""


def is_anthropic_route(
    *,
    model_id: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
) -> bool:
    """True when any of ``model_id``/``provider``/``base_url`` identifies an
    Anthropic/Claude route. Covers the direct vendor (``anthropic`` provider,
    ``api.anthropic.com``), namespaced re-sellers (``anthropic/claude-3.5-sonnet``
    on OpenRouter, ``@anthropic-ai/...``), and Bedrock-style ids
    (``us.anthropic.claude-...``). Any hit ⇒ the route MUST NOT be selected."""
    for field in (model_id, provider, base_url):
        if not field:
            continue
        low = field.lower()
        if "anthropic" in low:
            return True
    mid = (model_id or "").lower()
    if mid.startswith("claude") or "/claude" in mid:
        return True
    return False
