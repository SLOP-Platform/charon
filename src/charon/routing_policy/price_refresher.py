"""PRICE-REFRESHER — background sourced-price cache for model_pricing (ADR-0016 step #3).

ADOPT-NOT-BUILD (PRICING-TOOLS-EVAL.md, 2026-07-12): wraps three best-in-class
sources and writes the local ``model_pricing`` cache that
``order_pool_by_live_cost`` reads.

Writers (all COLD-START / ADVISORY / OFF-HOT-PATH):
  (a) VENDORED LiteLLM JSON — seed cache from the MIT-vendored
      ``vendor/litellm/model_prices_and_context_window.json`` snapshot on startup.
      Keyed per (provider, model_id) so the SAME model priced differently per
      provider is handled correctly (pitfall: model-level keys are wrong).
  (b) POLL OpenRouter /api/v1/models — one unauthenticated GET, hourly TTL,
      background thread only. Writes the cache; also the drift oracle for (a).
  (c) INGEST changedetection.io webhooks — Apache-2.0 JSON POST
      ``{provider, url, old, new}`` for the zero-coverage tail providers
      (nanogpt / neuralwatt / opencode-zen) as out-of-band updates.

ANTI-ROT: METER-OBSERVED per-(model, provider) cost supersedes any quoted
price the moment traffic exists. ``order_pool_by_live_cost`` overrides sourced
quotes with live metered costs via ``derived_cost_rank(..., metered_cost=...)``.
This module ONLY feeds the *quote*; the meter is the caller's concern.

FAIL-ON-REVERT contracts:
  1. Vendored-snapshot seeding → order_pool_by_live_cost orders cheapest-first
     with an EMPTY meter.
  2. Routing reads cache ONLY → forward_with_failover never triggers a network call.
  3. Non-empty meter supersedes any sourced quote (tested via mock meter data).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from charon.proxy_server import GatewayProxyServer

log = logging.getLogger("charon.price_refresher")

_OPENROUTER_API = "https://openrouter.ai/api/v1/models"
_OPENROUTER_TTL_S = 3600.0

_LITE_LLM_PROVIDER_MAP: dict[str, str] = {
    "openrouter": "openrouter",
    "together_ai": "together_ai",
    "deepseek": "deepseek",
    "anthropic": "anthropic",
    "openai": "openai",
    "azure": "azure",
    "bedrock": "bedrock",
    "bedrock_converse": "bedrock_converse",
    "google_genai": "gemini",
    "gemini": "gemini",
    "groq": "groq",
    "mistral": "mistral",
    "cohere": "cohere",
    "perplexity": "perplexity",
    "fireworks_ai": "fireworks_ai",
    "replicate": "replicate",
    "sambanova": "sambanova",
    "aws": "bedrock",
    "vertex_ai": "vertex_ai",
    "cloudflare": "cloudflare",
    "octoai": "octoai",
    "hyperbolic": "hyperbolic",
    "nvidia_nim": "nvidia_nim",
    "cerebras": "cerebras",
    "nebius": "nebius",
    "abaco": "abaco",
    "ai21": "ai21",
    "alibaba": "alibaba",
    "anyscale": "anyscale",
    "cohere_chat": "cohere",
    "databricks": "databricks",
    "friendliai": "friendliai",
    "github_copilot": "github_copilot",
    "inception": "inception",
    "jina_ai": "jina_ai",
    "llamagate": "llamagate",
    "meta_llama": "meta",
    "minimax": "minimax",
    "moonshot": "moonshot",
    "nlp_cloud": "nlp_cloud",
    "ollama": "ollama",
    "ovhcloud": "ovhcloud",
    "palm": "palm",
    "sagemaker": "sagemaker",
    "snowflake": "snowflake",
    "tavily": "tavily",
    "tencent": "tencent",
    "vllm": "vllm",
    "volcengine": "volcengine",
    "watsonx": "watsonx",
    "xai": "xai",
    "you_com": "you_com",
}


def _normalize_id(raw: str) -> str:
    from charon.proxy import _normalize_model_id
    return _normalize_model_id(raw)


def _vendor_litellm_snapshot() -> dict[tuple[str, str], dict[str, Any]]:
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        base = (
            Path(__file__).parent.parent.parent.parent
            / "vendor" / "litellm"
            / "model_prices_and_context_window.json"
        )
        with open(base) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("price_refresher: could not load vendored LiteLLM snapshot: %s", exc)
        return cache

    for model_id, entry in data.items():
        if model_id == "sample_spec" or not isinstance(entry, dict):
            continue
        litellm_prov = entry.get("litellm_provider", "")
        charon_prov = _LITE_LLM_PROVIDER_MAP.get(litellm_prov, litellm_prov)
        if not charon_prov:
            continue
        ci = entry.get("input_cost_per_token")
        co = entry.get("output_cost_per_token")
        if ci is None and co is None:
            continue
        price: dict[str, Any] = {}
        if ci is not None:
            price["cost_input"] = float(ci)
        if co is not None:
            price["cost_output"] = float(co)
        if not price:
            continue
        key = (charon_prov, _normalize_id(model_id))
        cache[key] = price
    return cache


def _parse_openrouter_pricing(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    prompt_str = raw.get("prompt", "")
    completion_str = raw.get("completion", "")
    try:
        prompt = float(prompt_str) if prompt_str else None
    except ValueError:
        prompt = None
    try:
        completion = float(completion_str) if completion_str else None
    except ValueError:
        completion = None
    if prompt is None and completion is None:
        return None
    result: dict[str, Any] = {}
    if prompt is not None:
        result["cost_input"] = prompt
    if completion is not None:
        result["cost_output"] = completion
    return result


def _poll_openrouter() -> dict[tuple[str, str], dict[str, Any]]:
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        import urllib.request
        req = urllib.request.Request(
            _OPENROUTER_API,
            headers={"Accept": "application/json", "User-Agent": "charon/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("price_refresher: OpenRouter poll failed: %s", exc)
        return cache

    models = data.get("data", [])
    for entry in models:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str):
            continue
        pricing_raw = entry.get("pricing")
        price = _parse_openrouter_pricing(pricing_raw)
        if not price:
            continue
        key = ("openrouter", _normalize_id(model_id))
        cache[key] = price
    return cache


class PriceRefresher:
    def __init__(
        self,
        *,
        openrouter_ttl_s: float = _OPENROUTER_TTL_S,
    ) -> None:
        self._model_pricing: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._server: GatewayProxyServer | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._openrouter_ttl_s = openrouter_ttl_s
        self._poll_count = 0

    @property
    def model_pricing(self) -> dict[tuple[str, str], dict[str, Any]]:
        return self._model_pricing

    def _load_vendor_snapshot(self) -> None:
        snapshot = _vendor_litellm_snapshot()
        if snapshot:
            with self._lock:
                self._model_pricing.update(snapshot)
            log.info(
                "price_refresher: seeded %d (provider, model) entries "
                "from vendored LiteLLM snapshot",
                len(snapshot),
            )

    def _poll_openrouter(self) -> None:
        self._poll_count += 1
        data = _poll_openrouter()
        if data:
            with self._lock:
                self._model_pricing.update(data)
            log.info(
                "price_refresher: OpenRouter poll wrote %d entries (total cache: %d)",
                len(data), len(self._model_pricing),
            )

    def ingest_changedetection(
        self,
        payload: dict[str, Any],
    ) -> None:
        provider = payload.get("provider")
        url = payload.get("url")
        new_price = payload.get("new")
        if not isinstance(provider, str) or not provider:
            log.warning("price_refresher: changedetection webhook missing 'provider'")
            return
        if not isinstance(new_price, dict):
            log.warning(
                "price_refresher: changedetection webhook 'new' must be a dict "
                "(got %r)", type(new_price).__name__,
            )
            return
        ci = new_price.get("input_cost_per_token") or new_price.get("cost_input")
        co = new_price.get("output_cost_per_token") or new_price.get("cost_output")
        price: dict[str, Any] = {}
        if ci is not None:
            try:
                price["cost_input"] = float(ci)
            except (TypeError, ValueError):
                pass
        if co is not None:
            try:
                price["cost_output"] = float(co)
            except (TypeError, ValueError):
                pass
        if not price:
            log.warning(
                "price_refresher: changedetection webhook for %r has no usable price fields",
                provider,
            )
            return
        model_id = "unknown"
        if isinstance(url, str):
            model_id = _normalize_id(url.split("/")[-1])
        key = (provider, model_id)
        with self._lock:
            self._model_pricing[key] = price
        log.info(
            "price_refresher: changedetection ingest for %r/%r: %s",
            provider, model_id, price,
        )

    def _bridge_to_server(self) -> None:
        if self._server is None:
            return
        srv_mp: dict[str, dict[str, Any]] = {}
        with self._lock:
            for (prov, mid), price in self._model_pricing.items():
                member_id = f"{prov}/{mid}"
                srv_mp.setdefault(member_id, dict(price))
        self._server.model_pricing = srv_mp
        self._server.observer.set_pricing(srv_mp)

    def bind(self, server: GatewayProxyServer) -> None:
        self._server = server
        self._load_vendor_snapshot()
        self._bridge_to_server()

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.is_set():
                self._poll_openrouter()
                self._bridge_to_server()
                if self._stop.wait(self._openrouter_ttl_s):
                    break

        self._thread = threading.Thread(
            target=_loop, daemon=True, name="charon-price-refresher",
        )
        self._thread.start()
        return self._thread

    def maybe_start(self) -> None:
        self.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)
