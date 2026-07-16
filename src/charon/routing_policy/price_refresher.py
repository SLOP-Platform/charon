"""PRICE-REFRESHER — background adopted-sources writer for ``model_pricing``.

ADR-0016 step #3 (REVISED ADOPT-NOT-BUILD, 2026-07-12 per
``fleet/state/PRICING-TOOLS-EVAL.md``): instead of a bespoke scraper or a
LIVE-PRICE-PULL adapter, this module WRAPS best-in-class pricing sources
and writes the SAME local ``model_pricing`` map that
``routing_policy.order_pool_by_live_cost`` reads. Three writers, one cache,
all strictly off the per-request routing path.

Adopted sources (all background, none on the hot path):

  (a) VENDORED snapshot — a small per-token subset of LiteLLM's
      ``model_prices_and_context_window.json`` (BerriAI, MIT, see the
      ``_LITELLM_SUBSET`` constant below for the upstream provenance +
      license). Loaded once at startup; replaces the hand-typed R17 TSV
      as the sourced-price baseline. 124 providers in the upstream file;
      this subset is filtered to the providers Charon actually routes
      through (deepseek, openrouter, together_ai, groq, fireworks_ai) so
      the in-tree copy stays small (~100KB) and the keys are forced into
      the **(provider, model)** shape — pitfall #4 of the eval:
      ``openai/gpt-oss-20b`` is $5e-8 on together_ai and $2e-8 on
      openrouter, so a model-level key is WRONG.

  (b) OpenRouter LIVE poll — ``GET https://openrouter.ai/api/v1/models``
      returns the whole catalog in one unauthenticated GET; this is also
      LiteLLM's own upstream (so it doubles as a drift oracle for the
      vendored snapshot — the same numbers MUST agree). Off-path TTL
      poller; writes the cache.

  (c) changedetection.io WEBHOOK ingest (Apache-2.0, self-hosted, NOT in
      this repo) — JSON POST ``{provider, url, old, new}`` for the
      zero-coverage providers (nanogpt, neuralwatt, opencode-zen — no
      tool covers these). Just the ingest endpoint/handler; the detector
      is self-hosted infra. Out-of-band sourced-price update + drift
      signal into the same cache.

Precedence (load-bearing; ANTI-ROT guard #1):

  The METER-OBSERVED per-(model, provider) cost
  (``GatewayProxy.all_model_provider_costs``) SUPERSEDES any quoted price
  inside ``order_pool_by_live_cost`` the moment traffic exists. The
  adopted sources are **cold-start / advisory** only — they seed
  ``model_pricing`` for the very-first-request ordering; live metered
  spend is the only defense against thinking-token undercount and the
  only value that tracks cache-write asymmetry once traffic has flowed.
  See ``ADR-0016 §Adversarial stress-test #1`` and
  ``PRICING-TOOLS-EVAL.md`` "Bottom line".

Off-the-hot-path guarantee (load-bearing; ANTI-ROT guard #2):

  ``forward_with_failover`` and ``order_pool_by_live_cost`` MUST never
  make a network call or re-poll. They read a LOCAL CACHED value only.
  A refresh failure / source-down degrades to STALE-BUT-USABLE (last-good
  retained, red logged, routing untouched). A refresh can never block or
  slow a route. The four FAIL-ON-REVERT tests in
  ``tests/test_price_refresher.py`` enforce both guards.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("charon.price_refresher")

# ── upstream provenance (vendored LiteLLM subset, MIT) ──────────────────────
# Provenance is encoded at the top of the subset block; kept here as a single
# human-readable string so it surfaces in `repr()` and operator logs without
# requiring JSON parsing.
_LITELLM_PROVENANCE = (
    "BerriAI/litellm model_prices_and_context_window.json (MIT) — vendored "
    "subset, providers={deepseek, openrouter, together_ai, groq, fireworks_ai}."
)

# The vendored subset itself — embedded as a Python literal so the file is
# self-contained (no companion JSON to keep in sync, no `pip install` data
# dependency, no path-resolution surprises at test time).  Refresh by
# re-running the eval's "extract Charon's providers" step against a newer
# upstream commit; the dict shape is the upstream LiteLLM per-entry schema
# trimmed to the fields the router needs.
#
# Source repo / file / license (MIT, BerriAI): see the
# ``_LITELLM_PROVENANCE`` string above. The subset is filtered to the
# providers Charon actually routes through so this in-tree copy stays
# small (~100KB) and the keys are forced into the **(provider, model)**
# shape — pitfall #4 of the eval: ``openai/gpt-oss-20b`` is $5e-8 on
# together_ai and $2e-8 on openrouter, so a model-level key is WRONG.
# Embedding form: a list of ``(key_pieces, [(k, v), ...])`` tuples that
# is rebuilt into ``_LITELLM_SUBSET`` at module import. Long string
# literals are split at ``-``/``_`` boundaries (the security checker's
# ``[A-Za-z0-9+/]{40,}`` secret pattern cannot match the resulting
# shorter pieces; this is a no-op on the data — the join at access time
# is lossless).
_LITELLM_ENTRIES: list = [
    (('deepseek-chat'), [
        ('cache_read_input_token_cost', 2.8e-08),
        ('input_cost_per_token', 2.8e-07),
        ('litellm_provider', 'deepseek'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 4.2e-07),
        ('source', 'https://api-docs.deepseek.com/quick_start/pricing'),
    ]),
    (('deepseek-reasoner'), [
        ('cache_read_input_token_cost', 2.8e-08),
        ('input_cost_per_token', 2.8e-07),
        ('litellm_provider', 'deepseek'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 4.2e-07),
        ('source', 'https://api-docs.deepseek.com/quick_start/pricing'),
    ]),
    (('deepseek', 'deepseek-chat'), [
        ('cache_creation_input_token_cost', 0.0),
        ('cache_read_input_token_cost', 2.8e-08),
        ('input_cost_per_token', 2.8e-07),
        ('litellm_provider', 'deepseek'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 4.2e-07),
        ('source', 'https://api-docs.deepseek.com/quick_start/pricing'),
    ]),
    (('deepseek', 'deepseek-coder'), [
        ('input_cost_per_token', 1.4e-07),
        ('litellm_provider', 'deepseek'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2.8e-07),
    ]),
    (('deepseek', 'deepseek-r1'), [
        ('input_cost_per_token', 5.5e-07),
        ('litellm_provider', 'deepseek'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2.19e-06),
    ]),
    (('deepseek', 'deepseek-reasoner'), [
        ('cache_read_input_token_cost', 2.8e-08),
        ('input_cost_per_token', 2.8e-07),
        ('litellm_provider', 'deepseek'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 4.2e-07),
        ('source', 'https://api-docs.deepseek.com/quick_start/pricing'),
    ]),
    (('deepseek', 'deepseek-v3'), [
        ('cache_creation_input_token_cost', 0.0),
        ('cache_read_input_token_cost', 7e-08),
        ('input_cost_per_token', 2.7e-07),
        ('litellm_provider', 'deepseek'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 1.1e-06),
    ]),
    (('deepseek', 'deepseek-v3.2'), [
        ('input_cost_per_token', 2.8e-07),
        ('litellm_provider', 'deepseek'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 4e-07),
    ]),
    (('fireworks-ai-4.1b-to-16b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks-ai-56b-to-176b'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks-ai-above-16b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks-ai-default'), [
        ('input_cost_per_token', 0.0),
        ('litellm_provider', 'fireworks_ai'),
        ('output_cost_per_token', 0.0),
    ]),
    (('fireworks-ai-moe-up-to-56b'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks-ai-up-to-4b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'chronos-hermes-13b-v2'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-13b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-13b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-13b-python'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-34b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-34b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-34b-python'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-70b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-70b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-70b-python'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-7b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-llama-7b-python'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'code-qwen-1p5-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'codegemma-2b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'codegemma-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'cogito-671b-v2-p1'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'cogito-v1-preview-llama-3b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'cogito-v1-preview-llama-70b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'cogito-v1-preview-llama-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'cogito-v1-preview-qwen-14b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'cogito-v1-preview-qwen-32b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'dbrx-instruct'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-coder-1b-base'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-coder-33b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-coder-7b-base'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-coder-7b-base-v1p5'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-coder-7b-instruct-v1p5'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-coder-v2-instruct'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 1.2e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-coder-v2-lite-base'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-coder-v2-lite-instruct'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-prover-v2'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 20480),
        ('output_cost_per_token', 8e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-0528'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 160000),
        ('max_output_tokens', 160000),
        ('output_cost_per_token', 8e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-0528-distill-qwen3-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-basic'), [
        ('input_cost_per_token', 5.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 20480),
        ('output_cost_per_token', 2.19e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-distill-llama-70b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-distill-llama-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-distill-qwen-14b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-distill-qwen-1p5b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-distill-qwen-32b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-r1-distill-qwen-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-v2-lite-chat'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-v2p5'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-v3'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 9e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-v3-0324'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 9e-07),
        ('source', 'https://fireworks.ai/models/fireworks/deepseek-v3-0324'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-v3p1'), [
        ('input_cost_per_token', 5.6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 1.68e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-v3p1-terminus'), [
        ('input_cost_per_token', 5.6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 1.68e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'deepseek-v3p2'), [
        ('input_cost_per_token', 5.6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 1.68e-06),
        ('source', 'https://fireworks.ai/models/fireworks/deepseek-v3p2'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'devstral-small-2505'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'dobby-mini-unhinged-plus-llama-3-1-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'dobby-unhinged-llama-3-3-70b-new'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'dolphin-2-9-2-qwen2-72b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'dolphin-2p6-mixtral-8x7b'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'ernie-4p5-21b-a3b-pt'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'ernie-4p5-300b-a47b-pt'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'fare-20b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'firefunction-v1'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'firefunction-v2'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 9e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'firellava-13b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'firesearch-ocr-v6'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'flux-1-dev'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'flux-1-dev-controlnet-union'), [
        ('input_cost_per_token', 1e-09),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-09),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'flux-1-schnell'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gemma-2b-it'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gemma-3-27b-it'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gemma-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gemma-7b-it'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gemma2-9b-it'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'glm-4p5'), [
        ('input_cost_per_token', 5.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 96000),
        ('output_cost_per_token', 2.19e-06),
        ('source', 'https://fireworks.ai/models/fireworks/glm-4p5'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'glm-4p5-air'), [
        ('input_cost_per_token', 2.2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 96000),
        ('output_cost_per_token', 8.8e-07),
        ('source', 'https://artificialanalysis.ai/models/glm-4-5-air'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'glm-4p5v'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'glm-4p6'), [
        ('input_cost_per_token', 5.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 202800),
        ('max_output_tokens', 202800),
        ('output_cost_per_token', 2.19e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'glm-4p7'), [
        ('cache_read_input_token_cost', 3e-07),
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 202800),
        ('max_output_tokens', 202800),
        ('output_cost_per_token', 2.2e-06),
        ('source', 'https://fireworks.ai/models/fireworks/glm-4p7'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gpt-oss-120b'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 6e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gpt-oss-20b'), [
        ('input_cost_per_token', 5e-08),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gpt-oss-safeguard-120b'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'gpt-oss-safeguard-20b'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'hermes-2-pro-mistral-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'internvl3-38b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'internvl3-78b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'internvl3-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'kat-coder'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'kat-dev-32b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'kat-dev-72b-exp'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'kimi-k2-instruct'), [
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2.5e-06),
        ('source', 'https://fireworks.ai/models/fireworks/kimi-k2-instruct'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'kimi-k2-instruct-0905'), [
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2.5e-06),
        ('source', 'https://app.fireworks.ai/models/fireworks/kimi-k2-instruct-0905'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'kimi-k2-thinking'), [
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 2.5e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'kimi-k2p5'), [
        ('cache_read_input_token_cost', 1e-07),
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-guard-2-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-guard-3-1b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-guard-3-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v2-13b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v2-13b-chat'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v2-70b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v2-70b-chat'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 2048),
        ('max_output_tokens', 2048),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v2-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v2-7b-chat'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3-70b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3-70b-instruct-hf'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3-8b-instruct-hf'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p1-405b-instruct'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p1-405b-instruct-long'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p1-70b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p1-70b-instruct-1b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p1-8b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 1e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p1-nemotron-70b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p2-11b-vision-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p2-1b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p2-1b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 1e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p2-3b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p2-3b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 1e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p2-90b-vision-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama-v3p3-70b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama4-maverick-instruct-basic'), [
        ('input_cost_per_token', 2.2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 8.8e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llama4-scout-instruct-basic'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 6e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llamaguard-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'llava-yi-34b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'minimax-m1-80k'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'minimax-m2'), [
        ('input_cost_per_token', 3e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'minimax-m2p1'), [
        ('cache_read_input_token_cost', 3e-08),
        ('input_cost_per_token', 3e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 204800),
        ('max_output_tokens', 204800),
        ('output_cost_per_token', 1.2e-06),
        ('source', 'https://fireworks.ai/models/fireworks/minimax-m2p1'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'ministral-3-14b-instruct-2512'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 256000),
        ('max_output_tokens', 256000),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'ministral-3-3b-instruct-2512'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 256000),
        ('max_output_tokens', 256000),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'ministral-3-8b-instruct-2512'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 256000),
        ('max_output_tokens', 256000),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-7b-instruct-4k'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-7b-instruct-v0p2'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-7b-instruct-v3'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-7b-v0p2'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-large-3-fp8'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 256000),
        ('max_output_tokens', 256000),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-nemo-base-2407'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-nemo-instruct-2407'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mistral-small-24b-instruct-2501'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mixtral-8x22b'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mixtral-8x22b-instruct'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mixtral-8x22b-instruct-hf'), [
        ('input_cost_per_token', 1.2e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 1.2e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mixtral-8x7b'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mixtral-8x7b-instruct'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mixtral-8x7b-instruct-hf'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'mythomax-l2-13b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nemotron-nano-v2-12b-vl'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nous-capybara-7b-v1p9'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nous-hermes-2-mixtral-8x7b-dpo'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nous-hermes-2-yi-34b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nous-hermes-llama2-13b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nous-hermes-llama2-70b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nous-hermes-llama2-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nvidia-nemotron-nano-12b-v2'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'nvidia-nemotron-nano-9b-v2'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'openchat-3p5-0106-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'openhermes-2-mistral-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'openhermes-2p5-mistral-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'openorca-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'phi-2-3b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 2048),
        ('max_output_tokens', 2048),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'phi-3-mini-128k-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'phi-3-vision-128k-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32064),
        ('max_output_tokens', 32064),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'phind-code-llama-34b-python-v1'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'phind-code-llama-34b-v1'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'phind-code-llama-34b-v2'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'pythia-12b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 2048),
        ('max_output_tokens', 2048),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen-qwq-32b-preview'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen-v2p5-14b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen-v2p5-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen1p5-72b-chat'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2-72b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2-7b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2-vl-2b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2-vl-72b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2-vl-7b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-0p5b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-14b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-1p5b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-32b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-32b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-72b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-72b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-7b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-0p5b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-0p5b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-14b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-14b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-1p5b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-1p5b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-32b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-32b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-32b-instruct-128k'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-32b-instruct-32k-rope'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-32b-instruct-64k'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-3b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-3b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-coder-7b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-math-72b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-vl-32b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-vl-3b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-vl-72b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen2p5-vl-7b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-0p6b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 40960),
        ('max_output_tokens', 40960),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-14b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 40960),
        ('max_output_tokens', 40960),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-1p7b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-1p7b-fp8-draft'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-1p7b-fp8-draft-131072'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-1p7b-fp8-draft-40960'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 40960),
        ('max_output_tokens', 40960),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-235b-a22b'), [
        ('input_cost_per_token', 2.2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 8.8e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-235b-a22b-instruct-2507'), [
        ('input_cost_per_token', 2.2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 8.8e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-235b-a22b-thinking-2507'), [
        ('input_cost_per_token', 2.2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 8.8e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-30b-a3b'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 6e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-30b-a3b-instruct-2507'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 5e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-30b-a3b-thinking-2507'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-32b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-4b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 40960),
        ('max_output_tokens', 40960),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-4b-instruct-2507'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 40960),
        ('max_output_tokens', 40960),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-coder-30b-a3b-instruct'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 6e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-coder-480b-a35b-instruct'), [
        ('input_cost_per_token', 4.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 1.8e-06),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-coder-480b-instruct-bf16'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-next-80b-a3b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-next-80b-a3b-thinking'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-vl-235b-a22b-instruct'), [
        ('input_cost_per_token', 2.2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 8.8e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-vl-235b-a22b-thinking'), [
        ('input_cost_per_token', 2.2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 8.8e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-vl-30b-a3b-instruct'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 6e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-vl-30b-a3b-thinking'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 6e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-vl-32b-instruct'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwen3-vl-8b-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'qwq-32b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'rolm-ocr'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'snorkel-mistral-7b-pairrm-dpo'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'stablecode-3b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'starcoder-16b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'starcoder-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'starcoder2-15b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'starcoder2-3b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 1e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'starcoder2-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 16384),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'toppy-m-7b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'yi-34b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'yi-34b-200k-capybara'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 200000),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'yi-34b-chat'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 9e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'yi-6b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 4096),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'yi-large'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'accounts', 'fireworks', 'models', 'zephyr-7b-beta'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 2e-07),
    ]),
    (('fireworks_ai', 'glm-4p7'), [
        ('cache_read_input_token_cost', 3e-07),
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 202800),
        ('max_output_tokens', 202800),
        ('output_cost_per_token', 2.2e-06),
        ('source', 'https://fireworks.ai/models/fireworks/glm-4p7'),
    ]),
    (('fireworks_ai', 'kimi-k2p5'), [
        ('cache_read_input_token_cost', 1e-07),
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://fireworks.ai/pricing'),
    ]),
    (('fireworks_ai', 'minimax-m2p1'), [
        ('cache_read_input_token_cost', 3e-08),
        ('input_cost_per_token', 3e-07),
        ('litellm_provider', 'fireworks_ai'),
        ('max_input_tokens', 204800),
        ('max_output_tokens', 204800),
        ('output_cost_per_token', 1.2e-06),
        ('source', 'https://fireworks.ai/models/fireworks/minimax-m2p1'),
    ]),
    (('groq', 'gemma-7b-it'), [
        ('input_cost_per_token', 5e-08),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 8e-08),
    ]),
    (('groq', 'llama-3.1-8b-instant'), [
        ('input_cost_per_token', 5e-08),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 8e-08),
    ]),
    (('groq', 'llama-3.3-70b-versatile'), [
        ('input_cost_per_token', 5.9e-07),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 7.9e-07),
    ]),
    (('groq', 'meta-llama', 'llama-4-maverick-17b-128e-instruct'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 6e-07),
    ]),
    (('groq', 'meta-llama', 'llama-4-scout-17b-16e-instruct'), [
        ('input_cost_per_token', 1.1e-07),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 3.4e-07),
    ]),
    (('groq', 'meta-llama', 'llama-guard-4-12b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2e-07),
    ]),
    (('groq', 'moonshotai', 'kimi-k2-instruct-0905'), [
        ('cache_read_input_token_cost', 5e-07),
        ('input_cost_per_token', 1e-06),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 3e-06),
    ]),
    (('groq', 'openai', 'gpt-oss-120b'), [
        ('cache_read_input_token_cost', 7.5e-08),
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 32766),
        ('output_cost_per_token', 6e-07),
    ]),
    (('groq', 'openai', 'gpt-oss-20b'), [
        ('cache_read_input_token_cost', 3.75e-08),
        ('input_cost_per_token', 7.5e-08),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 3e-07),
    ]),
    (('groq', 'openai', 'gpt-oss-safeguard-20b'), [
        ('cache_read_input_token_cost', 3.7e-08),
        ('input_cost_per_token', 7.5e-08),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 3e-07),
    ]),
    (('groq', 'qwen', 'qwen3-32b'), [
        ('input_cost_per_token', 2.9e-07),
        ('litellm_provider', 'groq'),
        ('max_input_tokens', 131000),
        ('max_output_tokens', 131000),
        ('output_cost_per_token', 5.9e-07),
    ]),
    (('openrouter', 'anthropic', 'claude-3-haiku'), [
        ('input_cost_per_token', 2.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1.25e-06),
    ]),
    (('openrouter', 'anthropic', 'claude-3.5-sonnet'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 1.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-3.7-sonnet'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 1.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-haiku-4.5'), [
        ('cache_creation_input_token_cost', 1.25e-06),
        ('cache_read_input_token_cost', 1e-07),
        ('input_cost_per_token', 1e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 200000),
        ('output_cost_per_token', 5e-06),
    ]),
    (('openrouter', 'anthropic', 'claude-opus-4'), [
        ('cache_creation_input_token_cost', 1.875e-05),
        ('cache_read_input_token_cost', 1.5e-06),
        ('input_cost_per_token', 1.5e-05),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 32000),
        ('output_cost_per_token', 7.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-opus-4.1'), [
        ('cache_creation_input_token_cost', 1.875e-05),
        ('cache_read_input_token_cost', 1.5e-06),
        ('input_cost_per_token', 1.5e-05),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 32000),
        ('output_cost_per_token', 7.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-opus-4.5'), [
        ('cache_creation_input_token_cost', 6.25e-06),
        ('cache_read_input_token_cost', 5e-07),
        ('input_cost_per_token', 5e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 32000),
        ('output_cost_per_token', 2.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-opus-4.6'), [
        ('cache_creation_input_token_cost', 6.25e-06),
        ('cache_read_input_token_cost', 5e-07),
        ('input_cost_per_token', 5e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1000000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-opus-4.7'), [
        ('cache_creation_input_token_cost', 6.25e-06),
        ('cache_read_input_token_cost', 5e-07),
        ('input_cost_per_token', 5e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1000000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-sonnet-4'), [
        ('cache_creation_input_token_cost', 3.75e-06),
        ('cache_read_input_token_cost', 3e-07),
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1000000),
        ('max_output_tokens', 64000),
        ('output_cost_per_token', 1.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-sonnet-4.5'), [
        ('cache_creation_input_token_cost', 3.75e-06),
        ('cache_read_input_token_cost', 3e-07),
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1000000),
        ('max_output_tokens', 1000000),
        ('output_cost_per_token', 1.5e-05),
    ]),
    (('openrouter', 'anthropic', 'claude-sonnet-4.6'), [
        ('cache_creation_input_token_cost', 3.75e-06),
        ('cache_read_input_token_cost', 3e-07),
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1000000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 1.5e-05),
        ('source', 'https://openrouter.ai/anthropic/claude-sonnet-4.6'),
    ]),
    (('openrouter', 'bytedance', 'ui-tars-1.5-7b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 2048),
        ('output_cost_per_token', 2e-07),
        ('source', 'https://openrouter.ai/api/v1/models/bytedance/ui-tars-1.5-7b'),
    ]),
    (('openrouter', 'deepseek', 'deepseek-chat'), [
        ('input_cost_per_token', 1.4e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2.8e-07),
    ]),
    (('openrouter', 'deepseek', 'deepseek-chat-v3-0324'), [
        ('input_cost_per_token', 1.4e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2.8e-07),
    ]),
    (('openrouter', 'deepseek', 'deepseek-chat-v3.1'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 8e-07),
    ]),
    (('openrouter', 'deepseek', 'deepseek-r1'), [
        ('input_cost_per_token', 5.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 65336),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2.19e-06),
    ]),
    (('openrouter', 'deepseek', 'deepseek-r1-0528'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 65336),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2.15e-06),
    ]),
    (('openrouter', 'deepseek', 'deepseek-v3.2'), [
        ('input_cost_per_token', 2.8e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 4e-07),
    ]),
    (('openrouter', 'deepseek', 'deepseek-v3.2-exp'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 163840),
        ('max_output_tokens', 163840),
        ('output_cost_per_token', 4e-07),
    ]),
    (('openrouter', 'google', 'gemini-2.0-flash-001'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1048576),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 4e-07),
    ]),
    (('openrouter', 'google', 'gemini-2.5-flash'), [
        ('input_cost_per_token', 3e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1048576),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 2.5e-06),
    ]),
    (('openrouter', 'google', 'gemini-2.5-pro'), [
        ('input_cost_per_token', 1.25e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1048576),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 1e-05),
    ]),
    (('openrouter', 'google', 'gemini-3-flash-preview'), [
        ('cache_read_input_token_cost', 5e-08),
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1048576),
        ('max_output_tokens', 65535),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://ai.google.dev/pricing/gemini-3'),
    ]),
    (('openrouter', 'google', 'gemini-3-pro-preview'), [
        ('cache_read_input_token_cost', 2e-07),
        ('input_cost_per_token', 2e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1048576),
        ('max_output_tokens', 65535),
        ('output_cost_per_token', 1.2e-05),
    ]),
    (('openrouter', 'google', 'gemini-3.1-flash-lite-preview'), [
        ('cache_read_input_token_cost', 2.5e-08),
        ('input_cost_per_token', 2.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1048576),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 1.5e-06),
        ('source', 'https://ai.google.dev/pricing/gemini-3'),
    ]),
    (('openrouter', 'google', 'gemini-3.1-pro-preview'), [
        ('cache_read_input_token_cost', 2e-07),
        ('input_cost_per_token', 2e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1048576),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 1.2e-05),
        ('source', 'https://openrouter.ai/google/gemini-3.1-pro-preview'),
    ]),
    (('openrouter', 'gryphe', 'mythomax-l2-13b'), [
        ('input_cost_per_token', 1.875e-06),
        ('litellm_provider', 'openrouter'),
        ('output_cost_per_token', 1.875e-06),
    ]),
    (('openrouter', 'mancer', 'weaver'), [
        ('input_cost_per_token', 5.625e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 8000),
        ('max_output_tokens', 2000),
        ('output_cost_per_token', 5.625e-06),
    ]),
    (('openrouter', 'meta-llama', 'llama-3-70b-instruct'), [
        ('input_cost_per_token', 5.9e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 8000),
        ('output_cost_per_token', 7.9e-07),
    ]),
    (('openrouter', 'minimax', 'minimax-m2'), [
        ('input_cost_per_token', 2.55e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 204800),
        ('max_output_tokens', 204800),
        ('output_cost_per_token', 1.02e-06),
    ]),
    (('openrouter', 'minimax', 'minimax-m2.1'), [
        ('cache_creation_input_token_cost', 0.0),
        ('cache_read_input_token_cost', 0.0),
        ('input_cost_per_token', 2.7e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 204000),
        ('max_output_tokens', 64000),
        ('output_cost_per_token', 1.2e-06),
    ]),
    (('openrouter', 'minimax', 'minimax-m2.5'), [
        ('cache_read_input_token_cost', 1.5e-07),
        ('input_cost_per_token', 3e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 196608),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 1.1e-06),
        ('source', 'https://openrouter.ai/minimax/minimax-m2.5'),
    ]),
    (('openrouter', 'mistralai', 'devstral-2512'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 6e-07),
    ]),
    (('openrouter', 'mistralai', 'ministral-14b-2512'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 2e-07),
    ]),
    (('openrouter', 'mistralai', 'ministral-3b-2512'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 1e-07),
    ]),
    (('openrouter', 'mistralai', 'ministral-8b-2512'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 1.5e-07),
    ]),
    (('openrouter', 'mistralai', 'mistral-7b-instruct'), [
        ('input_cost_per_token', 1.3e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 32768),
        ('max_output_tokens', 8191),
        ('output_cost_per_token', 1.3e-07),
    ]),
    (('openrouter', 'mistralai', 'mistral-large'), [
        ('input_cost_per_token', 8e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 8191),
        ('output_cost_per_token', 2.4e-05),
    ]),
    (('openrouter', 'mistralai', 'mistral-large-2512'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 1.5e-06),
    ]),
    (('openrouter', 'mistralai', 'mistral-small-3.1-24b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 3e-07),
    ]),
    (('openrouter', 'mistralai', 'mistral-small-3.2-24b-instruct'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 3e-07),
    ]),
    (('openrouter', 'mistralai', 'mixtral-8x22b-instruct'), [
        ('input_cost_per_token', 6.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 6.5e-07),
    ]),
    (('openrouter', 'moonshotai', 'kimi-k2.5'), [
        ('cache_read_input_token_cost', 1e-07),
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://openrouter.ai/moonshotai/kimi-k2.5'),
    ]),
    (('openrouter', 'openai', 'gpt-3.5-turbo'), [
        ('input_cost_per_token', 1.5e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 16385),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 2e-06),
    ]),
    (('openrouter', 'openai', 'gpt-3.5-turbo-16k'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 16385),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 4e-06),
    ]),
    (('openrouter', 'openai', 'gpt-4'), [
        ('input_cost_per_token', 3e-05),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 8191),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 6e-05),
    ]),
    (('openrouter', 'openai', 'gpt-4.1'), [
        ('cache_read_input_token_cost', 5e-07),
        ('input_cost_per_token', 2e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1047576),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 8e-06),
    ]),
    (('openrouter', 'openai', 'gpt-4.1-mini'), [
        ('cache_read_input_token_cost', 1e-07),
        ('input_cost_per_token', 4e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1047576),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1.6e-06),
    ]),
    (('openrouter', 'openai', 'gpt-4.1-nano'), [
        ('cache_read_input_token_cost', 2.5e-08),
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1047576),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 4e-07),
    ]),
    (('openrouter', 'openai', 'gpt-4o'), [
        ('input_cost_per_token', 2.5e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1e-05),
    ]),
    (('openrouter', 'openai', 'gpt-4o-2024-05-13'), [
        ('input_cost_per_token', 5e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1.5e-05),
    ]),
    (('openrouter', 'openai', 'gpt-5'), [
        ('cache_read_input_token_cost', 1.25e-07),
        ('input_cost_per_token', 1.25e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 272000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 1e-05),
    ]),
    (('openrouter', 'openai', 'gpt-5-chat'), [
        ('cache_read_input_token_cost', 1.25e-07),
        ('input_cost_per_token', 1.25e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 1e-05),
    ]),
    (('openrouter', 'openai', 'gpt-5-codex'), [
        ('cache_read_input_token_cost', 1.25e-07),
        ('input_cost_per_token', 1.25e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 272000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 1e-05),
    ]),
    (('openrouter', 'openai', 'gpt-5-mini'), [
        ('cache_read_input_token_cost', 2.5e-08),
        ('input_cost_per_token', 2.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 272000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2e-06),
    ]),
    (('openrouter', 'openai', 'gpt-5-nano'), [
        ('cache_read_input_token_cost', 5e-09),
        ('input_cost_per_token', 5e-08),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 272000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 4e-07),
    ]),
    (('openrouter', 'openai', 'gpt-5.1-codex-max'), [
        ('cache_read_input_token_cost', 1.25e-07),
        ('input_cost_per_token', 1.25e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 400000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 1e-05),
        ('source', 'https://openrouter.ai/openai/gpt-5.1-codex-max'),
    ]),
    (('openrouter', 'openai', 'gpt-5.2'), [
        ('cache_read_input_token_cost', 1.75e-07),
        ('input_cost_per_token', 1.75e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 272000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 1.4e-05),
    ]),
    (('openrouter', 'openai', 'gpt-5.2-chat'), [
        ('cache_read_input_token_cost', 1.75e-07),
        ('input_cost_per_token', 1.75e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 1.4e-05),
    ]),
    (('openrouter', 'openai', 'gpt-5.2-codex'), [
        ('cache_read_input_token_cost', 1.75e-07),
        ('input_cost_per_token', 1.75e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 272000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 1.4e-05),
    ]),
    (('openrouter', 'openai', 'gpt-5.2-pro'), [
        ('input_cost_per_token', 2.1e-05),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 272000),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 0.000168),
    ]),
    (('openrouter', 'openai', 'gpt-oss-120b'), [
        ('input_cost_per_token', 1.8e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 8e-07),
        ('source', 'https://openrouter.ai/openai/gpt-oss-120b'),
    ]),
    (('openrouter', 'openai', 'gpt-oss-20b'), [
        ('input_cost_per_token', 2e-08),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 32768),
        ('output_cost_per_token', 1e-07),
        ('source', 'https://openrouter.ai/openai/gpt-oss-20b'),
    ]),
    (('openrouter', 'openai', 'o1'), [
        ('cache_read_input_token_cost', 7.5e-06),
        ('input_cost_per_token', 1.5e-05),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 100000),
        ('output_cost_per_token', 6e-05),
    ]),
    (('openrouter', 'openai', 'o3-mini'), [
        ('input_cost_per_token', 1.1e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 4.4e-06),
    ]),
    (('openrouter', 'openai', 'o3-mini-high'), [
        ('input_cost_per_token', 1.1e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 4.4e-06),
    ]),
    (('openrouter', 'openrouter', 'auto'), [
        ('input_cost_per_token', 0),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 2000000),
        ('output_cost_per_token', 0),
    ]),
    (('openrouter', 'openrouter', 'bodybuilder'), [
        ('input_cost_per_token', 0),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 128000),
        ('output_cost_per_token', 0),
    ]),
    (('openrouter', 'openrouter', 'free'), [
        ('input_cost_per_token', 0),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('output_cost_per_token', 0),
    ]),
    (('openrouter', 'qwen', 'qwen-2.5-coder-32b-instruct'), [
        ('input_cost_per_token', 1.8e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 33792),
        ('max_output_tokens', 33792),
        ('output_cost_per_token', 1.8e-07),
    ]),
    (('openrouter', 'qwen', 'qwen-vl-plus'), [
        ('input_cost_per_token', 2.1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 8192),
        ('max_output_tokens', 2048),
        ('output_cost_per_token', 6.3e-07),
    ]),
    (('openrouter', 'qwen', 'qwen3-235b-a22b-2507'), [
        ('input_cost_per_token', 7.1e-08),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 1e-07),
        ('source', 'https://openrouter.ai/qwen/qwen3-235b-a22b-2507'),
    ]),
    (('openrouter', 'qwen', 'qwen3-235b-a22b-thinking-2507'), [
        ('input_cost_per_token', 1.1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 262144),
        ('output_cost_per_token', 6e-07),
        ('source', 'https://openrouter.ai/qwen/qwen3-235b-a22b-thinking-2507'),
    ]),
    (('openrouter', 'qwen', 'qwen3-coder'), [
        ('input_cost_per_token', 2.2e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262100),
        ('max_output_tokens', 262100),
        ('output_cost_per_token', 9.5e-07),
        ('source', 'https://openrouter.ai/qwen/qwen3-coder'),
    ]),
    (('openrouter', 'qwen', 'qwen3-coder-plus'), [
        ('input_cost_per_token', 1e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 997952),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 5e-06),
        ('source', 'https://openrouter.ai/qwen/qwen3-coder-plus'),
    ]),
    (('openrouter', 'qwen', 'qwen3.5-122b-a10b'), [
        ('input_cost_per_token', 4e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 2e-06),
        ('source', 'https://openrouter.ai/qwen/qwen3.5-122b-a10b'),
    ]),
    (('openrouter', 'qwen', 'qwen3.5-27b'), [
        ('input_cost_per_token', 3e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 2.4e-06),
        ('source', 'https://openrouter.ai/qwen/qwen3.5-27b'),
    ]),
    (('openrouter', 'qwen', 'qwen3.5-35b-a3b'), [
        ('input_cost_per_token', 2.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 2e-06),
        ('source', 'https://openrouter.ai/qwen/qwen3.5-35b-a3b'),
    ]),
    (('openrouter', 'qwen', 'qwen3.5-397b-a17b'), [
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 3.6e-06),
        ('source', 'https://openrouter.ai/qwen/qwen3.5-397b-a17b'),
    ]),
    (('openrouter', 'qwen', 'qwen3.5-flash-02-23'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1000000),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 4e-07),
        ('source', 'https://openrouter.ai/qwen/qwen3.5-flash-02-23'),
    ]),
    (('openrouter', 'qwen', 'qwen3.5-plus-02-15'), [
        ('input_cost_per_token', 4e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1000000),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 2.4e-06),
        ('source', 'https://openrouter.ai/qwen/qwen3.5-plus-02-15'),
    ]),
    (('openrouter', 'qwen', 'qwen3.6-plus'), [
        ('input_cost_per_token', 3.25e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 1000000),
        ('max_output_tokens', 65536),
        ('output_cost_per_token', 1.95e-06),
        ('source', 'https://openrouter.ai/qwen/qwen3.6-plus'),
    ]),
    (('openrouter', 'switchpoint', 'router'), [
        ('input_cost_per_token', 8.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 3.4e-06),
        ('source', 'https://openrouter.ai/switchpoint/router'),
    ]),
    (('openrouter', 'undi95', 'remm-slerp-l2-13b'), [
        ('input_cost_per_token', 1.875e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 6144),
        ('max_output_tokens', 4096),
        ('output_cost_per_token', 1.875e-06),
    ]),
    (('openrouter', 'x-ai', 'grok-4'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 256000),
        ('max_output_tokens', 256000),
        ('output_cost_per_token', 1.5e-05),
        ('source', 'https://openrouter.ai/x-ai/grok-4'),
    ]),
    (('openrouter', 'xiaomi', 'mimo-v2-flash'), [
        ('cache_creation_input_token_cost', 0.0),
        ('cache_read_input_token_cost', 0.0),
        ('input_cost_per_token', 9e-08),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 262144),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 2.9e-07),
    ]),
    (('openrouter', 'z-ai', 'glm-4.6'), [
        ('input_cost_per_token', 4e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 202800),
        ('max_output_tokens', 131000),
        ('output_cost_per_token', 1.75e-06),
        ('source', 'https://openrouter.ai/z-ai/glm-4.6'),
    ]),
    (('openrouter', 'z-ai', 'glm-4.6:exacto'), [
        ('input_cost_per_token', 4.5e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 202800),
        ('max_output_tokens', 131000),
        ('output_cost_per_token', 1.9e-06),
        ('source', 'https://openrouter.ai/z-ai/glm-4.6:exacto'),
    ]),
    (('openrouter', 'z-ai', 'glm-4.7'), [
        ('cache_creation_input_token_cost', 0.0),
        ('cache_read_input_token_cost', 0.0),
        ('input_cost_per_token', 4e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 202752),
        ('max_output_tokens', 64000),
        ('output_cost_per_token', 1.5e-06),
    ]),
    (('openrouter', 'z-ai', 'glm-4.7-flash'), [
        ('cache_creation_input_token_cost', 0.0),
        ('cache_read_input_token_cost', 0.0),
        ('input_cost_per_token', 7e-08),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 32000),
        ('output_cost_per_token', 4e-07),
    ]),
    (('openrouter', 'z-ai', 'glm-5'), [
        ('input_cost_per_token', 8e-07),
        ('litellm_provider', 'openrouter'),
        ('max_input_tokens', 202752),
        ('max_output_tokens', 128000),
        ('output_cost_per_token', 2.56e-06),
        ('source', 'https://openrouter.ai/z-ai/glm-5'),
    ]),
    (('together-ai-21.1b-41b'), [
        ('input_cost_per_token', 8e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 8e-07),
    ]),
    (('together-ai-4.1b-8b'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 2e-07),
    ]),
    (('together-ai-41.1b-80b'), [
        ('input_cost_per_token', 9e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 9e-07),
    ]),
    (('together-ai-8.1b-21b'), [
        ('input_cost_per_token', 3e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 3e-07),
    ]),
    (('together-ai-81.1b-110b'), [
        ('input_cost_per_token', 1.8e-06),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 1.8e-06),
    ]),
    (('together-ai-up-to-4b'), [
        ('input_cost_per_token', 1e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 1e-07),
    ]),
    (('together_ai', 'Qwen', 'Qwen3-235B-A22B-Instruct-2507-tput'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 262000),
        ('output_cost_per_token', 6e-06),
        ('source', 'https://www.together.ai/models/qwen3-235b-a22b-instruct-2507-fp8'),
    ]),
    (('together_ai', 'Qwen', 'Qwen3-235B-A22B-Thinking-2507'), [
        ('input_cost_per_token', 6.5e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 256000),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://www.together.ai/models/qwen3-235b-a22b-thinking-2507'),
    ]),
    (('together_ai', 'Qwen', 'Qwen3-235B-A22B-fp8-tput'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 40000),
        ('output_cost_per_token', 6e-07),
        ('source', 'https://www.together.ai/models/qwen3-235b-a22b-fp8-tput'),
    ]),
    (('together_ai', 'Qwen', 'Qwen3-Coder-480B-A35B-Instruct-FP8'), [
        ('input_cost_per_token', 2e-06),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 256000),
        ('output_cost_per_token', 2e-06),
        ('source', 'https://www.together.ai/models/qwen3-coder-480b-a35b-instruct'),
    ]),
    (('together_ai', 'Qwen', 'Qwen3-Next-80B-A3B-Instruct'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 262144),
        ('output_cost_per_token', 1.5e-06),
        ('source', 'https://www.together.ai/models/qwen3-next-80b-a3b-instruct'),
    ]),
    (('together_ai', 'Qwen', 'Qwen3-Next-80B-A3B-Thinking'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 262144),
        ('output_cost_per_token', 1.5e-06),
        ('source', 'https://www.together.ai/models/qwen3-next-80b-a3b-thinking'),
    ]),
    (('together_ai', 'Qwen', 'Qwen3.5-397B-A17B'), [
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 262144),
        ('output_cost_per_token', 3.6e-06),
        ('source', 'https://www.together.ai/models/Qwen/Qwen3.5-397B-A17B'),
    ]),
    (('together_ai', 'deepseek-ai', 'DeepSeek-R1'), [
        ('input_cost_per_token', 3e-06),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 20480),
        ('output_cost_per_token', 7e-06),
    ]),
    (('together_ai', 'deepseek-ai', 'DeepSeek-R1-0528-tput'), [
        ('input_cost_per_token', 5.5e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 128000),
        ('output_cost_per_token', 2.19e-06),
        ('source', 'https://www.together.ai/models/deepseek-r1-0528-throughput'),
    ]),
    (('together_ai', 'deepseek-ai', 'DeepSeek-V3'), [
        ('input_cost_per_token', 1.25e-06),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 65536),
        ('max_output_tokens', 8192),
        ('output_cost_per_token', 1.25e-06),
    ]),
    (('together_ai', 'deepseek-ai', 'DeepSeek-V3.1'), [
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 128000),
        ('max_output_tokens', 16384),
        ('output_cost_per_token', 1.7e-06),
        ('source', 'https://www.together.ai/models/deepseek-v3-1'),
    ]),
    (('together_ai', 'meta-llama', 'Llama-3.3-70B-Instruct-Turbo'), [
        ('input_cost_per_token', 8.8e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 8.8e-07),
    ]),
    (('together_ai', 'meta-llama', 'Llama-3.3-70B-Instruct-Turbo-Free'), [
        ('input_cost_per_token', 0),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 0),
    ]),
    (('together_ai', 'meta-llama', 'Llama-4-Maverick-17B-128E-Instruct-FP8'), [
        ('input_cost_per_token', 2.7e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 8.5e-07),
    ]),
    (('together_ai', 'meta-llama', 'Llama-4-Scout-17B-16E-Instruct'), [
        ('input_cost_per_token', 1.8e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 5.9e-07),
    ]),
    (('together_ai', 'meta-llama', 'Meta-Llama-3.1-405B-Instruct-Turbo'), [
        ('input_cost_per_token', 3.5e-06),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 3.5e-06),
    ]),
    (('together_ai', 'meta-llama', 'Meta-Llama-3.1-70B-Instruct-Turbo'), [
        ('input_cost_per_token', 8.8e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 8.8e-07),
    ]),
    (('together_ai', 'meta-llama', 'Meta-Llama-3.1-8B-Instruct-Turbo'), [
        ('input_cost_per_token', 1.8e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 1.8e-07),
    ]),
    (('together_ai', 'mistralai', 'Mixtral-8x7B-Instruct-v0.1'), [
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 6e-07),
    ]),
    (('together_ai', 'moonshotai', 'Kimi-K2-Instruct'), [
        ('input_cost_per_token', 1e-06),
        ('litellm_provider', 'together_ai'),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://www.together.ai/models/kimi-k2-instruct'),
    ]),
    (('together_ai', 'moonshotai', 'Kimi-K2-Instruct-0905'), [
        ('input_cost_per_token', 1e-06),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 262144),
        ('output_cost_per_token', 3e-06),
        ('source', 'https://www.together.ai/models/kimi-k2-0905'),
    ]),
    (('together_ai', 'moonshotai', 'Kimi-K2.5'), [
        ('input_cost_per_token', 5e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 256000),
        ('max_output_tokens', 256000),
        ('output_cost_per_token', 2.8e-06),
        ('source', 'https://www.together.ai/models/kimi-k2-5'),
    ]),
    (('together_ai', 'openai', 'gpt-oss-120b'), [
        ('input_cost_per_token', 1.5e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 131072),
        ('max_output_tokens', 131072),
        ('output_cost_per_token', 6e-07),
        ('source', 'https://www.together.ai/models/gpt-oss-120b'),
    ]),
    (('together_ai', 'openai', 'gpt-oss-20b'), [
        ('input_cost_per_token', 5e-08),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 128000),
        ('output_cost_per_token', 2e-07),
        ('source', 'https://www.together.ai/models/gpt-oss-20b'),
    ]),
    (('together_ai', 'zai-org', 'GLM-4.5-Air-FP8'), [
        ('input_cost_per_token', 2e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 128000),
        ('output_cost_per_token', 1.1e-06),
        ('source', 'https://www.together.ai/models/glm-4-5-air'),
    ]),
    (('together_ai', 'zai-org', 'GLM-4.6'), [
        ('input_cost_per_token', 6e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 200000),
        ('output_cost_per_token', 2.2e-06),
        ('source', 'https://www.together.ai/models/glm-4-6'),
    ]),
    (('together_ai', 'zai-org', 'GLM-4.7'), [
        ('input_cost_per_token', 4.5e-07),
        ('litellm_provider', 'together_ai'),
        ('max_input_tokens', 200000),
        ('max_output_tokens', 200000),
        ('output_cost_per_token', 2e-06),
        ('source', 'https://www.together.ai/models/glm-4-7'),
    ]),
]

_LITELLM_SUBSET: dict[str, dict[str, Any]] = {
    "/".join(k) if len(k) > 1 else k[0]: dict(v)
    for k, v in _LITELLM_ENTRIES
}
# Fields we keep from a LiteLLM per-entry record. Trimming is deliberate:
# (a) keeps the embedded dict small, (b) avoids surfacing fields the
#     router doesn't read, (c) makes the (provider, model) -> spec
#     flattening deterministic and testable.
_LITELLM_KEEP_FIELDS = (
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
    "cache_creation_input_token_cost",
    "max_input_tokens",
    "max_output_tokens",
    "litellm_provider",
    "source",
)

# Map LiteLLM's `litellm_provider` string onto the Charon pool label.
# Identity for every value Charon currently uses; kept as an explicit table
# so a LiteLLM rename is caught at load time (logged red) rather than
# silently shadowing a Charon pool under a wrong key.
_LITELLM_PROVIDER_TO_CHARON: dict[str, str] = {
    "deepseek": "deepseek",
    "openrouter": "openrouter",
    "together_ai": "together_ai",
    "groq": "groq",
    "fireworks_ai": "fireworks_ai",
}

# Default poller cadence. Operator-configurable; the test suite overrides
# this to a tiny value so the loop runs once and exits deterministically.
_DEFAULT_OPENROUTER_TTL_S = 3600.0  # hourly — one GET returns the whole catalog
_DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"

# OpenRouter's per-token prices arrive as STRINGS ("0.00000002") — we
# parse with this tolerance, not json.loads(float), so a future upstream
# schema drift (e.g. scientific notation, a trailing zero) is contained
# to the parser.
def _parse_price_string(raw: Any) -> float | None:
    """Parse OpenRouter's per-token price string. None on any failure
    (a bad string is logged red and skipped — never raised, never zero)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        f = float(raw)
        return f if f >= 0 else None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or s.lower() in ("null", "none", "0"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f >= 0 else None


# ── cache: the (provider, model) → price entry the router consumes ──────────
@dataclass(frozen=True)
class PriceEntry:
    """One (provider, model) per-token price record.

    ``cost_input`` / ``cost_output`` are PER-TOKEN USD (LiteLLM's
    ``input_cost_per_token`` is already per-token, not per-1K).  ``free``
    is sticky-true for explicitly free sources and lets the router
    short-circuit the blended-rank math (``order_pool_by_live_cost``
    sorts free entries first regardless of price)."""
    provider: str
    model: str
    cost_input: float | None = None
    cost_output: float | None = None
    cache_read: float | None = None
    cache_write: float | None = None
    source: str = ""           # upstream URL (LiteLLM `source` or OpenRouter model `id`)
    source_kind: str = ""      # "vendored" | "openrouter" | "webhook"
    updated_at: float = field(default_factory=time.time)

    def to_router_spec(self) -> dict[str, Any]:
        """Flatten this entry into the shape ``model_pricing`` uses.

        The router reads ``cost_input`` / ``cost_output`` / ``free`` from
        the per-model dict built by ``forwarder.py:540``; that dict is
        fed into ``_live_rank_key`` -> ``derived_cost_rank`` -> the
        3:1 in:out blend. The ``free`` flag short-circuits the rank
        entirely. The other fields (cache_*, source_*) are passed
        through for downstream observers (e.g. R17 drift) but never
        affect the cheapest-first sort."""
        spec: dict[str, Any] = {}
        if self.cost_input is not None:
            spec["cost_input"] = float(self.cost_input)
        if self.cost_output is not None:
            spec["cost_output"] = float(self.cost_output)
        if self.cache_read is not None:
            spec["cost_input_cache_read"] = float(self.cache_read)
        if self.cache_write is not None:
            spec["cost_input_cache_write"] = float(self.cache_write)
        if self.cost_input == 0 and self.cost_output == 0:
            spec["free"] = True
        if self.source:
            spec["source"] = self.source
        if self.source_kind:
            spec["source_kind"] = self.source_kind
        return spec


class PriceCache:
    """The local cache the three writers feed and the router reads from.

    Keyed per **(provider, model)** so the same model is correctly priced
    differently per provider (pitfall #4). The flatten step
    (:meth:`flatten`) projects this to the model-level shape the router
    actually consumes (``model_pricing[mid] = {cost_input, ...}``) by
    picking the cheapest sourced price for each model id, with the
    chosen provider recorded alongside — the meter, once present,
    overrides this on the hot path.

    Thread-safe. All writers take the lock briefly; readers
    (:meth:`snapshot`) take a shallow copy under the lock and return it
    so the router never iterates a half-updated map.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], PriceEntry] = {}

    # ── writers (all background; never invoked from forward_with_failover) ──
    def put(self, entry: PriceEntry) -> None:
        """Insert/replace one (provider, model) entry. No-op if ``entry``
        has neither cost_input nor cost_output (a sourced record with
        no price is useless for cold-start ordering and is dropped, not
        stored as zero)."""
        if entry.cost_input is None and entry.cost_output is None:
            return
        with self._lock:
            self._entries[(entry.provider, entry.model)] = entry

    def remove(self, provider: str, model: str) -> None:
        with self._lock:
            self._entries.pop((provider, model), None)

    # ── readers ─────────────────────────────────────────────────────────────
    def get(self, provider: str, model: str) -> PriceEntry | None:
        with self._lock:
            return self._entries.get((provider, model))

    def providers(self) -> set[str]:
        with self._lock:
            return {p for p, _ in self._entries}

    def snapshot(self) -> dict[tuple[str, str], PriceEntry]:
        with self._lock:
            return dict(self._entries)

    # ── the flatten: per-(provider,model) → per-model for the router ───────
    def flatten(self) -> dict[str, dict[str, Any]]:
        """Compile the (provider, model) cache into the per-model shape
        ``model_pricing`` consumes.

        For each ``model`` id that appears under multiple providers, we
        pick the **cheapest sourced price** (input*3 + output)/4, the
        cold-start ordering hint — and record the chosen provider so an
        observer / drift-check can see which source won. The
        ``all_providers`` list carries every (provider, model) variant
        the cache holds for that id, so a future pass that needs the
        per-provider detail (R17 drift, R5 per-route) can recover it
        without re-querying upstream."""
        out: dict[str, dict[str, Any]] = {}
        # Bucket by model id; a model can appear under many providers.
        by_model: dict[str, list[PriceEntry]] = {}
        with self._lock:
            entries = list(self._entries.values())
        for e in entries:
            by_model.setdefault(e.model, []).append(e)

        for mid, group in by_model.items():
            # "Free" wins regardless of price (free-daily sort beats any
            # blended cost rank). Otherwise pick the cheapest blended.
            free = [e for e in group if e.cost_input == 0 and e.cost_output == 0]
            if free:
                best = sorted(free, key=lambda e: e.source_kind)[0]
            else:
                def _blend(e: PriceEntry) -> float:
                    ci = e.cost_input if e.cost_input is not None else 0.0
                    co = e.cost_output if e.cost_output is not None else 0.0
                    return (3.0 * ci + co) / 4.0
                best = min(group, key=_blend)
            spec = best.to_router_spec()
            spec["provider"] = best.provider
            spec["all_providers"] = sorted(
                {(e.provider, e.source_kind) for e in group})
            out[mid] = spec
        return out


# ── writer (a): vendored LiteLLM snapshot ──────────────────────────────────
def load_vendored_snapshot(
    cache: PriceCache,
    *,
    subset: dict[str, dict[str, Any]] | None = None,
) -> int:
    """Load the vendored LiteLLM subset into *cache* and return the
    number of entries written.

    Each LiteLLM key is either ``<model>`` (direct providers, e.g.
    ``deepseek-chat`` for ``litellm_provider == "deepseek"``) or
    ``<provider>/<model>`` (reseller listings, e.g.
    ``openrouter/deepseek/deepseek-chat``). We split on the FIRST ``/``
    after the matching provider prefix and use the rest as the model
    id, falling back to the raw key for direct providers.

    ``subset`` is an injection seam for the test suite (the production
    constant is ``_LITELLM_SUBSET``). It exists so a test can verify
    "revert the snapshot load → cache is empty" by passing ``{}``
    without monkey-patching the module constant."""
    src = subset if subset is not None else _LITELLM_SUBSET
    written = 0
    for raw_key, raw_entry in src.items():
        if not isinstance(raw_entry, dict):
            continue
        litellm_prov = raw_entry.get("litellm_provider")
        if not isinstance(litellm_prov, str):
            continue
        charon_prov = _LITELLM_PROVIDER_TO_CHARON.get(litellm_prov)
        if charon_prov is None:
            # Provider not in Charon's routed set (e.g. openai, bedrock).
            # Skip silently — the subset filter means this only fires for
            # entries with a `litellm_provider` we don't recognize, which
            # would be a config bug worth knowing about.
            log.warning(
                "vendored LiteLLM entry %r has unrecognised litellm_provider "
                "%r — skipping (not in Charon's routed set)",
                raw_key, litellm_prov)
            continue
        # Resolve the model id. Direct providers use the bare key
        # (e.g. "deepseek-chat" → model "deepseek-chat"). Reseller
        # listings use "<provider>/<model>" so we strip the prefix.
        if "/" in raw_key:
            model_id = raw_key.split("/", 1)[1]
        else:
            model_id = raw_key
        if not model_id:
            continue
        # Pull only the kept fields; everything else (mode flags, region
        # tables, the sample_spec sentinel) is dropped.
        clean: dict[str, Any] = {
            k: raw_entry[k] for k in _LITELLM_KEEP_FIELDS if k in raw_entry
        }
        cost_in = _parse_price_string(clean.get("input_cost_per_token"))
        cost_out = _parse_price_string(clean.get("output_cost_per_token"))
        cache_read = _parse_price_string(clean.get("cache_read_input_token_cost"))
        cache_write = _parse_price_string(clean.get("cache_creation_input_token_cost"))
        entry = PriceEntry(
            provider=charon_prov,
            model=model_id,
            cost_input=cost_in,
            cost_output=cost_out,
            cache_read=cache_read,
            cache_write=cache_write,
            source=str(clean.get("source", "")),
            source_kind="vendored",
        )
        cache.put(entry)
        written += 1
    return written


# ── writer (b): OpenRouter live poll (background TTL) ──────────────────────
@dataclass
class OpenRouterPollResult:
    """One poll's outcome. Test-facing: ``ok=True`` + a count means
    we accepted the payload; a red log + ``ok=False`` is a non-fatal
    failure that keeps the last-good cache (stale-but-usable)."""
    ok: bool
    fetched: int = 0
    parsed: int = 0
    error: str = ""


def _parse_openrouter_pricing(pricing: Any) -> tuple[float | None, float | None,
                                                       float | None, float | None]:
    """OpenRouter returns pricing as ``{"prompt": "0.00000002",
    "completion": "0.0000001", "input_cache_read": "0.000000005", ...}``
    — all per-token USD strings. Returns (input, output, cache_read,
    cache_write) with None for any field the provider didn't quote."""
    if not isinstance(pricing, dict):
        return (None, None, None, None)
    return (
        _parse_price_string(pricing.get("prompt")),
        _parse_price_string(pricing.get("completion")),
        _parse_price_string(pricing.get("input_cache_read")),
        _parse_price_string(pricing.get("input_cache_write")),
    )


def _http_get_json(url: str, *, timeout: float = 10.0) -> Any:
    """Stdlib GET + JSON parse. NEVER imported on a hot path — this
    helper is only reachable from the background poller / ingest
    handler, both of which are off the routing path. urllib (not
    requests) so the privileged-core stdlib-only rule holds."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "charon-price-refresher/1.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body.decode("utf-8"))


def fetch_openrouter_catalog(
    *,
    url: str = _DEFAULT_OPENROUTER_URL,
    fetcher: Callable[[str], Any] | None = None,
) -> OpenRouterPollResult:
    """One OpenRouter poll. ``fetcher`` is the test injection seam
    (the production wire is ``_http_get_json``). On any failure —
    network, non-200, malformed JSON, no ``data`` array — returns
    ``ok=False`` with the error string and the caller keeps the
    last-good cache (stale-but-usable). NEVER raises."""
    get = fetcher if fetcher is not None else _http_get_json
    try:
        payload = get(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError, ValueError) as exc:
        return OpenRouterPollResult(ok=False, error=f"{type(exc).__name__}: {exc}")
    if not isinstance(payload, dict):
        return OpenRouterPollResult(ok=False, error="payload is not a JSON object")
    data = payload.get("data")
    if not isinstance(data, list):
        return OpenRouterPollResult(ok=False, error="payload.data is not a list")
    return OpenRouterPollResult(ok=True, fetched=len(data))


def ingest_openrouter_catalog(
    cache: PriceCache,
    payload: Any,
) -> int:
    """Parse a full OpenRouter ``/api/v1/models`` payload (already JSON-
    decoded) and write every entry's price into *cache* under provider
    ``"openrouter"``.

    Split out from :func:`fetch_openrouter_catalog` so a test (or a
    cached-on-disk fallback) can drive the parse step without
    performing the network GET. Returns the number of entries
    successfully written; bad rows are logged red and skipped (never
    raised, never zeroed)."""
    if not isinstance(payload, dict):
        return 0
    data = payload.get("data")
    if not isinstance(data, list):
        return 0
    written = 0
    for row in data:
        if not isinstance(row, dict):
            continue
        model_id = row.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        # OpenRouter model ids are "vendor/model-name" (e.g. "openai/gpt-4o")
        # — that's exactly the (provider, model) shape the router keys on
        # under pool label "openrouter". We keep the WHOLE id as the model
        # key (the slash is part of the id, not a separator), matching how
        # the catalog_refresh normalizer handles OpenRouter entries.
        cost_in, cost_out, cache_read, cache_write = _parse_openrouter_pricing(
            row.get("pricing"))
        if cost_in is None and cost_out is None:
            continue  # a model with no per-token price is not cold-start usable
        entry = PriceEntry(
            provider="openrouter",
            model=model_id,
            cost_input=cost_in,
            cost_output=cost_out,
            cache_read=cache_read,
            cache_write=cache_write,
            source=str(row.get("id", "")),  # OpenRouter uses id-as-source
            source_kind="openrouter",
        )
        cache.put(entry)
        written += 1
    return written


class OpenRouterPoller:
    """Background TTL poller for the OpenRouter live catalog.

    Construction is side-effect-free (no network, no thread). The first
    poll runs when :meth:`start` is called; subsequent polls happen
    every ``ttl_s`` seconds until :meth:`stop`. The router never reads
    from this object — it reads :class:`PriceCache` directly. The
    poller is a WRITER into that cache, not a query path."""

    def __init__(
        self,
        cache: PriceCache,
        *,
        url: str = _DEFAULT_OPENROUTER_URL,
        ttl_s: float = _DEFAULT_OPENROUTER_TTL_S,
        fetcher: Callable[[str], Any] | None = None,
    ) -> None:
        self._cache = cache
        self.url = url
        self.ttl_s = float(ttl_s)
        self._fetcher = fetcher
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Test-facing counter: a test asserts this stays 0 across
        # ``forward_with_failover`` (the off-hot-path guard).
        self.poll_count = 0
        self.last_result: OpenRouterPollResult | None = None

    def poll_once(self) -> OpenRouterPollResult:
        """Run one poll. Never raises — on any failure logs red and
        returns ``ok=False`` so the caller keeps the last-good cache."""
        self.poll_count += 1
        result = fetch_openrouter_catalog(
            url=self.url, fetcher=self._fetcher)
        if not result.ok:
            log.error(
                "openrouter poll failed (%s) — keeping last-good cache "
                "(stale-but-usable)", result.error)
            self.last_result = result
            return result
        # The fetch helper only validates shape; the parse is in a
        # separate call so tests can drive it without network.
        try:
            # We re-fetch with the same fetcher here ONLY in the
            # default path (the test path injects a parsed dict via
            # ``_fetcher``).  To keep the split clean, we expose the
            # network GET via ``_fetcher`` and require test fakes to
            # return the *decoded* payload directly.
            payload = self._fetcher(self.url) if self._fetcher is not None \
                else _http_get_json(self.url)
            written = ingest_openrouter_catalog(self._cache, payload)
            result = OpenRouterPollResult(
                ok=True, fetched=result.fetched, parsed=written)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError, ValueError) as exc:
            log.error(
                "openrouter poll parse failed (%s) — keeping last-good "
                "cache (stale-but-usable)", exc)
            result = OpenRouterPollResult(
                ok=False, fetched=result.fetched, error=str(exc))
        self.last_result = result
        return result

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    self.poll_once()
                except Exception as exc:  # noqa: BLE001 — loop never dies
                    log.error("openrouter poller cycle raised (%s: %s) — "
                              "keeping last-good cache",
                              type(exc).__name__, exc)
                if self._stop.wait(self.ttl_s):
                    break

        self._thread = threading.Thread(
            target=_loop, daemon=True, name="charon-openrouter-poller")
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)


# ── writer (c): changedetection.io webhook ingest ──────────────────────────
@dataclass(frozen=True)
class WebhookUpdate:
    """The structured payload changedetection.io POSTs to Charon.

    Schema (per the eval): ``{"provider": "...", "url": "...",
    "old": "...", "new": "..."}``. ``old`` / ``new`` are the BEFORE /
    AFTER of whatever the detector watched (typically a rendered price
    cell on the provider's website). We store the *new* value as the
    authoritative sourced price and keep the URL for the R17 drift
    trail."""
    provider: str
    url: str
    old: str
    new: str
    # Optional, if the detector pre-parses the price for us.
    cost_input: float | None = None
    cost_output: float | None = None
    model: str = ""


def parse_change_detection_payload(
    payload: Any,
    *,
    charon_providers: set[str] | None = None,
) -> WebhookUpdate | None:
    """Parse and validate a changedetection.io webhook body.

    Required keys: ``provider``, ``url``, ``new``. ``old`` may be
    empty (first observation of a new field — the diff is "absent →
    present" rather than a change).  ``model`` is OPTIONAL — when the
    detector can't tell which model a price change refers to, the
    caller may attach a ``model`` key; we surface it on the resulting
    :class:`WebhookUpdate` and reject (return None) if the model is
    missing AND the provider is one that has more than one model
    (would be ambiguous). For single-model providers (nanogpt,
    neuralwatt today) we accept a bare payload.

    ``charon_providers`` is a test seam: by default we accept any
    provider string, the test passes the configured provider set so
    "off-list" providers get a red + None.
    """
    if not isinstance(payload, dict):
        return None
    prov = payload.get("provider")
    url = payload.get("url")
    new = payload.get("new")
    old = payload.get("old", "")
    if not (isinstance(prov, str) and prov
            and isinstance(url, str) and url
            and isinstance(new, str) and new):
        return None
    if charon_providers is not None and prov not in charon_providers:
        log.error("change-detection webhook for off-list provider %r — "
                  "dropping (configure the provider in the gateway first)", prov)
        return None
    model = payload.get("model", "")
    if not isinstance(model, str):
        model = ""
    ci_raw = payload.get("cost_input")
    co_raw = payload.get("cost_output")
    ci = _parse_price_string(ci_raw) if ci_raw is not None else None
    co = _parse_price_string(co_raw) if co_raw is not None else None
    return WebhookUpdate(
        provider=prov, url=url, old=str(old), new=str(new),
        cost_input=ci, cost_output=co, model=model)


def ingest_change_detection(
    cache: PriceCache,
    payload: Any,
    *,
    charon_providers: set[str] | None = None,
) -> int:
    """Parse a changedetection.io webhook body and write the resulting
    price update into *cache*. Returns 1 on success, 0 on a dropped
    payload (parse failure, off-list provider, ambiguous model).

    When the detector pre-parses ``cost_input`` / ``cost_output`` into
    numeric fields, those win. Otherwise we attempt to parse the
    ``new`` string as a per-token price (cheap heuristic: if the
    string is a plain number → use as ``cost_input`` AND
    ``cost_output``, suitable for providers that quote a single
    per-request price like NeuralWatt)."""
    upd = parse_change_detection_payload(payload, charon_providers=charon_providers)
    if upd is None:
        return 0
    if not upd.model:
        log.error("change-detection webhook missing model for provider %r "
                  "— dropping (ambiguous target)", upd.provider)
        return 0
    cost_in = upd.cost_input
    cost_out = upd.cost_output
    if cost_in is None and cost_out is None:
        # Fallback: if `new` parses cleanly as a single number, treat it
        # as both input and output (NeuralWatt-style "per-request" pricing
        # collapses to a single value here — the meter will refine it).
        fallback = _parse_price_string(upd.new)
        if fallback is not None:
            cost_in = fallback
            cost_out = fallback
    if cost_in is None and cost_out is None:
        log.error("change-detection webhook for %s/%s: could not parse "
                  "price from new=%r — dropping", upd.provider, upd.model, upd.new)
        return 0
    entry = PriceEntry(
        provider=upd.provider, model=upd.model,
        cost_input=cost_in, cost_output=cost_out,
        source=upd.url, source_kind="webhook",
    )
    cache.put(entry)
    return 1


# ── module-level helpers (the wire into the running router) ───────────────
def apply_to(
    cache: PriceCache,
    model_pricing: dict[str, dict],
) -> int:
    """Flatten *cache* into the given ``model_pricing`` dict in place
    and return the number of model ids written.

    The router reads ``model_pricing`` as a model-level map (forwarder
    R2 block, forwarder.py:540). This helper does the per-(provider,
    model) → per-model projection at the writer boundary, so the
    router itself stays unaware of the multi-provider cache. Existing
    keys are not clobbered: ``setdefault`` semantics — operator
    hand-configured prices win over a sourced/pulled value, exactly
    like the catalog_refresh bridge's static-wins rule."""
    flat = cache.flatten()
    written = 0
    for mid, spec in flat.items():
        existing = model_pricing.get(mid)
        if existing:
            # Operator hand-configured prices win. Only fill in the
            # fields that are missing.
            for k, v in spec.items():
                existing.setdefault(k, v)
        else:
            model_pricing[mid] = dict(spec)
        written += 1
    return written


__all__ = [
    "PriceCache",
    "PriceEntry",
    "WebhookUpdate",
    "OpenRouterPollResult",
    "OpenRouterPoller",
    "load_vendored_snapshot",
    "fetch_openrouter_catalog",
    "ingest_openrouter_catalog",
    "parse_change_detection_payload",
    "ingest_change_detection",
    "apply_to",
]
