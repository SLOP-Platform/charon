"""Provider model discovery — query /v1/models, cross-reference, build cost maps.

Implements PROPOSAL-1 Phase A: discover all models available across configured
providers by querying their /v1/models endpoints in parallel, then cross-reference
model IDs to build a cost map for routing decisions.

CATALOG-COMPLETENESS (P0): price (input/output per Mtok), context window, and the
free-tier flag are REQUIRED catalog fields. An entry missing any of them is
REJECTED loudly (:class:`CatalogIncompleteError`) — never silently routed as if
it had data. The cost map is PERSISTED (``cost_map.json``) and a restart READS it
rather than recomputing; litellm's ``model_cost`` feed (already a dependency) is
consulted FIRST as a price source, then provider /models; disagreement between
sources is recorded rather than silently picking a winner.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
from pathlib import Path

from . import (
    config,
    netutil,  # key-egress choke point (keyed_request/open_keyed)
    providers,
    secrets,
)

log = logging.getLogger("charon.discover")

_COST_MAP_FILE = "cost_map.json"

# Required catalog fields — a cost-map entry missing any of these is REJECTED
# loudly (CATALOG-COMPLETENESS contract a). ``cost_input``/``cost_output`` are
# per-token USD (the canonical unit the rest of the routing layer expects).
_REQUIRED_FIELDS: tuple[str, ...] = ("cost_input", "cost_output", "context_window", "free")


class CatalogIncompleteError(ValueError):
    """A catalog entry is missing a required field (price / context / free flag).

    Raised LOUDLY — never silently dropped — so the operator sees that a served
    model carries no price/context data and the cost directive cannot rank it
    (CATALOG-COMPLETENESS contract a: revert the check → RED)."""


def validate_catalog_entry(model_id: str, entry: dict) -> None:
    """Raise :class:`CatalogIncompleteError` if *entry* is missing a required
    catalog field (price input/output, context window, free flag).

    ANTI-OVER-BLOCK (contract d): an entry with EVERY required field present
    passes untouched. The check is the SINGLE home for "is this entry complete
    enough to route on" so the cost directive never ranks on absent data."""
    missing = [f for f in _REQUIRED_FIELDS if f not in entry]
    if missing:
        raise CatalogIncompleteError(
            f"catalog entry {model_id!r} is missing required field(s): "
            f"{', '.join(missing)} (need cost_input, cost_output, context_window, "
            f"free). A served model without price/context cannot be cost-ranked — "
            f"populate it (litellm feed, provider /models, or hand-set) before "
            f"serving it."
        )


# ── litellm price feed (ADOPT — already a dependency) ──────────────────────────
# litellm ships ``model_prices_and_context_window.json`` carrying price + context
# for thousands of models. Per the substrate directive we consult it FIRST as a
# price source, then provider /models; disagreement between sources is RECORDED
# (a ``price_sources`` list per provider entry) rather than silently picking a
# winner — multiple corroborating sources over one SSOT for observed facts.
#
# The feed is read from the in-memory ``litellm.model_cost`` dict (the parsed form
# of the same JSON). Unit: ``input_cost_per_token`` / ``output_cost_per_token`` are
# per-token USD — the SAME canonical unit Charon stores as ``cost_input`` /
# ``cost_output`` (see providers._extract_pricing), so values are carried through
# verbatim with NO scaling.


def _litellm_feed() -> dict[str, dict]:
    """Return ``{casefolded_model_id: {cost_input, cost_output, context_window,
    free, source: "litellm"}}`` from litellm's ``model_cost``.

    Lazy import: litellm is an OPTIONAL runtime dep for the discovery path (the
    gateway commodity plane adopts it, but discovery must not hard-fail when it
    is absent). Returns ``{}`` when litellm is not installed. Filters the
    ``sample_spec`` placeholder and non-finite/negative prices."""
    try:
        import litellm  # lazy: discovery must not require litellm to import
    except ImportError:  # pragma: no cover — litellm is a declared extra
        return {}
    feed: dict[str, dict] = {}
    mc = getattr(litellm, "model_cost", None)
    if not isinstance(mc, dict):
        return {}
    import math
    for mid, spec in mc.items():
        if not isinstance(mid, str) or not isinstance(spec, dict):
            continue
        if mid == "sample_spec":
            continue
        ci = spec.get("input_cost_per_token")
        co = spec.get("output_cost_per_token")
        try:
            ci_f = float(ci) if ci is not None else None
            co_f = float(co) if co is not None else None
        except (TypeError, ValueError):
            continue
        if ci_f is not None and not (math.isfinite(ci_f) and ci_f >= 0):
            ci_f = None
        if co_f is not None and not (math.isfinite(co_f) and co_f >= 0):
            co_f = None
        if ci_f is None and co_f is None:
            continue
        # context: prefer max_input_tokens, fall back to max_tokens
        ctx = spec.get("max_input_tokens")
        if not isinstance(ctx, int) or ctx <= 0:
            ctx = spec.get("max_tokens")
        if not isinstance(ctx, int) or ctx <= 0:
            ctx = None
        free = bool(ci_f == 0.0 and co_f == 0.0)
        feed[mid.casefold()] = {
            "cost_input": float(ci_f) if ci_f is not None else 0.0,
            "cost_output": float(co_f) if co_f is not None else 0.0,
            "context_window": ctx,
            "free": free,
            "source": "litellm",
        }
    return feed


def _merge_litellm(entry: dict, mid: str, feed: dict[str, dict],
                   provider_name: str | None = None) -> None:
    """Corroborate *entry* (a per-provider cost-map entry) with the litellm feed.

    Fills ``cost_input``/``cost_output``/``context_window`` when the provider
    /models payload omitted them, and RECORDS disagreement: when both sources
    quote a price and they differ, the provider's quote WINS (it is the
    provider's own price) but the litellm figure is preserved in
    ``price_sources`` so the discrepancy is visible, not erased."""
    candidates = [mid.casefold()]
    if provider_name:
        candidates.insert(0, f"{provider_name}/{mid}".casefold())
    spec = next((feed[key] for key in candidates if key in feed), None)
    if spec is None:
        return
    if "cost_input" not in entry:
        entry["cost_input"] = spec["cost_input"]
    if "cost_output" not in entry:
        entry["cost_output"] = spec["cost_output"]
    if "context_window" not in entry:
        cw = spec["context_window"]
        if cw is not None:
            entry["context_window"] = cw
    if not entry.get("free") and spec.get("free"):
        entry["free"] = True
    sources: list[dict] = []
    if (entry.get("cost_input") != spec["cost_input"] or
            entry.get("cost_output") != spec["cost_output"]):
        sources.append({"source": "litellm",
                        "cost_input": spec["cost_input"],
                        "cost_output": spec["cost_output"]})
    if sources:
        entry.setdefault("price_sources", [])
        if isinstance(entry["price_sources"], list):
            entry["price_sources"].extend(sources)
    entry.setdefault("sources", []).append("litellm")


def discover_provider(base_url: str, api_key: str | None,
                      strip_v1: bool = True, timeout: float = 10) -> list[dict] | None:
    """Query a single provider's /models endpoint.

    If *strip_v1* is True the base URL already includes the /v1 prefix so /models
    is appended.  If False the base is a bare host and /v1/models is appended.
    Returns a list of raw model dicts (each with at least ``"id"``), or None on
    any error.
    """
    # Endpoint construction + SSRF guard delegated to the shared helper
    # (PROVIDER-URL-HELPER): previously this function did its own bare
    # ``base_url.rstrip("/") + "/models"`` with no scheme/host check at all,
    # so a bad base could surface as a confusing urllib error instead of None.
    path = "models" if strip_v1 else "v1/models"
    try:
        url = providers.join_endpoint(providers.validate_base_url(base_url), path)
    except ValueError:
        return None

    try:
        # netutil is the key-egress choke point: it attaches the Bearer and
        # disables redirect-following (urllib does NOT strip Authorization
        # cross-host, so a 302 here would hand the key to another host).
        req = netutil.keyed_request(url, api_key=api_key, method="GET")
        resp = netutil.open_keyed(req, timeout=timeout)
        raw = resp.read()
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None

    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None

    result: list[dict] = []
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("id"), str):
            result.append(it)
        elif isinstance(it, str):
            result.append({"id": it})
    return result


def _provider_blended_cost(entry: dict) -> float:
    """Cost-first sort key for a per-provider entry: the 3:1 in:out blend the
    routing layer uses (mirrors routing_policy.derived_cost_rank). Missing
    prices sort last (``inf``) so an unpriced offer never floats above a priced
    one (CATALOG-COMPLETENESS contract c — cheapest capable provider wins)."""
    ci = entry.get("cost_input")
    co = entry.get("cost_output")
    if ci is None and co is None:
        return float("inf")
    ci = float(ci) if ci is not None else 0.0
    co = float(co) if co is not None else 0.0
    return (3.0 * ci + co) / 4.0


def build_cost_map(discoveries: dict[str, list[dict] | None]) -> dict:
    """Cross-reference model IDs across providers into a cost map.

    *discoveries* is ``{provider_name: [model_dict, ...] | None}`` where each
    model dict is a raw /models entry (at minimum ``{"id": str}``).

    Returns ``{model_id: {"providers": [...]}}`` grouped case-insensitively by
    model ID. Each provider entry carries ``provider``, ``free``, and (when
    available) ``cost_input``/``cost_output``/``context_window``. The litellm
    ``model_cost`` feed is consulted FIRST to fill price/context a provider's
    /models omitted (CATALOG-COMPLETENESS scope 3), with disagreement recorded.

    Providers serving the SAME model are sorted CHEAPEST-FIRST by the 3:1
    in:out blend (contract c) — so the cheapest capable provider for a model is
    always first. A provider whose discovery returned ``None`` (failure) is
    simply skipped.
    """
    feed = _litellm_feed()
    _by_key: dict[str, tuple[str, list[dict]]] = {}

    for provider_name, model_list in discoveries.items():
        if not model_list:
            continue
        for m in model_list:
            mid = m.get("id")
            if not isinstance(mid, str):
                continue
            key = mid.casefold()

            entry: dict[str, object] = {"provider": provider_name}

            pricing = m.get("pricing")
            if isinstance(pricing, dict):
                entry["pricing"] = dict(pricing)

            # extract per-token cost from provider pricing (the canonical seam)
            price_entry: dict[str, object] = {}
            providers._extract_pricing(m, price_entry)
            for fld in ("cost_input", "cost_output"):
                v = price_entry.get(fld)
                if isinstance(v, (int, float)):
                    entry[fld] = float(v)

            free_val = False
            if mid.endswith(":free"):
                free_val = True
            elif isinstance(pricing, dict):
                try:
                    vals = [float(pricing[k]) for k in ("prompt", "completion")]
                    free_val = bool(vals) and all(v == 0 for v in vals)
                except (KeyError, TypeError, ValueError):
                    pass
            entry["free"] = free_val

            # upstream context, when the provider advertises it
            for src_key in ("context_window", "context_length"):
                ctx = m.get(src_key)
                if isinstance(ctx, (int, float)) and int(ctx) > 0:
                    entry["context_window"] = int(ctx)
                    break

            # corroborate with the litellm feed FIRST (fills gaps, records
            # disagreement) so an unpriced provider entry still gets a price
            # when litellm knows the model.
            _merge_litellm(entry, mid, feed, provider_name)
            entry.setdefault("sources", [])

            if key not in _by_key:
                _by_key[key] = (mid, [])
            _by_key[key][1].append(entry)

    # cheapest-first within each model (contract c): stable sort keeps the
    # provider discovery order for ties.
    out: dict[str, dict] = {}
    for orig_id, prov_list in _by_key.values():
        prov_list.sort(key=_provider_blended_cost)
        out[orig_id] = {"providers": prov_list}
    return out


def save_cost_map(cost_map: dict, config_dir: str | Path | None = None):
    """Write cost_map.json to *config_dir* (or the default config dir)."""
    d = Path(config_dir) if config_dir is not None else secrets.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / _COST_MAP_FILE
    p.write_text(json.dumps(cost_map, indent=2), encoding="utf-8")


def load_cost_map(config_dir: str | Path | None = None) -> dict:
    """Read cost_map.json.  Returns ``{}`` when the file is absent or corrupt."""
    d = Path(config_dir) if config_dir is not None else secrets.config_dir()
    p = d / _COST_MAP_FILE
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_cost_map(config_dir: str | Path | None = None, *,
                 refresh: bool = False, timeout: int = 10) -> dict:
    """Return the cost map, reading the PERSISTED ``cost_map.json`` when present
    and *refresh* is False (a restart READS rather than recomputes —
    CATALOG-COMPLETENESS contract b). When absent or *refresh* is True, runs a
    fresh discovery (which persists the result) and returns it."""
    if not refresh:
        cached = load_cost_map(config_dir=config_dir)
        if cached:
            return cached
    return discover_models(refresh=refresh, timeout=timeout, config_dir=config_dir)


def discover_models(refresh: bool = False, timeout: int = 10,
                    config_dir: str | Path | None = None) -> dict:
    """Query all configured providers' /v1/models endpoints.

    Loads configured providers from config + built-in presets, resolves API keys
    from env vars or secrets, then queries all providers in parallel via
    ThreadPoolExecutor (max 5 workers).  Saves the resulting cost map to disk and
    returns it.

    *refresh* is reserved for future use (force re-query even if cached). A
    restart that wants to READ the persisted map rather than re-poll should call
    :func:`get_cost_map` (CATALOG-COMPLETENESS contract b) — this function always
    performs a fresh poll and persists the result.
    """
    prov_cfg = config.load_providers(config_dir=config_dir)
    secs = secrets.load_secrets(cd=config_dir)

    targets: list[tuple[str, str, str | None, bool]] = []
    seen: set[str] = set()

    for name, preset in providers.PRESETS.items():
        override = prov_cfg.get(name) or {}
        base = override.get("base_url", preset.base_url)
        key_env = override.get("key_env", preset.key_env)
        strip = override.get("strip_v1", preset.strip_v1)

        api_key = secrets.get_provider_key(name, key_env=key_env, base_url=base, secs=secs)

        targets.append((name, base, api_key, strip))
        seen.add(name)

    for name, prov in prov_cfg.items():
        if name in seen:
            continue
        base = prov.get("base_url")
        if not isinstance(base, str):
            continue
        key_env = prov.get("key_env")
        api_key = secrets.get_provider_key(
            name, key_env=key_env if isinstance(key_env, str) else None,
            base_url=base, secs=secs)
        strip = prov.get("strip_v1", True)
        targets.append((name, base, api_key, strip))

    discoveries: dict[str, list[dict] | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futs: dict[concurrent.futures.Future[list[dict] | None], str] = {}
        for name, base, api_key, strip in targets:
            fut = executor.submit(discover_provider, base, api_key, strip, timeout)
            futs[fut] = name

        for fut in concurrent.futures.as_completed(futs):
            name = futs[fut]
            try:
                discoveries[name] = fut.result()
            except Exception:  # noqa: BLE001
                discoveries[name] = None

    cost_map = build_cost_map(discoveries)
    save_cost_map(cost_map, config_dir=config_dir)
    _update_model_pricing_from_discovery(discoveries, config_dir=config_dir)
    return cost_map


def _update_model_pricing_from_discovery(
    discoveries: dict[str, list[dict] | None],
    config_dir: str | Path | None = None,
) -> None:
    """Persist per-token pricing from discovered models into ``models.json``.

    For each discovered model that matches an existing entry in the model
    registry (case-insensitive), extract ``cost_input`` / ``cost_output``
    via ``providers._extract_pricing`` and write them into the registry so
    served models carry real cost data.

    Clobber-protection: an operator's hand-set price is never overwritten. A
    price written by this function stamps ``priced_by: "discovery"``; on later
    discoveries only entries carrying that marker are refreshed. An existing
    ``cost_input``/``cost_output`` without the marker is treated as operator-set
    (``config.add_model``, ``models import``, or a hand-edit) and left untouched.
    """
    models = config.load_models(config_dir=config_dir)
    if not models:
        return
    changed = False
    for _provider_name, model_list in discoveries.items():
        if not model_list:
            continue
        for m in model_list:
            mid = m.get("id")
            if not isinstance(mid, str):
                continue
            key = mid.casefold()
            matched = None
            for existing_id in models:
                if existing_id.casefold() == key:
                    matched = existing_id
                    break
            if matched is None:
                continue
            existing = models[matched]
            # Protect an operator-set price: a cost value NOT stamped by a prior
            # discovery is operator-owned and must survive re-discovery.
            if existing.get("priced_by") != "discovery" and (
                "cost_input" in existing or "cost_output" in existing):
                continue
            entry: dict[str, object] = {}
            providers._extract_pricing(m, entry)
            wrote = False
            for field in ("cost_input", "cost_output"):
                if field in entry:
                    v = entry[field]
                    if isinstance(v, (int, float)):
                        existing[field] = float(v)
                        wrote = True
            if wrote:
                existing["priced_by"] = "discovery"
                changed = True
    if changed:
        config._save("models.json", models, config_dir=config_dir)


# ── Phase D: OpenRouter swarm import ────────────────────────────────

_OPENROUTER_API = "https://openrouter.ai/api/v1/models"
_ALIAS_FILE = "model_aliases.json"


def discover_openrouter(timeout: float = 10) -> list[dict] | None:
    """Fetch the OpenRouter model catalogue (no auth needed)."""
    try:
        req = netutil.keyed_request(_OPENROUTER_API, method="GET")
        resp = netutil.open_keyed(req, timeout=timeout)
        raw = resp.read()
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(data, list):
        return [m for m in data if isinstance(m, dict) and "id" in m]
    items = data.get("data") if isinstance(data, dict) else None
    if isinstance(items, list):
        return [m for m in items if isinstance(m, dict) and "id" in m]
    return None


def _load_alias_map(config_dir: str | Path | None = None) -> dict:
    d = Path(config_dir) if config_dir is not None else secrets.config_dir()
    p = d / _ALIAS_FILE
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_KNOWN_PREFIXES = {"openai", "anthropic", "google", "meta-llama", "mistralai",
                   "deepseek", "cohere", "x-ai", "perplexity", "together", "groq"}


def fuzzy_match_model_id(or_id: str, charon_models: list[str],
                         config_dir: str | Path | None = None) -> tuple[str | None, int]:
    """Match an OpenRouter model ID to an existing Charon model.

    Returns ``(charon_id, match_stage)`` where stage is:
        0 — no match
        1 — exact match (case-insensitive)
        2 — prefix-stripped match
        3 — alias-map match

    Stage 1 matches can be auto-imported; stages 2-3 need review.
    """
    key = or_id.casefold()
    alias_map = _load_alias_map(config_dir)
    if key in alias_map:
        return alias_map[key], 3
    for m in charon_models:
        if m.casefold() == key:
            return m, 1
    for prefix in _KNOWN_PREFIXES:
        tag = prefix + "/"
        if or_id.lower().startswith(tag):
            bare = or_id[len(tag):]
            for m in charon_models:
                if m.casefold() == bare.casefold():
                    return m, 2
    return None, 0


def import_openrouter_models(dry_run: bool = False,
                              config_dir: str | Path | None = None) -> dict:
    """Pull OpenRouter catalogue, cross-reference, and bulk-import.

    Returns ``{"imported": N, "fuzzy_review": N, "new": N, "skipped": N}``.
    When *dry_run* is True, nothing is persisted.
    Stage-1 (exact) matches are auto-imported; stage 2-3 matches go to review.
    """
    or_models = discover_openrouter()
    if not or_models:
        return {"imported": 0, "fuzzy_review": 0, "new": 0, "skipped": 0}
    existing = config.load_models(config_dir=config_dir)
    charon_ids = list(existing.keys())
    imported, fuzzy_review, new, skipped = 0, 0, 0, 0
    review: dict[str, list[dict]] = {}
    for m in or_models:
        or_id = m.get("id")
        if not isinstance(or_id, str):
            skipped += 1
            continue
        match, stage = fuzzy_match_model_id(or_id, charon_ids, config_dir=config_dir)
        if match is not None and stage == 1:
            if not dry_run:
                cost_input: float | None = None
                cost_output: float | None = None
                pricing = m.get("pricing")
                # Canonical per-token USD, validated (finite/non-negative), via the
                # single pricing seam — OpenRouter values are already per-token.
                price_entry: dict[str, object] = {}
                providers._extract_pricing(m, price_entry)
                ci = price_entry.get("cost_input")
                co = price_entry.get("cost_output")
                if isinstance(ci, (int, float)):
                    cost_input = float(ci)
                if isinstance(co, (int, float)):
                    cost_output = float(co)
                ctx = m.get("context_length")
                context_window: int | None = int(ctx) if isinstance(ctx, (int, float)) else None
                free = or_id.endswith(":free") or (isinstance(pricing, dict) and
                    all(float(str(pricing.get(k, "0"))) == 0 for k in ("prompt", "completion")))
                if free:
                    cost_input = cost_output = 0.0
                config.add_model(match, free=free, context_window=context_window,
                                 cost_input=cost_input, cost_output=cost_output)
            imported += 1
        elif match is not None:
            fuzzy_review += 1
            if not dry_run:
                key = or_id.casefold()
                review.setdefault(key, []).append(m)
        else:
            new += 1
            if not dry_run:
                key = or_id.casefold()
                review.setdefault(key, []).append(m)
    if not dry_run and review:
        d = Path(config_dir) if config_dir is not None else secrets.config_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "discover_review.json").write_text(
            json.dumps(review, indent=2), encoding="utf-8")
    return {"imported": imported, "fuzzy_review": fuzzy_review,
            "new": new, "skipped": skipped}
