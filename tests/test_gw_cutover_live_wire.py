"""GW-CUTOVER-LIVE-WIRE — the cutover was NOT performed. These are its guards.

WHY THERE IS NO CUTOVER IN THIS COMMIT
--------------------------------------
The ticket asks to replace ``forwarder.forward_with_failover`` + the stdlib
``http.server`` data-plane with ``litellm.Router`` serving LIVE traffic and to
delete ~650-750 LOC. Doing that TODAY would ship a **policy-missing money path**:
the four GW-BRIDGE legs re-hosted classification, streaming and park/cooldown
*reads*, but the adopted plane performs **zero money-state mutation** and does
**not** re-host the routing controls that decide WHERE spend lands. Measured,
not inferred (see the tests below):

  * ``litellm.Router`` as ``make_router`` configures it uses litellm's default
    ``simple-shuffle`` strategy — it picks uniformly at random among the
    deployments of a model_name and **discards the chain order entirely**. The
    cheapest-capable / funding-class order Charon computes would be thrown away
    on every request. That is a *spend* regression, and it fails the ticket's
    accept (3) MECHANICAL ORDERING PRESERVED by construction —
    see :func:`test_router_does_not_preserve_chain_order`.
  * Nothing in ``charon.litellm_plane`` calls ``record_spend``,
    ``record_exhaustion``, ``park``/``unpark``, ``spend_limiter.record`` or
    ``observer.record``. The ONLY writers of park state on the request path are
    ``forwarder.py`` (pre-flight drain-park and the deterministic-402 auto-park).
    Deleting the forwarder deletes both, so drain-then-park would stop advancing
    and a drained key would stay in rotation forever.
  * ``litellm.Router`` swallows the intermediate failed legs of its own internal
    failover, so the per-attempt ``observer.record`` / ``set_cooldown`` /
    ``failovers`` list that populates the ADR-0016 ``providers_tried`` envelope
    has no source on the Router path.

This is the same defect CLASS the 2026-07-03 silent double-bill belongs to —
money moving without Charon's accounting seeing it — so the prior stop-signal
still holds and the money path is left untouched. What lands instead is the
mechanized version of that signal: guards that (a) protect the live controls
from being deleted before they are re-hosted, and (b) go RED the moment a
half-migration is wired in.

RED means: the cutover precondition changed. Re-open GW-CUTOVER-LIVE-WIRE and
re-derive the gap; do not silence the guard.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src" / "charon"
_PLANE = _SRC / "litellm_plane"

# The live data-plane modules. If ANY of these grows a ``litellm_plane`` import,
# the money path is being migrated and the re-host guard below becomes binding.
_LIVE_DATA_PLANE = ("forwarder.py", "proxy_server.py", "gateway.py")

# Every money/routing control the hand-rolled live path owns today. The cutover
# may delete the hand-roll only once each of these has a re-hosted equivalent.
_LIVE_CONTROLS = {
    "spend-cap pre-flight": "spend_limiter.check",
    "spend-cap record": "spend_limiter.record",
    "balance record_spend": "balance_tracker.record_spend",
    "auto-park on deterministic 402": "record_exhaustion",
    "pre-flight drain park": "bt.park(",
    "unpark on top-up": "bt.unpark(",
    "usage observation": "observer.record",
    "live cheapest-first order": "order_pool_by_live_cost",
    "cooldown order": "order_by_cooldown",
    "funding-class order": "order_chain_by_funding_class",
    "cooldown write": "set_cooldown",
    "sole-leg guard": "_has_live_sibling",
    "capability exclusion": "capability_matrix",
    "max_concurrency / inflight": "inflight_inc",
    "ADR-0016 exhaustion envelope": "all_providers_exhausted",
    "semantic cache": "semantic_cache",
    "guardrail request scan": "guardrails",
    "tool-call repair": "tool_repair",
    "latency tracking": "latency_tracker",
    "session cost attribution": "X-Charon-Session",
}

# Mutators that move money or park state. ADR-0020 keeps these on Charon's side:
# the adopted plane is verify-only and must never become the source of record.
_MONEY_MUTATORS = (
    ".record_spend(",
    ".record_exhaustion(",
    ".park(",
    ".unpark(",
    "spend_limiter.record(",
    "observer.record(",
    ".observe(",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _code_lines(src: str) -> list[str]:
    """Source lines with full-line ``#`` comments dropped, so a marker that only
    appears in prose cannot satisfy a control check."""
    return [ln for ln in src.splitlines() if not ln.strip().startswith("#")]


def _plane_sources() -> dict[str, str]:
    return {p.name: _read(p) for p in sorted(_PLANE.glob("*.py"))}


# ── 1. the hand-rolled live money-path controls must still be live ──────────
def test_live_money_path_controls_are_all_present() -> None:
    """DELETE-GUARD for accept (4).

    The cutover deletes ~650-750 LOC from the hand-rolled money path. Every
    control listed in ``_LIVE_CONTROLS`` decides how much is spent or where it
    is spent; deleting one without a re-hosted equivalent silently changes the
    money path. This asserts they are all still reachable in the live modules.
    """
    assert len(_LIVE_CONTROLS) >= 15, "non-vacuity: the control set must be real"
    live = "\n".join(_read(_SRC / name) for name in _LIVE_DATA_PLANE)
    assert len(live) > 50_000, "non-vacuity: the live data-plane sources must be read"

    missing = sorted(name for name, marker in _LIVE_CONTROLS.items() if marker not in live)
    assert not missing, (
        "live money-path control(s) removed from the hand-rolled path: "
        f"{missing}. If this is the cutover, each control must be re-hosted on "
        "the Router path FIRST — see the module docstring."
    )


# ── 2. ADR-0020: the adopted plane never mutates money/park state ───────────
def test_litellm_plane_performs_no_money_state_mutation() -> None:
    """ADR-0020 verify-only invariant.

    Charon's own accounting REMAINS the source of record advancing
    BalanceTracker + drain-then-park. The adopted plane may classify and
    cross-check, never bill, park or record. A violation here means litellm
    became the money source of record — the exact inversion ADR-0020 rejected.
    """
    sources = _plane_sources()
    assert len(sources) >= 4, "non-vacuity: the plane's modules must be present"
    assert _MONEY_MUTATORS, "non-vacuity: the mutator set must be non-empty"

    offenders: list[str] = []
    for name, src in sources.items():
        for ln_no, line in enumerate(_code_lines(src), start=1):
            if '"""' in line or line.strip().startswith("*"):
                continue
            for mutator in _MONEY_MUTATORS:
                if mutator in line:
                    offenders.append(f"{name}:{ln_no}: {mutator}")
    assert not offenders, (
        "charon.litellm_plane mutated money/park state — ADR-0020 says it is "
        f"verify-only: {offenders}"
    )


# ── 3. a half-migrated money path is forbidden ──────────────────────────────
def test_live_wire_in_requires_the_controls_to_be_rehosted() -> None:
    """CUTOVER PRECONDITION.

    Today the live data plane holds zero references to ``litellm_plane`` — the
    plane is inert, so no request can bypass Charon's accounting. The moment a
    live module imports the plane, the money path is being migrated and every
    money/routing control must exist on the Router side too. This guard is what
    turns the stop-signal into a mechanism instead of prose.
    """
    live_refs = {
        name for name in _LIVE_DATA_PLANE
        if "litellm_plane" in "\n".join(_code_lines(_read(_SRC / name)))
    }
    plane_src = "\n".join(
        "\n".join(_code_lines(s)) for s in _plane_sources().values())
    assert plane_src, "non-vacuity: the plane sources must be readable"

    # The money/routing subset that MUST be re-hosted before any live wire-in.
    required = {
        "auto-park on deterministic 402": "record_exhaustion",
        "balance record_spend": "record_spend",
        "spend-cap record": "spend_limiter",
        "usage observation": "observer.record",
        "live cheapest-first order": "order_pool_by_live_cost",
        "cooldown order": "order_by_cooldown",
        "capability exclusion": "capability_matrix",
        "max_concurrency / inflight": "inflight_count",
        "ADR-0016 providers_tried population": "retry_after_hint",
    }
    assert len(required) >= 8, "non-vacuity: the required re-host set must be real"
    not_rehosted = sorted(k for k, marker in required.items() if marker not in plane_src)

    assert not live_refs or not not_rehosted, (
        f"the live data plane {sorted(live_refs)} routes through charon.litellm_plane "
        f"but these money/routing controls are NOT re-hosted there: {not_rehosted}. "
        "That is a half-migrated money path — the 2026-07-03 defect class."
    )


# ── 4. the Router discards Charon's chain order (accept (3) blocker) ────────
def test_router_does_not_preserve_chain_order() -> None:
    """MEASURED blocker for accept (3) MECHANICAL ORDERING PRESERVED.

    ``make_router`` does not pass ``routing_strategy``, so ``litellm.Router``
    uses its default ``simple-shuffle`` and selects uniformly at random among a
    model_name's deployments. Charon's cheapest-capable / funding-class chain
    order is therefore DISCARDED on the Router path, and the hand-rolled
    ordering must stay live.

    If ``make_router`` ever pins an order-preserving strategy this test skips
    the measurement — but the live-ordering requirement below still holds until
    the ordering itself is re-hosted.
    """
    pytest.importorskip("litellm")
    from litellm import Router

    from charon.litellm_plane import litellm_router as lr

    forwarder_src = _read(_SRC / "forwarder.py")
    assert "order_pool_by_live_cost" in forwarder_src and "order_by_cooldown" in forwarder_src, (
        "the live cheapest-first + cooldown ordering left forwarder.py; if it moved "
        "to the Router path, re-derive this guard"
    )

    if "routing_strategy" in _read(_PLANE / "litellm_router.py"):
        pytest.skip("make_router now pins a routing strategy — re-derive the ordering guard")

    model_list = [
        {"model_name": "m", "litellm_params": {
            "model": f"openai/{tag}", "api_base": f"http://127.0.0.1:900{i}",
            "api_key": f"k{i}"}}
        for i, tag in enumerate("abc", start=1)
    ]
    router = Router(
        model_list=model_list,
        cooldown_time=60.0,
        allowed_fails=lr.DEFAULT_ALLOWED_FAILS,
        num_retries=lr.DEFAULT_NUM_RETRIES,
        retry_after=60,
        set_verbose=False,
    )
    assert router.routing_strategy == "simple-shuffle"

    picks = {
        router.get_available_deployment(model="m")["litellm_params"]["model"]
        for _ in range(200)
    }
    assert len(picks) > 1, (
        "the Router now appears to honor model_list order — the accept (3) "
        "blocker may be resolved; re-open GW-CUTOVER-LIVE-WIRE and re-derive"
    )


# ── 5. e2e: the guarded Router serve path reshapes the upstream body ────────
class _StubUpstream(BaseHTTPRequestHandler):
    BODY = json.dumps({
        "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "ma",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        "provider": "stub-provider", "system_fingerprint": "fp_1",
    }).encode()

    def log_message(self, *args) -> None:  # keep pytest output clean
        pass

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.BODY)))
        self.end_headers()
        self.wfile.write(self.BODY)


def test_guarded_router_e2e_preserves_upstream_keys_but_is_not_byte_compatible() -> None:
    """e2e through the GUARDED serve path against a real loopback upstream.

    Two facts, both load-bearing for the cutover:

    * PERMANENT INVARIANT — the Router path must never DROP an upstream key
      (a provider-specific field silently vanishing is a contract break for
      clients that read it).
    * accept (1) BYTE-COMPAT is NOT met: litellm's ``ModelResponse`` dump adds
      fields the upstream never sent, so the relayed bytes differ from the
      hand-rolled path's verbatim relay.
    """
    pytest.importorskip("litellm")
    from litellm import Router

    from charon.litellm_plane import complete_via_router_guarded

    server = HTTPServer(("127.0.0.1", 0), _StubUpstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        router = Router(
            model_list=[{"model_name": "ma", "litellm_params": {
                "model": "openai/ma",
                "api_base": f"http://127.0.0.1:{server.server_address[1]}",
                "api_key": "k"}}],
            cooldown_time=60.0, allowed_fails=3, num_retries=1, set_verbose=False,
        )
        guarded = complete_via_router_guarded(
            router, {"model": "ma", "messages": [{"role": "user", "content": "x"}]})
    finally:
        server.shutdown()

    upstream = json.loads(_StubUpstream.BODY)
    served = guarded.response
    assert served.get("choices"), "non-vacuity: a real completion must have come back"
    assert guarded.downgrade is False, "the stub returns the requested model — no downgrade"

    dropped = sorted(set(upstream) - set(served))
    assert not dropped, f"the Router serve path DROPPED upstream key(s): {dropped}"

    added = sorted(set(served) - set(upstream))
    assert added, (
        "the Router response now matches the upstream shape exactly — accept (1) "
        "byte-compat may be satisfiable; re-open GW-CUTOVER-LIVE-WIRE and re-derive"
    )
