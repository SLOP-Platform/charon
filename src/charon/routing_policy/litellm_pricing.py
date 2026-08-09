"""litellm.model_cost as a PRICING SOURCE for cost-rank derivation (LITELLM-COST-ADOPT).

THE PROBLEM this module fixes (measured 2026-08-08): ``models.json`` holds ~860
models and only ~10 carry ``cost_input``/``cost_output``. ``cost_rank.derived_cost_rank``
derives ordering from (1) live metered cost, (2) configured ``cost_input``/
``cost_output``, (3) a NEUTRAL 1000 fallback — so ~850 legs collapsed to the
same value and cost-first ordering was INOPERATIVE. A live ``glm-5.2`` request
served via openrouter with ``X-Charon-Failovers: 0`` while three nominally-
cheaper legs were never tried proved the collapse.

THE FIX: ``litellm`` ships ``litellm.model_cost`` — a curated, per-token-USD
price table keyed by ``"<litellm_provider>/<model>"`` (or bare ``"<model>"`` for
direct providers). This module is the ONE seam that maps Charon's
provider-suffixed catalog ids onto litellm keys and yields ``cost_input``/
``cost_output`` so ``derived_cost_rank`` has real numbers.

MAPPING RULE (provider-faithful — NEVER guesses across providers):

  Charon ids are provider-suffixed (``glm-5.2-or``, ``deepseek-v4-pro-ds``,
  ``gpt-5-ng``); the suffix encodes the serving provider. ``upstream_model``
  (when present) is the raw id the upstream advertises. For a model to be
  PRICED by litellm, the provider that ACTUALLY SERVES the request must be one
  litellm models directly:

      openrouter -> "openrouter/<upstream_model>"
      deepseek   -> "deepseek/<upstream_or_id>"  (bare "<id>" also tried —
                    litellm keys deepseek both ways)
      groq       -> "groq/<upstream_or_id>"
      together   -> "together_ai/<upstream_or_id>"
      mistral    -> "mistral/<upstream_or_id>"
      cerebras   -> "cerebras/<upstream_or_id>"
      zai        -> "zai/<upstream_or_id>"

  Proprietary aggregators (``nanogpt``, ``neuralwatt``, ``opencode-zen``,
  ``opencode-go``) have NO litellm pricing source — their per-token rate is
  their own (markup/subscription), and stamping the *underlying* provider's
  price would be a GUESS that misprices the money path (worse than no price).
  Such legs stay UNPRICED and are REPORTED by :func:`coverage_report`, never
  defaulted to the neutral 1000 silently.

  A ``:free`` suffix on the upstream id is stripped before lookup (free models
  are priced $0 by the ``free:true`` axis, not by litellm).

RED-PROOF contract:
  * a model with a known litellm price MUST get that price (exact per-token USD);
  * an UNMAPPABLE model MUST stay unpriced (``price_for`` returns ``None``) and
    appear in :func:`coverage_report`'s ``unmapped`` list — NEVER defaulted.

This module is OPT-IN safe: importing it never touches the network or disk; the
litellm table is an in-process dict. Callers (:func:`enrich_registry`,
:func:`price_for`) are pure functions of the registry + the litellm table.
"""
from __future__ import annotations

import logging
import math
from typing import Any, TypedDict

log = logging.getLogger("charon.litellm_pricing")

# Charon provider name -> litellm provider prefix (the ONE that actually serves).
# ONLY providers litellm models directly are listed; a provider absent here has
# NO litellm pricing source and its legs are reported as unmapped (never guessed).
_PROVIDER_TO_LITELLM: dict[str, str] = {
    "openrouter": "openrouter",
    "deepseek": "deepseek",
    "groq": "groq",
    "together": "together_ai",
    "mistral": "mistral",
    "cerebras": "cerebras",
    "zai": "zai",
}

# The provider suffixes Charon stamps onto catalog ids (the ``-<tag>`` encoding).
# Used to recover the upstream id when ``upstream_model`` is absent. Order matters
# only for overlap safety; the set is deliberately explicit (no ``-x`` that could
# clip a real model-name segment like ``gpt-5-x``).
_PROVIDER_SUFFIXES: tuple[str, ...] = (
    "openrouter", "together", "cerebras", "groq",
    "or", "ng", "ds", "nw", "go", "cb", "code", "free",
)


class UnmappedModel(TypedDict):
    """One entry in :func:`coverage_report`'s ``unmapped`` list — a NAMED
    unmappable model (never a silent default)."""
    id: str
    provider: str
    upstream_model: object  # str | None — the raw upstream id, when present
    tried: list[str]        # candidate litellm keys attempted (evidence)


class CoverageReport(TypedDict):
    """The evidence surface :func:`coverage_report` returns: per-provider
    ``priced/total`` and the NAMED list of unmapped models."""
    total: int
    priced: int
    unmapped_count: int
    per_provider: dict[str, list[int]]
    unmapped: list[UnmappedModel]


def _strip_free_suffix(s: str) -> str:
    """Strip a trailing ``:free`` (OpenRouter free-tier id convention)."""
    return s[: -len(":free")] if s.endswith(":free") else s


def _strip_provider_suffix(model_id: str) -> str:
    """Recover the upstream id from a provider-suffixed Charon id when
    ``upstream_model`` is absent. Strips the LAST ``-<tag>`` segment iff it is a
    known provider suffix (so ``gpt-5.4-mini-ng`` -> ``gpt-5.4-mini``, but
    ``deepseek-v4-flash`` is left intact — ``-flash`` is NOT a provider suffix)."""
    for tag in _PROVIDER_SUFFIXES:
        if model_id.endswith("-" + tag):
            stripped = model_id[: -(len(tag) + 1)]
            if stripped:
                return stripped
    return model_id


def _litellm_candidates(model_id: str, spec: dict[str, Any]) -> list[str]:
    """Yield litellm key candidates, provider-faithful, best-first. NEVER guesses
    across providers. Returns ``[]`` for a provider litellm does not model
    (proprietary aggregators) — those legs are reported as unmapped."""
    prov = spec.get("provider")
    if not isinstance(prov, str):
        return []
    lp = _PROVIDER_TO_LITELLM.get(prov)
    if lp is None:
        return []  # proprietary aggregator — no litellm source; report unmapped
    um = spec.get("upstream_model")
    if isinstance(um, str) and um:
        base = _strip_free_suffix(um)
    else:
        base = _strip_provider_suffix(model_id)
    if not base:
        return []
    if lp == "deepseek":
        # litellm keys deepseek both as "deepseek/<model>" and bare "<model>"
        return [f"deepseek/{base}", base]
    return [f"{lp}/{base}"]


def _get_model_cost() -> dict[str, dict] | None:
    """Return the litellm ``model_cost`` table, or ``None`` when litellm is not
    installed (the optional ``[router]`` extra is absent). A missing table makes
    :func:`price_for` return ``None`` for every id — the neutral fallback in
    ``derived_cost_rank`` stays, so cost ordering is unchanged, never broken."""
    try:
        from litellm import model_cost  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 — optional extra; absence is a reportable, not a crash
        log.debug("litellm.model_cost unavailable (litellm not installed) — pricing source idle")
        return None
    # litellm exports model_cost as a dict, but the type is not statically
    # declared (the import is ignore'd), so narrow through object to keep the
    # runtime guard reachable and honest rather than relying on the ignore.
    raw: object = model_cost
    if not isinstance(raw, dict):
        return None
    return raw


def price_for(model_id: str, spec: dict[str, Any]) -> tuple[float, float] | None:
    """Return ``(cost_input, cost_output)`` per-token USD for *model_id* from
    ``litellm.model_cost``, or ``None`` when the model is unmappable.

    Per-token USD is litellm's native unit (``input_cost_per_token`` /
    ``output_cost_per_token``) and matches Charon's ``cost_input``/``cost_output``
    canonical unit (per ``providers._extract_pricing`` — verbatim per-token, no
    1e6 scaling). Returns ``None`` (NOT a guessed/defaulted price) when:

      * litellm is not installed;
      * the model's provider is a proprietary aggregator litellm does not model;
      * no candidate litellm key matches;
      * the matched entry has no finite, non-negative ``input_cost_per_token``/
        ``output_cost_per_token`` (an image/audio-only model, or a corrupt entry).

    The price is EXACT — never adjusted, rounded, or blended here. The 3:1
    in:out blend is ``derived_cost_rank``'s job; this source hands it the raw
    per-token magnitudes the way ``models.json``'s ``cost_input``/``cost_output``
    would."""
    table = _get_model_cost()
    if table is None:
        return None
    for cand in _litellm_candidates(model_id, spec):
        entry = table.get(cand)
        if not isinstance(entry, dict):
            continue
        ci = entry.get("input_cost_per_token")
        co = entry.get("output_cost_per_token")
        try:
            ci_f = float(ci) if ci is not None else None
            co_f = float(co) if co is not None else None
        except (TypeError, ValueError):
            continue
        # Reject non-finite / negative — garbage never reaches the money path.
        if ci_f is not None and (not math.isfinite(ci_f) or ci_f < 0):
            continue
        if co_f is not None and (not math.isfinite(co_f) or co_f < 0):
            continue
        if ci_f is None and co_f is None:
            continue  # entry exists but carries no token price (e.g. image-only)
        return (ci_f or 0.0, co_f or 0.0)
    return None


def enrich_registry(registry: dict[str, object]) -> dict[str, dict[str, Any]]:
    """Stamp litellm-sourced ``cost_input``/``cost_output`` onto registry entries
    that lack them. Returns a NEW dict (the input is not mutated); only entries
    that get a price are copied-with-update so the rest alias the originals.

    CLOBBER-SAFE: an operator's hand-set ``cost_input``/``cost_output`` is NEVER
    overwritten — litellm only fills entries where BOTH are absent (the
    ~850-leg gap that collapsed to the neutral 1000). ``priced_by: "litellm"`` is
    stamped on enriched entries so downstream tools can attribute the source and
    a re-enrichment is idempotent (an operator later hand-setting a price still
    wins because the marker is irrelevant once a cost field is present).

    NEVER GUESSES: an entry litellm cannot price is left untouched — the neutral
    1000 fallback in ``derived_cost_rank`` remains, and the model is named in
    :func:`coverage_report`'s ``unmapped`` list rather than silently defaulted.
    """
    out: dict[str, dict[str, Any]] = {}
    for mid, spec in registry.items():
        if not isinstance(spec, dict):
            # pass through non-dict entries unchanged (registry is object-valued)
            out[mid] = spec  # type: ignore[assignment]
            continue
        has_ci = spec.get("cost_input") is not None
        has_co = spec.get("cost_output") is not None
        if has_ci or has_co:
            out[mid] = spec  # operator or discovery already priced — keep as-is
            continue
        price = price_for(mid, spec)
        if price is None:
            out[mid] = spec  # unmappable — leave unpriced (reported, not guessed)
            continue
        ci, co = price
        enriched = dict(spec)
        enriched["cost_input"] = ci
        enriched["cost_output"] = co
        enriched["priced_by"] = "litellm"
        out[mid] = enriched
    return out


def coverage_report(registry: dict[str, object]) -> CoverageReport:
    """Report litellm pricing coverage for *registry*: per-provider
    ``priced/total`` and the NAMED list of unmapped models (never a silent
    default). Returns a JSON-serializable dict::

        {
          "total": 201,
          "priced": 30,
          "unmapped_count": 171,
          "per_provider": {"openrouter": [23, 50], "deepseek": [2, 2], ...},
          "unmapped": [
            {"id": "glm-5.2-or", "provider": "openrouter",
             "upstream_model": "z-ai/glm-5.2", "tried": ["openrouter/z-ai/glm-5.2"]},
            ...
          ],
        }

    This is the evidence surface the brief requires: "Report the mapping rule
    and its coverage as priced/total PER PROVIDER, and NAME every model you
    could not map rather than guessing."
    """
    table = _get_model_cost()
    per_provider: dict[str, list[int]] = {}
    priced = 0
    unmapped: list[UnmappedModel] = []
    for mid, spec in registry.items():
        if not isinstance(spec, dict):
            continue
        prov = str(spec.get("provider") or "<unknown>")
        counter = per_provider.setdefault(prov, [0, 0])
        counter[1] += 1
        # operator-set pricing counts as priced (it IS a real price)
        if spec.get("cost_input") is not None or spec.get("cost_output") is not None:
            priced += 1
            counter[0] += 1
            continue
        if table is not None:
            price = price_for(mid, spec)
            if price is not None:
                priced += 1
                counter[0] += 1
                continue
        unmapped.append({
            "id": mid,
            "provider": prov,
            "upstream_model": spec.get("upstream_model"),
            "tried": _litellm_candidates(mid, spec),
        })
    return {
        "total": len(registry),
        "priced": priced,
        "unmapped_count": len(unmapped),
        "per_provider": per_provider,
        "unmapped": unmapped,
    }
