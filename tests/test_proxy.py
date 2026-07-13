"""MVP #2 — observing gateway proxy core (ADR-0004 R1).

Proves the linchpin signal: turning a gateway response into exhaustion / silent-
downgrade / cost — the thing Charon can't otherwise see because the agent (not
Charon) talks to the gateway. Pure observation logic; no real network.
"""
from __future__ import annotations

from charon.proxy import GatewayProxy


def test_429_is_exhaustion_with_retry_after() -> None:
    p = GatewayProxy()
    obs = p.observe("openrouter/qwen3-coder", 429,
                    headers={"Retry-After": "30"},
                    body={"error": {"metadata": {"error_type": "rate_limit_exceeded"}}})
    assert obs.exhausted and obs.failover
    assert obs.retry_after == 30
    assert "rate_limit_exceeded" in obs.note
    assert p.is_exhausted("openrouter/qwen3-coder")
    assert p.exhausted_models() == {"openrouter/qwen3-coder"}


def test_402_payment_required_is_exhaustion() -> None:
    p = GatewayProxy()
    obs = p.observe("nano-gpt/kimi-k2", 402, body={"error": {"code": "payment_required"}})
    assert obs.exhausted and obs.failover


def test_200_model_match_records_usage_no_failover() -> None:
    p = GatewayProxy()
    obs = p.observe("openrouter/qwen3-coder", 200,
                    body={"model": "openrouter/qwen3-coder",
                          "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.002}})
    assert not obs.failover and not obs.exhausted and not obs.pseudo_success
    assert obs.usage is not None and obs.usage.tokens == 150
    assert p.cumulative_usage().cost_usd == 0.002
    assert p.exhausted_models() == set()


def test_silent_downgrade_is_pseudo_success_failover() -> None:
    # asked for a flat paid model, gateway silently served a free one → must fail over.
    p = GatewayProxy()
    obs = p.observe("opencode-go/glm-5.2", 200,
                    body={"model": "glm-free", "usage": {"prompt_tokens": 10}})
    assert obs.pseudo_success and obs.failover and not obs.exhausted
    assert "silent downgrade" in obs.note
    assert p.is_exhausted("opencode-go/glm-5.2")  # excluded on next route


def test_prefixed_pool_id_native_return_is_not_false_pseudo_success() -> None:
    """The router records exclusion under the prefixed pool id
    (``opencode-go/kimi-k2.7-code``) while the upstream returns the bare native id
    (``kimi-k2.7-code``). Comparing the return against the pool id would
    false-flag every honest 200 as a silent downgrade (it did, live); the native
    ``expected_model`` is the correct baseline."""
    p = GatewayProxy()
    obs = p.observe("opencode-go/kimi-k2.7-code", 200,
                    body={"model": "kimi-k2.7-code",
                          "usage": {"prompt_tokens": 8, "completion_tokens": 2}},
                    expected_model="kimi-k2.7-code")
    assert not obs.pseudo_success and not obs.failover
    assert obs.usage is not None and obs.usage.tokens == 10
    assert p.exhausted_models() == set()


def test_pseudo_success_still_fires_against_native_expected_model() -> None:
    # genuine downgrade: asked (native) kimi, gateway served a free model.
    p = GatewayProxy()
    obs = p.observe("opencode-go/kimi-k2.7-code", 200,
                    body={"model": "some-free-model"},
                    expected_model="kimi-k2.7-code")
    assert obs.pseudo_success and obs.failover
    assert p.is_exhausted("opencode-go/kimi-k2.7-code")  # excluded under the pool id


def test_cumulative_usage_sums_across_calls() -> None:
    p = GatewayProxy()
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.5}
    for _ in range(3):
        p.observe("m", 200, body={"model": "m", "usage": usage})
    u = p.cumulative_usage()
    assert u.tokens_in == 30 and u.tokens_out == 15 and u.cost_usd == 1.5


def test_503_overload_is_exhaustion() -> None:
    p = GatewayProxy()
    assert p.observe("m", 503).failover


def test_404_drops_model_from_pool() -> None:
    # free rosters churn: 404 = "unavailable for free" = drop, not retry (R6).
    p = GatewayProxy()
    obs = p.observe("openrouter/deepseek:free", 404, body={"error": {"message": "unavailable"}})
    assert obs.dropped and obs.failover and not obs.exhausted
    assert p.is_exhausted("openrouter/deepseek:free")
    assert "dropped" in obs.note


def test_400_unsupported_model_drops_and_fails_over() -> None:
    # A provider that doesn't host a model returns a terminal 400 ("Model gpt-5.5
    # is not supported"). Treat it like a 404 drop so the router fails over to a
    # provider that DOES have it (tier/cross-provider fallback), instead of
    # returning the error straight to the client.
    p = GatewayProxy()
    obs = p.observe("gpt-5.5", 400,
                    body={"error": {"message": "Model gpt-5.5 is not supported"}})
    assert obs.dropped and obs.failover and not obs.exhausted
    assert p.is_exhausted("gpt-5.5")  # excluded from the next route
    assert "dropped" in obs.note and "unsupported" in obs.note


def test_400_generic_bad_request_does_not_fail_over() -> None:
    # A generic 400 (bad params, NOT a model-availability error) must not drop or
    # fail over — it would fail identically on every provider.
    p = GatewayProxy()
    obs = p.observe("m", 400, body={"error": {"message": "temperature must be <= 2.0"}})
    assert not obs.dropped and not obs.failover and not obs.exhausted


def test_take_delta_returns_increment() -> None:
    p = GatewayProxy()
    p.observe("m", 200, body={"model": "m", "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    d1 = p.take_delta()
    assert d1.tokens == 15
    p.observe("m", 200, body={"model": "m", "usage": {"prompt_tokens": 4, "completion_tokens": 1}})
    d2 = p.take_delta()
    assert d2.tokens == 5  # only the new increment
    assert p.take_delta().tokens == 0  # nothing new


def test_concurrent_observe_loses_no_usage() -> None:
    # the proxy server is threaded; observe() must be atomic (review #1).
    import threading
    p = GatewayProxy()
    usage = {"prompt_tokens": 1, "completion_tokens": 1}

    def hammer() -> None:
        for _ in range(200):
            p.observe("m", 200, body={"model": "m", "usage": usage})

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 8 threads × 200 calls × 2 tokens = 3200, none lost to a race
    assert p.cumulative_usage().tokens == 3200


def test_upstream_returns_model_with_provider_prefix() -> None:
    # R10d: an upstream returning a normalized model id with provider prefix
    # should not false-positive as a silent downgrade. The expected model is
    # bare ("kimi-k2.7-code"), but upstream returns it with prefix
    # ("opencode-go/kimi-k2.7-code") — both resolve to the same model.
    p = GatewayProxy()
    obs = p.observe("opencode-go/kimi-k2.7-code", 200,
                    body={"model": "opencode-go/kimi-k2.7-code",
                          "usage": {"prompt_tokens": 10}},
                    expected_model="kimi-k2.7-code")
    assert not obs.pseudo_success and not obs.failover
    assert obs.usage is not None and obs.usage.tokens_in == 10
    assert p.exhausted_models() == set()


def test_normalized_comparison_still_catches_real_downgrade() -> None:
    # Ensure the normalization doesn't suppress REAL downgrades. If asked for
    # one model and get a different one (even after stripping prefixes), flag it.
    p = GatewayProxy()
    obs = p.observe("opencode-go/gpt-4", 200,
                    body={"model": "opencode-go/gpt-4-turbo",
                          "usage": {"prompt_tokens": 10}},
                    expected_model="gpt-4")
    assert obs.pseudo_success and obs.failover
    assert "silent downgrade" in obs.note
    assert p.is_exhausted("opencode-go/gpt-4")


def test_normalized_comparison_both_prefixed() -> None:
    # Both sides have provider prefixes but the same model id.
    p = GatewayProxy()
    obs = p.observe("opencode-go/kimi-k2.7-code", 200,
                    body={"model": "opencode-go/kimi-k2.7-code",
                          "usage": {"prompt_tokens": 5}},
                    expected_model="opencode-go/kimi-k2.7-code")
    assert not obs.pseudo_success and not obs.failover
    assert obs.usage is not None and obs.usage.tokens_in == 5
    assert p.exhausted_models() == set()


def test_normalized_comparison_different_prefixes_same_model() -> None:
    # The upstream might return a model with a DIFFERENT provider prefix
    # (e.g., the proxy normalizes "opencode-go/model" to "openai/model" or
    # bare "model"). As long as the base model id matches, it's not a downgrade.
    p = GatewayProxy()
    obs = p.observe("opencode-go/gpt-4", 200,
                    body={"model": "openai/gpt-4",
                          "usage": {"prompt_tokens": 8}},
                    expected_model="gpt-4")
    assert not obs.pseudo_success and not obs.failover
    assert obs.usage is not None
    assert p.exhausted_models() == set()


def test_401_with_billing_body_is_exhaustion() -> None:
    """OpenCode returns 401 for billing failures — body says 'insufficient_balance'.
    The proxy must detect this as exhausted (fail over), not auth (don't fail over)."""
    p = GatewayProxy()
    obs = p.observe("opencode-go/kimi-k2.7-code", 401,
                    body={"error": {"message": "Insufficient balance"}})
    assert obs.exhausted and obs.failover
    assert "exhausted" in obs.note
    assert p.is_exhausted("opencode-go/kimi-k2.7-code")


def test_401_with_auth_body_is_not_exhaustion() -> None:
    """A 401 with 'invalid_api_key' is an auth error — do NOT fail over because
    retrying with the same bad key on another provider is pointless."""
    p = GatewayProxy()
    obs = p.observe("opencode-go/kimi-k2.7-code", 401,
                    body={"error": {"message": "Invalid API key"}})
    assert not obs.exhausted and not obs.failover
    assert p.exhausted_models() == set()


def test_401_with_neither_pattern_is_auth() -> None:
    """A 401 with an unrecognized body is conservatively treated as auth — don't
    fail over if we can't confirm it's billing."""
    p = GatewayProxy()
    obs = p.observe("opencode-go/kimi-k2.7-code", 401,
                    body={"error": {"message": "something else"}})
    assert not obs.exhausted and not obs.failover
    assert p.exhausted_models() == set()


def test_401_with_no_body_is_auth() -> None:
    """A 401 with no response body — assume auth, don't fail over."""
    p = GatewayProxy()
    obs = p.observe("opencode-go/kimi-k2.7-code", 401, body=None)
    assert not obs.exhausted and not obs.failover
    assert p.exhausted_models() == set()


def test_list_shaped_body_does_not_raise_and_classifies_status() -> None:
    """Google's OpenAI-compatible error bodies are a JSON *array*, not an object
    (e.g. ``[{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}]``).
    ``classify``/``observe`` must degrade gracefully (no parseable fields) rather
    than raise ``AttributeError: 'list' object has no attribute 'get'`` — which,
    pre-fix, surfaced mid-request as a client-visible connection reset instead of
    a clean 429 passthrough. The status must still classify the same as an empty
    dict body would."""
    p = GatewayProxy()
    list_body = [{"error": {"code": 429, "message": "depleted", "status": "RESOURCE_EXHAUSTED"}}]
    obs = p.observe("google-aistudio/gemini-2.5-pro", 429, body=list_body)  # must not raise
    baseline = GatewayProxy().observe("google-aistudio/gemini-2.5-pro-2", 429, body={})
    assert obs.exhausted == baseline.exhausted and obs.exhausted is True
    assert obs.failover and obs.status == 429
    assert obs.returned_model is None


def test_list_shaped_billing_body_at_401_is_still_detected_as_exhaustion() -> None:
    """A list-shaped body isn't just a crash risk — dropping it outright (treating
    it as "no body") would also blind the 401 billing-pattern check, since
    ``_is_auth_error`` conservatively treats a bodyless 401 as auth (don't fail
    over). Wrapping the list as ``{"error": body}`` instead of discarding it lets
    ``_collect_error_strings`` (which already recurses into lists) still find the
    billing language, so this must classify the same as the dict-body sibling
    ``test_401_with_billing_body_is_exhaustion`` — exhausted + failover, not auth."""
    p = GatewayProxy()
    list_body = [{"error": {"message": "Insufficient balance for this request"}}]
    obs = p.observe("google-aistudio/gemini-2.5-pro", 401, body=list_body)
    assert obs.exhausted and obs.failover
    assert "exhausted" in obs.note
    assert p.is_exhausted("google-aistudio/gemini-2.5-pro")


def test_list_shaped_body_without_billing_language_is_auth() -> None:
    """A list-shaped 401 body with no recognizable pattern falls back to the same
    conservative "assume auth, don't fail over" verdict as an empty dict body —
    wrapping the list must not manufacture a false billing match."""
    p = GatewayProxy()
    list_body = [{"error": {"message": "something else entirely"}}]
    obs = p.observe("google-aistudio/gemini-2.5-pro", 401, body=list_body)
    assert not obs.exhausted and not obs.failover
    assert p.exhausted_models() == set()


def test_401_unsupported_model_drops_and_fails_over() -> None:
    """RED failover-401-not-classified: opencode-go returns a *401* for a model it
    doesn't host ("Model gpt-5.5 is not supported") — neither billing nor auth. It
    must be classified as an unsupported-model DROP so failover advances to the next
    provider (the model may exist on a cheaper/free tier elsewhere). On master 401
    is absent from the unsupported-status set, so this is misclassified as auth and
    failover never fires."""
    p = GatewayProxy()
    obs = p.observe("opencode-go/gpt-5.5", 401,
                    body={"error": {"message": "Model gpt-5.5 is not supported"}})
    assert obs.dropped and obs.failover
    assert not obs.exhausted  # not billing — nothing to cool down
    assert "dropped" in obs.note and "unsupported" in obs.note
    assert p.is_exhausted("opencode-go/gpt-5.5")


def test_openrouter_wrapped_error_is_classifiable() -> None:
    """RED failover-401-not-classified: OpenRouter wraps the real upstream error under
    ``error.metadata.raw`` — often a *stringified JSON* blob — while ``error.message``
    is a generic "Provider returned error". On master ``_body_text_lower`` reads only
    ``error.message``, so the actionable "Invalid model" text is invisible and the
    body matches no classifier → the raw error is relayed instead of failing over.
    Flattening the nested/stringified error makes it classify as unsupported → drop."""
    p = GatewayProxy()
    body = {"error": {
        "message": "Provider returned error",
        "code": 400,
        "metadata": {
            "provider_name": "OpenRouter",
            "raw": '{"error": {"message": "Invalid model ID: gpt-5.5"}}',
        },
    }}
    obs = p.observe("openrouter/gpt-5.5", 400, body=body)
    assert obs.dropped and obs.failover
    assert p.is_exhausted("openrouter/gpt-5.5")


def test_billing_body_pattern_insufficient_quota() -> None:
    p = GatewayProxy()
    obs = p.observe("m", 402,
                    body={"error": {"message": "Insufficient quota exceeded"}})
    assert obs.exhausted and obs.failover


def test_billing_body_pattern_credits_exhausted() -> None:
    p = GatewayProxy()
    obs = p.observe("m", 429,
                    body={"error": {"type": "credits_exhausted"}})
    assert obs.exhausted and obs.failover


def test_billing_body_detail_field() -> None:
    """Check the 'detail' field (some providers put error text there)."""
    p = GatewayProxy()
    obs = p.observe("m", 401,
                    body={"detail": "Payment required — account balance is zero"})
    assert obs.exhausted and obs.failover


def test_billing_body_message_field() -> None:
    """Check top-level 'message' field."""
    p = GatewayProxy()
    obs = p.observe("m", 401,
                    body={"message": "Rate limit exceeded"})
    assert obs.exhausted and obs.failover


def test_exhaustion_body_does_not_match_auth_case_insensitive() -> None:
    """Auth patterns should NOT be caught as billing."""
    p = GatewayProxy()
    obs = p.observe("m", 401,
                    body={"error": {"code": "INVALID_KEY", "message": "Bad credentials"}})
    assert not obs.exhausted and not obs.failover


def test_exhaustion_body_patterns_in_error_code_field() -> None:
    """Error code field can carry a billing-pattern string."""
    p = GatewayProxy()
    obs = p.observe("m", 401,
                    body={"error": {"code": "insufficient_balance"}})
    assert obs.exhausted and obs.failover


# ── SR-5b: computed cost_usd from captured per-token pricing ──────────

def test_computed_cost_from_pricing_when_provider_reports_none() -> None:
    """A priced model that returns a 200 with NO cost → cost_usd is computed from
    the stored per-token rates (units are per-TOKEN, not per-1M)."""
    pricing = {"m": {"cost_input": 0.000002, "cost_output": 0.000006}}
    p = GatewayProxy(model_pricing=pricing)
    obs = p.observe("m", 200,
                    body={"model": "m",
                          "usage": {"prompt_tokens": 1000, "completion_tokens": 500}})
    assert obs.usage is not None
    # 1000 * 2e-6 + 500 * 6e-6 = 0.002 + 0.003 = 0.005
    assert obs.usage.cost_usd == 0.005
    assert obs.cost_source == "computed"
    assert p.cumulative_usage().cost_usd == 0.005


def test_provider_reported_cost_is_not_overwritten() -> None:
    """When the provider self-reports a non-zero cost, it wins — pricing is ignored."""
    pricing = {"m": {"cost_input": 0.000002, "cost_output": 0.000006}}
    p = GatewayProxy(model_pricing=pricing)
    obs = p.observe("m", 200,
                    body={"model": "m",
                          "usage": {"prompt_tokens": 1000, "completion_tokens": 500,
                                    "cost": 0.42}})
    assert obs.usage is not None and obs.usage.cost_usd == 0.42
    assert obs.cost_source == "provider"


def test_unpriced_model_falls_back_to_zero_no_crash() -> None:
    """A model with NO stored pricing → cost stays 0/None, cost_source=unpriced,
    and nothing crashes."""
    p = GatewayProxy(model_pricing={"other": {"cost_input": 1.0, "cost_output": 1.0}})
    obs = p.observe("m", 200,
                    body={"model": "m",
                          "usage": {"prompt_tokens": 1000, "completion_tokens": 500}})
    assert obs.usage is not None and obs.usage.cost_usd == 0.0
    assert obs.cost_source == "unpriced"
    assert p.cumulative_usage().cost_usd == 0.0


def test_free_flag_pricing_path() -> None:
    """A model flagged free:true → cost stays 0 and cost_source=free (not computed)."""
    p = GatewayProxy(model_pricing={"m": {"free": True}})
    obs = p.observe("m", 200,
                    body={"model": "m",
                          "usage": {"prompt_tokens": 1000, "completion_tokens": 500}})
    assert obs.usage is not None and obs.usage.cost_usd == 0.0
    assert obs.cost_source == "free"


def test_namespaced_model_id_resolves_pricing() -> None:
    """A namespaced request id (deepseek/deepseek-v4-pro) resolves pricing stored
    under the bare final segment — parity with the pre-flight estimate, not the
    silent default floor."""
    pricing = {"deepseek-v4-pro": {"cost_input": 0.000001, "cost_output": 0.000001}}
    p = GatewayProxy(model_pricing=pricing)
    obs = p.observe("deepseek/deepseek-v4-pro", 200,
                    body={"model": "deepseek/deepseek-v4-pro",
                          "usage": {"prompt_tokens": 100, "completion_tokens": 100}})
    assert obs.usage is not None
    assert abs(obs.usage.cost_usd - 0.0002) < 1e-12  # 200 * 1e-6
    assert obs.cost_source == "computed"


def test_set_pricing_hot_reload_updates_cost() -> None:
    """set_pricing swaps pricing live (web-setup hot-reload) so subsequent calls
    compute cost from the new rates."""
    p = GatewayProxy()
    obs0 = p.observe("m", 200,
                     body={"model": "m", "usage": {"prompt_tokens": 100}})
    assert obs0.cost_source == "unpriced"
    p.set_pricing({"m": {"cost_input": 0.00001, "cost_output": 0.00001}})
    obs1 = p.classify("m", 200,
                      body={"model": "m",
                            "usage": {"prompt_tokens": 100, "completion_tokens": 0}})
    assert obs1.usage is not None and obs1.usage.cost_usd == 0.001
    assert obs1.cost_source == "computed"


# ---- DRAIN routing: free-first-then-drain ordering + exclude-at-0 ----------

def test_order_chain_by_funding_class_free_before_drain_before_payg():
    """Free-daily (1) sorts BEFORE drain-then-park (3) BEFORE flat-sub (2)
    BEFORE PAYG (4).  Within class 3, positive balance sorts first (drain
    priority)."""
    from charon.proxy_server import UpstreamRoute
    from charon.routing_policy import order_chain_by_funding_class

    chain = [
        UpstreamRoute("http://payg/v1", api_key="k", provider="payg"),
        UpstreamRoute("http://drain/v1", api_key="k", provider="drain"),
        UpstreamRoute("http://free/v1", api_key="k", provider="free-daily"),
        UpstreamRoute("http://flat/v1", api_key="k", provider="flat-sub"),
    ]

    fc_map = {"payg": 4, "drain": 3, "free-daily": 1, "flat-sub": 2}
    rem_map = {"drain": 5.0}

    ordered = order_chain_by_funding_class(
        chain,
        funding_class_fn=lambda p: fc_map.get(p),
        remaining_fn=lambda p: rem_map.get(p),
    )
    providers = [r.provider for r in ordered]

    # free-daily (1) first, then drain (3, positive), then flat (2), then PAYG (4)
    assert providers.index("free-daily") < providers.index("drain")
    assert providers.index("drain") < providers.index("flat-sub")
    assert providers.index("flat-sub") < providers.index("payg")


def test_order_chain_by_funding_class_drain_priority_within_class3():
    """Within class 3, providers with positive balance sort first; those at ~0
    sort last.  Free-daily (class 1) still sorts before all class 3."""
    from charon.proxy_server import UpstreamRoute
    from charon.routing_policy import order_chain_by_funding_class

    chain = [
        UpstreamRoute("http://drain-empty/v1", api_key="k", provider="drain-empty"),
        UpstreamRoute("http://free/v1", api_key="k", provider="free"),
        UpstreamRoute("http://drain-full/v1", api_key="k", provider="drain-full"),
    ]

    fc_map = {"drain-empty": 3, "free": 1, "drain-full": 3}
    rem_map = {"drain-empty": 0.0, "drain-full": 10.0}

    ordered = order_chain_by_funding_class(
        chain,
        funding_class_fn=lambda p: fc_map.get(p),
        remaining_fn=lambda p: rem_map.get(p),
    )
    providers = [r.provider for r in ordered]

    # free (class 1) first
    assert providers.index("free") == 0
    # drain-full (class 3, positive) before drain-empty (class 3, zero)
    assert providers.index("drain-full") < providers.index("drain-empty")


def test_funding_class_order_values():
    """funding_class_order returns the correct sort priority."""
    from charon.routing_policy import funding_class_order

    # Lower = preferred
    assert funding_class_order(1) < funding_class_order(3)   # free before drain
    assert funding_class_order(3) < funding_class_order(2)   # drain before flat
    assert funding_class_order(2) < funding_class_order(4)   # flat before PAYG
    assert funding_class_order(None) == 5   # unconfigured sorts last


def test_order_chain_empty_chain_returns_empty():
    from charon.routing_policy import order_chain_by_funding_class
    assert order_chain_by_funding_class([], funding_class_fn=lambda p: None) == []


def test_order_chain_single_provider_unchanged():
    from charon.proxy_server import UpstreamRoute
    from charon.routing_policy import order_chain_by_funding_class
    chain = [UpstreamRoute("http://x/v1", api_key="k", provider="only")]
    result = order_chain_by_funding_class(
        chain,
        funding_class_fn=lambda p: 3,
        remaining_fn=lambda p: 1.0,
    )
    assert result == chain

