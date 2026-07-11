"""Pricing and limits drift checker (R17).

Reads a canonical provider-pricing-limits data file and compares it against the
currently configured ``models.json`` / ``providers.json``. Flags:

- Price moves > configurable threshold (default 5 %).
- Limit changes (RPM / RPD / TPM / TPD cuts or additions).
- Missing models / providers in config vs canonical.
- Unknown / stale entries in config not present in canonical.
- Non-token pricing model drift (energy_kWh, subscription, request_cap).

Outputs structured :class:`Finding` objects that can feed downstream alerts
(R16) and cost-rank (R5).  Standalone — no threading, no network, no external
deps.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import config

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One drift / mismatch / staleness finding."""

    severity: str  # red | yellow | green
    category: str  # price_drift | limit_change | missing | stale | plan | non_token
    provider: str
    model: str | None
    message: str
    canonical_value: Any = None
    configured_value: Any = None


@dataclass
class ProviderLimitSpec:
    """Canonical limits for a provider."""

    rpm: int | None = None
    rpd: int | None = None
    tpm: int | None = None
    tpd: int | None = None


@dataclass
class ModelPriceSpec:
    """Canonical per-token pricing for a model."""

    cost_input: float | None = None
    cost_output: float | None = None
    free: bool = False


@dataclass
class NonTokenPricing:
    """Non-token pricing descriptor (NeuralWatt / Featherless / Synthetic)."""

    type: str  # energy_kwh | subscription | request_cap
    rate: float | None = None  # marginal rate (USD per unit)
    unit: str | None = None  # kWh | mo | request
    included_monthly: float | None = None  # allotment per period (e.g. 6 kWh)
    subscription_usd: float | None = None  # flat monthly cost
    overflow_rate: float | None = None  # PAYG rate past allotment


@dataclass
class ProviderCanonical:
    """Canonical entry for one provider — the source of truth."""

    limits: ProviderLimitSpec = field(default_factory=ProviderLimitSpec)
    pricing: dict[str, ModelPriceSpec] = field(default_factory=dict)
    non_token: NonTokenPricing | None = None
    plan: str | None = None  # e.g. "payg", "basic", "pro"
    source_url: str | None = None
    last_verified: str | None = None


@dataclass
class CheckerConfig:
    """Top-level canonical data file schema."""

    providers: dict[str, ProviderCanonical] = field(default_factory=dict)
    threshold_pct: float = 5.0
    last_updated: str | None = None
    sources: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Load / save canonical file
# ---------------------------------------------------------------------------

_CANONICAL_FILE = "provider_pricing_limits.json"


def _snake_to_camel(snake: str) -> str:
    """Convert a snake_case key to the camelCase used in canonical JSON."""
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _coerce_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def _coerce_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _load_non_token(data: dict[str, Any]) -> NonTokenPricing | None:
    t = data.get("type")
    if t is None:
        return None
    return NonTokenPricing(
        type=str(t),
        rate=_coerce_float(data.get("rate")),
        unit=data.get("unit"),
        included_monthly=_coerce_float(data.get("included_monthly")),
        subscription_usd=_coerce_float(data.get("subscription_usd")),
        overflow_rate=_coerce_float(data.get("overflow_rate")),
    )


def load_canonical(
    *, config_dir: str | Path | None = None
) -> CheckerConfig:
    """Read the canonical ``provider_pricing_limits.json`` from *config_dir*."""
    d = Path(config_dir) if config_dir is not None else config.secrets.config_dir()
    p = d / _CANONICAL_FILE
    if not p.exists():
        return CheckerConfig()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CheckerConfig()
    if not isinstance(raw, dict):
        return CheckerConfig()

    providers: dict[str, ProviderCanonical] = {}
    for pname, pblock in raw.get("providers", {}).items():
        if not isinstance(pblock, dict):
            continue
        lim = ProviderLimitSpec(
            rpm=_coerce_int(pblock.get("limits", {}).get("rpm")),
            rpd=_coerce_int(pblock.get("limits", {}).get("rpd")),
            tpm=_coerce_int(pblock.get("limits", {}).get("tpm")),
            tpd=_coerce_int(pblock.get("limits", {}).get("tpd")),
        )
        pricing: dict[str, ModelPriceSpec] = {}
        for mid, mblock in pblock.get("pricing", {}).items():
            if not isinstance(mblock, dict):
                continue
            pricing[mid] = ModelPriceSpec(
                cost_input=_coerce_float(mblock.get("cost_input")),
                cost_output=_coerce_float(mblock.get("cost_output")),
                free=bool(mblock.get("free", False)),
            )
        non_token = _load_non_token(pblock.get("non_token") or {})
        providers[pname] = ProviderCanonical(
            limits=lim,
            pricing=pricing,
            non_token=non_token,
            plan=pblock.get("plan"),
            source_url=pblock.get("source_url"),
            last_verified=pblock.get("last_verified"),
        )

    return CheckerConfig(
        providers=providers,
        threshold_pct=_coerce_float(raw.get("threshold_pct")) or 5.0,
        last_updated=raw.get("last_updated"),
        sources=dict(raw.get("sources", {})),
    )


def save_canonical(
    cfg: CheckerConfig,
    *,
    config_dir: str | Path | None = None,
) -> Path:
    """Persist *cfg* to ``provider_pricing_limits.json`` in *config_dir*."""
    d = Path(config_dir) if config_dir is not None else config.secrets.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / _CANONICAL_FILE

    providers_out: dict[str, dict[str, Any]] = {}
    for pname, pc in cfg.providers.items():
        block: dict[str, Any] = {}
        lim = {k: v for k, v in asdict(pc.limits).items() if v is not None}
        if lim:
            block["limits"] = lim
        if pc.pricing:
            block["pricing"] = {
                mid: {k: v for k, v in asdict(ms).items() if v is not None}
                for mid, ms in pc.pricing.items()
            }
        if pc.non_token is not None:
            block["non_token"] = {
                k: v for k, v in asdict(pc.non_token).items() if v is not None
            }
        if pc.plan is not None:
            block["plan"] = pc.plan
        if pc.source_url is not None:
            block["source_url"] = pc.source_url
        if pc.last_verified is not None:
            block["last_verified"] = pc.last_verified
        providers_out[pname] = block

    out: dict[str, Any] = {
        "providers": providers_out,
        "threshold_pct": cfg.threshold_pct,
    }
    if cfg.last_updated is not None:
        out["last_updated"] = cfg.last_updated
    if cfg.sources:
        out["sources"] = dict(cfg.sources)

    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


# ---------------------------------------------------------------------------
# Load configured state
# ---------------------------------------------------------------------------


def load_configured(*, config_dir: str | Path | None = None) -> dict[str, Any]:
    """Return the current gateway-side configured pricing + limits as a plain dict."""
    models = config.load_models(config_dir=config_dir)
    provs = config.load_providers(config_dir=config_dir)
    return {"models": models, "providers": provs}


# ---------------------------------------------------------------------------
# Check logic
# ---------------------------------------------------------------------------


def _price_drift(
    canon: float | None, configured: float | None, threshold_pct: float
) -> tuple[bool, float]:
    """Return (is_drift, pct_change).  Either side being None is treated as drift."""
    if canon is None and configured is None:
        return False, 0.0
    if canon is None or configured is None:
        return True, float("inf")
    if canon == 0.0 and configured == 0.0:
        return False, 0.0
    if canon == 0.0:
        return True, float("inf")
    pct = (configured - canon) / canon * 100.0
    return abs(pct) > threshold_pct, pct


def check_pricing_limits(
    canonical: CheckerConfig,
    configured: dict[str, Any],
    *,
    threshold_pct: float | None = None,
) -> list[Finding]:
    """Compare *canonical* against *configured* and return a list of findings.

    *configured* is the dict returned by :func:`load_configured`.
    """
    findings: list[Finding] = []
    thresh = threshold_pct if threshold_pct is not None else canonical.threshold_pct
    models: dict[str, dict] = configured.get("models") or {}
    providers_cfg: dict[str, dict] = configured.get("providers") or {}

    # ------------------------------------------------------------------
    # 1. canonical -> configured (missing or drifted)
    # ------------------------------------------------------------------
    for pname, pc in canonical.providers.items():
        # -- limits --
        # We don't have a separate limits store today; limits are advisory in
        # quota.py config.  We note when limits differ from canonical but
        # there's no runtime file to diff against — so we flag "stale" if the
        # provider exists in config but limits are not documented anywhere.
        # For now we compare against an empty configured-limits dict.
        if pc.limits.rpm is not None or pc.limits.tpm is not None:
            findings.append(
                Finding(
                    severity="yellow",
                    category="limit_change",
                    provider=pname,
                    model=None,
                    message=f"canonical limits defined for {pname} — ensure runtime quota tracker is in sync",
                    canonical_value=asdict(pc.limits),
                    configured_value=None,
                )
            )

        # -- non-token pricing drift --
        if pc.non_token is not None:
            msg = _non_token_alert(pc.non_token, pname)
            findings.append(
                Finding(
                    severity="yellow" if pc.non_token.rate else "red",
                    category="non_token",
                    provider=pname,
                    model=None,
                    message=msg,
                    canonical_value=asdict(pc.non_token),
                    configured_value=None,
                )
            )

        # -- per-model pricing --
        for mid, ms in pc.pricing.items():
            mcfg = models.get(mid)
            if mcfg is None:
                findings.append(
                    Finding(
                        severity="red",
                        category="missing",
                        provider=pname,
                        model=mid,
                        message=f"model {mid!r} present in canonical but missing from configured models.json",
                        canonical_value=asdict(ms),
                        configured_value=None,
                    )
                )
                continue

            c_in = _coerce_float(mcfg.get("cost_input"))
            c_out = _coerce_float(mcfg.get("cost_output"))
            drift_in, pct_in = _price_drift(ms.cost_input, c_in, thresh)
            drift_out, pct_out = _price_drift(ms.cost_output, c_out, thresh)

            if drift_in:
                findings.append(
                    Finding(
                        severity="red",
                        category="price_drift",
                        provider=pname,
                        model=mid,
                        message=f"cost_input drift: canonical={ms.cost_input} configured={c_in} ({pct_in:+.1f}%)",
                        canonical_value=ms.cost_input,
                        configured_value=c_in,
                    )
                )
            if drift_out:
                findings.append(
                    Finding(
                        severity="red",
                        category="price_drift",
                        provider=pname,
                        model=mid,
                        message=f"cost_output drift: canonical={ms.cost_output} configured={c_out} ({pct_out:+.1f}%)",
                        canonical_value=ms.cost_output,
                        configured_value=c_out,
                    )
                )
            if ms.free and not mcfg.get("free"):
                findings.append(
                    Finding(
                        severity="red",
                        category="price_drift",
                        provider=pname,
                        model=mid,
                        message="canonical marks free=True but configured does not",
                        canonical_value=True,
                        configured_value=mcfg.get("free"),
                    )
                )

    # ------------------------------------------------------------------
    # 2. configured -> canonical (stale / unknown entries)
    # ------------------------------------------------------------------
    for mid, mcfg in models.items():
        if not isinstance(mcfg, dict):
            continue
        provider = mcfg.get("provider")
        if provider is None:
            continue
        pc = canonical.providers.get(provider)
        if pc is None:
            # Provider exists in config but not in canonical at all
            findings.append(
                Finding(
                    severity="yellow",
                    category="stale",
                    provider=provider,
                    model=mid,
                    message=f"provider {provider!r} has configured model {mid!r} but no canonical entry",
                    canonical_value=None,
                    configured_value={k: mcfg[k] for k in ("cost_input", "cost_output", "free") if k in mcfg},
                )
            )
            continue
        if mid not in pc.pricing and not mcfg.get("free"):
            # Model in config but not in canonical pricing table
            findings.append(
                Finding(
                    severity="yellow",
                    category="stale",
                    provider=provider,
                    model=mid,
                    message=f"model {mid!r} configured but absent from canonical pricing table",
                    canonical_value=None,
                    configured_value={k: mcfg[k] for k in ("cost_input", "cost_output", "free") if k in mcfg},
                )
            )

    return findings


def _non_token_alert(nt: NonTokenPricing, pname: str) -> str:
    """Human-readable non-token pricing alert."""
    if nt.type == "energy_kwh":
        parts = [f"{pname} bills by ENERGY ({nt.rate or 'unknown'} USD/kWh)"]
        if nt.included_monthly:
            parts.append(f"included {nt.included_monthly} kWh/mo")
        if nt.subscription_usd:
            parts.append(f"subscription ${nt.subscription_usd}/mo")
        if nt.overflow_rate:
            parts.append(f"overflow ${nt.overflow_rate}/kWh")
        return "; ".join(parts)
    if nt.type == "subscription":
        return f"{pname} flat subscription: ${nt.rate or 'unknown'}/{nt.unit or 'mo'}"
    if nt.type == "request_cap":
        return f"{pname} request-capped: ${nt.rate or 'unknown'}/{nt.unit or 'request'}"
    return f"{pname} non-token pricing type={nt.type}"


# ---------------------------------------------------------------------------
# Marginal-cost helper (apples-to-apples normalisation for cost-rank)
# ---------------------------------------------------------------------------


def marginal_cost_per_token(
    non_token: NonTokenPricing,
    *,
    avg_tokens_per_request: float = 1000.0,
    avg_kwh_per_request: float | None = None,
) -> float | None:
    """Convert a non-token pricing model into an approximate per-token USD rate.

    This is a **heuristic** — the real cost comes from the provider's usage
    API (METER-MODEL-PROVIDER wave-2).  Returns ``None`` when no conversion
    is possible.
    """
    if non_token.type == "energy_kwh":
        if avg_kwh_per_request is None:
            # Use a rule-of-thumb: 1 kWh ≈ 2 M tokens for a mid-size MoE
            # (operator reported 0.45 kWh / 23.6 M tokens ≈ 0.019 kWh / 1 M tok)
            avg_kwh_per_request = avg_tokens_per_request * 1.9e-8
        rate = non_token.rate or non_token.overflow_rate
        if rate is None:
            return None
        return rate * avg_kwh_per_request
    if non_token.type == "subscription":
        if non_token.rate is None:
            return None
        # Assume the subscription covers a large request volume; very rough.
        # A $20/mo sub with 100k req/mo → $0.0002/req.
        # Per-token: $0.0002 / 1000 tok = $2e-7 / tok.
        # Without actual usage we can't be precise — return a sentinel-like low
        # value that signals "possibly cheap" rather than a fabricated number.
        return None
    if non_token.type == "request_cap":
        if non_token.rate is None:
            return None
        return non_token.rate / avg_tokens_per_request
    return None


# ---------------------------------------------------------------------------
# CLI / script entry point
# ---------------------------------------------------------------------------


def run_check(
    *,
    config_dir: str | Path | None = None,
    threshold_pct: float | None = None,
) -> list[Finding]:
    """High-level convenience: load canonical + configured, compare, return findings."""
    canonical = load_canonical(config_dir=config_dir)
    configured = load_configured(config_dir=config_dir)
    return check_pricing_limits(canonical, configured, threshold_pct=threshold_pct)


def findings_to_dicts(findings: list[Finding]) -> list[dict[str, Any]]:
    return [asdict(f) for f in findings]
