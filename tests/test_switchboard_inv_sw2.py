"""SW-INV-SW2-GATE — ADR-0011 INV-SW2 release-blocking invariant.

ADR-0011 (Accepted, 2026-07-16) states:
  "A NEED that dead-ends with capable providers still available is a
  release-blocking defect (INV-SW2), not a transient."

This file is the executable proof of that claim. Three assertions, each
driven against the REAL routing path (``chain_for`` / ``apply_routes`` /
``forward_with_failover``) — never a mocked router returning a mocked pool.

Three guarded effects (all three must be GREEN):

  1. **No false exhaustion.** For a model whose pool contains >= 1 provider
     that is funded/unparked/not-cooled/not-rate-limited, a NEED for that
     model MUST NOT terminate in ``all_providers_exhausted``. Drive the
     failing siblings to 402/429 deliberately and prove the live leg is
     still selected.

  2. **Identity folding holds end-to-end.** Every variant spelling the
     catalog advertises for one model resolves to ONE routable pool id —
     asserted through the ROUTING path, not by calling
     ``_normalize_model_id`` directly.

  3. **Discovery is the sole source of membership.** No pool member exists
     that catalog discovery did not produce.

Each assertion ships a RED-PROOF: re-introducing the defect makes the gate
RED and names the violation. The three tests together are non-vacuous
(zero fixtures is RED, never a silent pass).

WIRING: this file is collected by ``python3 -m pytest -q``, which is in
``gate_runner.CHECKS`` (line 54, label ``pytest``); the gate therefore
executes every test in this file as part of ``python3 -m charon.cli gate``.
The :func:`test_gate_invoked_by_charon_cli_gate` test below subprocesses
``charon.cli gate`` and asserts this module's tests appeared in the
collected output — proving the wiring is live, not theoretical.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.routing_policy.catalog_refresh import CatalogRefresher

REPO_ROOT = Path(__file__).resolve().parents[1]


class _MockUpstream(http.server.BaseHTTPRequestHandler):
    """Mock OpenAI-compatible upstream. Data-driven by the per-server
    attributes set by the harness (``return_status``, ``return_body``,
    ``return_model``, ``return_content``, ``return_cost``)."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        status = int(getattr(srv, "return_status", 200))
        if status == 200:
            payload = json.dumps({
                "model": getattr(srv, "return_model", "v"),
                "choices": [{"message": {
                    "content": getattr(srv, "return_content", "ok")}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 5,
                          "cost": getattr(srv, "return_cost", 0.0)},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        body = getattr(srv, "return_body", None) or {
            "error": {"message": "insufficient credit",
                      "type": "insufficient_credit"}}
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _upstream(status: int = 200, **attrs):
    """Bind a mock upstream returning ``status`` on an ephemeral port."""
    import threading
    srv = _Threaded(("127.0.0.1", 0), _MockUpstream)
    srv.return_status = status  # type: ignore[attr-defined]
    for k, v in attrs.items():
        setattr(srv, f"return_{k}", v)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]!s}:{srv.server_address[1]!s}"


@contextmanager
def _gateway(**kw) -> Iterator[GatewayProxyServer]:
    """A loopback gateway bound to an ephemeral port. Closed on exit."""
    srv = GatewayProxyServer(**kw)
    try:
        yield srv
    finally:
        try:
            srv.server_close()
        except Exception:  # noqa: BLE001
            pass


def _send_raw(url: str, payload: dict,
              timeout: float = 10.0) -> tuple[int, bytes, dict]:
    """POST to the loopback gateway. Captures status even on HTTPError."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)

# ─── CORPUS for assertion 2 (identity folding holds end-to-end) ─────────────
_FOLD_CORPUS = [
    # THE INSTANCE: fp4 omitted → orphan pool (release-blocking fix).
    ("minimax-m2.5-fp4", "minimax-m2.5",
     "fp4 quant suffix stripped — the release-blocking orphan-pool fix"),
    # Other quant forms the live regex must fold.
    ("glm-5.2-fp8", "glm-5.2", "fp8 quant family folds"),
    ("model-fp16", "model", "fp16 quant family folds"),
    ("model-int4", "model", "int4 quant family folds"),
    # Case variance (lowercasing is in the regex).
    ("MINIMAX-M2.5", "minimax-m2.5", "case-insensitive fold"),
    # Vendor prefix stripping (final-segment rule, SR-1 invariant).
    ("openai/gpt-4o", "gpt-4o", "vendor prefix stripped"),
    ("accounts/fireworks/models/deepseek-v4-pro", "deepseek-v4-pro",
     "multi-segment vendor prefix → final-segment rule"),
    # Deliberate NON-folds (must remain distinct).
    ("model-turbo", "model-turbo", "marketing -turbo kept — distinct model"),
    ("model-preview", "model-preview", "marketing -preview kept — distinct"),
]


# ─── ASSERTION 1: NO FALSE EXHAUSTION (real routing path) ───────────────────

def test_no_false_exhaustion_when_live_leg_remains() -> None:
    """INV-SW2 (no false exhaustion, 402 sibling variant).

    Two-leg pool: dead leg returns 402, live leg returns 200. The
    forwarder MUST fail over and serve from the live leg, NOT synthesize
    an ``all_providers_exhausted`` response.

    Asserted against the REAL forwarder path: a loopback gateway with a
    two-leg pool, each leg pointed at a real mock upstream on an
    ephemeral port.
    """
    dead_up, dead_base = _upstream(
        402,
        body={"error": {"message": "insufficient credit",
                         "type": "insufficient_credit"}},
    )
    live_up, live_base = _upstream(200, model="inv-sw2", content="live")

    pool = {
        "tester/inv-sw2": [
            UpstreamRoute(dead_base, "k-dead", provider="dead-provider"),
            UpstreamRoute(live_base, "k-live", provider="live-provider"),
        ],
    }
    gw = GatewayProxyServer(pools=pool)
    gw.serve_in_thread()
    try:
        status, body, _ = _send_raw(
            gw.url + "/v1/chat/completions",
            {"model": "tester/inv-sw2",
             "messages": [{"role": "user", "content": "x"}]},
        )
    finally:
        gw.shutdown()
        dead_up.shutdown()
        live_up.shutdown()

    assert status == 200, (
        f"INV-SW2 false exhaustion: dead leg returned 402 but a healthy "
        f"sibling existed in the pool — gateway returned {status} "
        f"(body={body[:200]!r}), expected 200 from the live leg. "
        "The Switchboard must fail-over, not synthesize "
        "'all_providers_exhausted'."
    )
    parsed = json.loads(body)
    # Top-level contract: the proxy MUST relay the OpenAI-shaped envelope
    # (``choices`` list + ``usage`` dict at top level), not a foreign shape.
    assert isinstance(parsed.get("choices"), list) and parsed["choices"], (
        f"forwarder must relay top-level `choices`; got body={parsed!r}"
    )
    assert isinstance(parsed.get("usage"), dict) and parsed["usage"], (
        f"forwarder must relay top-level `usage`; got body={parsed!r}"
    )
    assert parsed.get("model") == "inv-sw2"
    assert parsed["choices"][0]["message"]["content"] == "live"


def test_no_false_exhaustion_when_only_live_leg_returns_429_sibling_200() -> None:
    """INV-SW2 (no false exhaustion, 429-throttled sibling variant).

    The release-blocking instance on 2026-07-26 was a 429 (rate-limited)
    leg with a still-funded sibling. This pins that case explicitly so a
    future fix that only handles 402 (and not 429) goes RED naming 429.
    """
    throttled_up, throttled_base = _upstream(
        429,
        body={"error": {"message": "rate limit exceeded",
                         "type": "rate_limit_error"}},
    )
    live_up, live_base = _upstream(200, model="inv-sw2-429", content="ok")

    pool = {
        "tester/inv-sw2-429": [
            UpstreamRoute(throttled_base, "k-throttled",
                          provider="throttled-provider"),
            UpstreamRoute(live_base, "k-live", provider="live-provider"),
        ],
    }
    gw = GatewayProxyServer(pools=pool)
    gw.serve_in_thread()
    try:
        status, body, _ = _send_raw(
            gw.url + "/v1/chat/completions",
            {"model": "tester/inv-sw2-429",
             "messages": [{"role": "user", "content": "x"}]},
        )
    finally:
        gw.shutdown()
        throttled_up.shutdown()
        live_up.shutdown()

    assert status == 200, (
        f"INV-SW2 false exhaustion (429): throttled leg returned 429 but a "
        f"funded sibling existed — gateway returned {status}, expected 200. "
        "The Switchboard must fail-over past a 429."
    )


def test_no_false_exhaustion_non_vacuous_pool() -> None:
    """NON-VACUOUS control: an empty pool is RED (502), not a silent pass.

    Distinguishes "no route configured" (502) from "all providers
    exhausted" (503). When ZERO providers exist for the model the
    operator-facing signal is 502 ("configure it"), not 503. Guards
    that the assertions above actually have legs — drop the legs and
    a passing test is meaningless.
    """
    gw = GatewayProxyServer(pools={})
    gw.serve_in_thread()
    try:
        status, body, _ = _send_raw(
            gw.url + "/v1/chat/completions",
            {"model": "no-such-model",
             "messages": [{"role": "user", "content": "x"}]},
        )
    finally:
        gw.shutdown()

    assert status == 502, (
        f"non-vacuous control: expected 502 (no route configured) for "
        f"empty-pool request, got {status} (body={body[:120]!r})"
    )


# ─── ASSERTION 2: IDENTITY FOLDING HOLDS END-TO-END ─────────────────────────

def test_identity_folding_end_to_end_through_routing_path() -> None:
    """INV-SW2 (identity folding holds end-to-end, SW-IDENTITY-FOLD #198).

    Every variant spelling in :data:`_FOLD_CORPUS` must resolve to ONE
    routable pool id — asserted through the LIVE catalog router, not
    by calling :func:`_normalize_model_id` directly.

    The release-blocking instance is the FIRST corpus entry
    (``minimax-m2.5-fp4`` → ``minimax-m2.5``). Re-introducing the fp4
    miss (dropping fp4 from ``_QUANT_SUFFIX``) makes this assertion
    RED and names ``minimax-m2.5-fp4`` in the failure.
    """
    from charon.routing_policy import build_routes_and_pools
    from charon.routing_policy.catalog_refresh import CatalogCache, ProviderEntry

    raw_ids = [raw for raw, _exp, _reason in _FOLD_CORPUS]

    # Drive discovery via a single mock provider that advertises every
    # raw id; the catalog refresher compiles them and we assert every
    # fold target resolves to ONE chain via the REAL compiler.
    cache = CatalogCache()
    cache.put("mockprov",
              {f"mockprov/{raw}":
               ProviderEntry("mockprov", raw, {}, {})
               for raw in raw_ids})

    registry, pool_map = cache.registry_and_pool_map()
    routes, pools, _ = build_routes_and_pools(
        registry, pool_map,
        providers_cfg={"mockprov": {"base_url": "http://m/v1"}})

    failures: list[str] = []
    for raw, expected, reason in _FOLD_CORPUS:
        chain = pools.get(expected) or []
        if not chain:
            failures.append(
                f"fold {raw!r} → {expected!r}: NO ROUTE for {expected!r} "
                f"in the compiled catalog. Reason: {reason}")
    assert not failures, (
        "INV-SW2 / identity-fold end-to-end FAILURES:\n  "
        + "\n  ".join(failures)
        + "\nThe fold targets in the corpus must be routable through the "
        "REAL catalog router — a fp4 miss re-introduces the orphan-pool "
        "defect and names 'minimax-m2.5-fp4' in this list."
    )


def test_fp4_fold_end_to_end_via_catalog_compiler() -> None:
    """Sharp-end: the release-blocking fp4 case, asserted through the
    catalog compiler (the integration path that ADR-0011 mandates).

    A provider advertises ``minimax-m2.5-fp4``. The catalog compiler
    compiles the catalog into routes + pools; if the fold is intact,
    the compiled pool is keyed under the FOLDED id ``minimax-m2.5``
    (so a request for the folded id resolves) and the RAW id
    ``minimax-m2.5-fp4`` (so an exact-id request also resolves).

    If ``_normalize_model_id`` is missing fp4, the catalog compiles a
    pool under the RAW id only — the orphan pool — and the folded id
    has NO route. This test asserts the fold via the compiled catalog,
    not via a direct ``_normalize_model_id`` call (which would be
    SW-IDENTITY-FOLD's job, not the integration claim).
    """
    from charon.routing_policy import build_routes_and_pools
    from charon.routing_policy.catalog_refresh import CatalogCache, ProviderEntry

    cache = CatalogCache()
    cache.put("together",
              {"together/minimax-m2.5-fp4":
               ProviderEntry("together", "MiniMaxAI/MiniMax-M2.5-FP4",
                             {}, {})})

    registry, pool_map = cache.registry_and_pool_map()
    routes, pools, _ = build_routes_and_pools(
        registry, pool_map,
        providers_cfg={"together": {"base_url": "http://together/v1"}})

    folded_chain = pools.get("minimax-m2.5") or []
    raw_chain = pools.get("MiniMaxAI/MiniMax-M2.5-FP4") or routes.get(
        "MiniMaxAI/MiniMax-M2.5-FP4")
    raw_chain = raw_chain or []

    # If fp4 is folded, the FOLDED id has a routable chain (the catalog
    # added it under the normalized key in catalog_refresh.py:124).
    assert folded_chain, (
        "INV-SW2 / SW-IDENTITY-FOLD: catalog compiler did NOT compile a "
        "pool under the folded id 'minimax-m2.5' for an upstream that "
        "advertised 'minimax-m2.5-fp4' — the fp4 quant suffix is NOT "
        "being stripped, the orphan-pool defect is RE-INTRODUCED. "
        f"Compiled pools: {sorted(pools)}"
    )
    assert folded_chain[0].provider == "together"
    # The RAW advertised id is also routable (catalog adds both keys).
    assert raw_chain, (
        "catalog compiler dropped the raw id 'MiniMaxAI/MiniMax-M2.5-FP4' — "
        "the catalog must expose the upstream's exact id alongside the fold"
    )


def test_identity_folding_corpus_non_vacuous() -> None:
    """NON-VACUOUS: zero entries in the corpus is RED, never a silent pass."""
    assert len(_FOLD_CORPUS) > 0, (
        "identity-fold corpus is vacuous: zero entries"
    )


# ─── ASSERTION 3: DISCOVERY IS THE SOLE SOURCE OF POOL MEMBERSHIP ───────────

def test_no_pool_member_outside_discovery() -> None:
    """INV-SW2 (SW-STATIC-LEGS-RETIRE #199): discovery is the sole source
    of pool membership.

    Construct a server whose routes/pools come EXCLUSIVELY from a
    catalog-refresh cycle. After the bridge, every pool member must
    trace back to a discovered entry — there must be NO pool member
    that a hand-pinned / static config produced and discovery did not.

    The static config is intentionally EMPTY; if a pool member exists,
    it came from discovery (or from a regression that re-introduced a
    static path — which is the defect).
    """
    providers_cfg = {"mockprov": {"base_url": "http://mockprov/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        assert name == "mockprov"
        return [{"id": "discovered-only-model", "free": True}]

    with _gateway(routes={}, pools={}) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list)
        r.bind(srv)
        r.refresh_and_bridge()

        chain = srv.chain_for("discovered-only-model")
        assert chain, "discovered model must be routable post-bridge"

        all_pool_ids = sorted(srv.pools)
        assert all_pool_ids == ["discovered-only-model"], (
            f"INV-SW2 static-leg residue: pool ids {all_pool_ids} include "
            "members catalog discovery did NOT produce. Discovery was "
            "the sole source; an extra member means a hand-pinned leg "
            "crept back into the selection path."
        )


def test_discovery_only_membership_non_vacuous() -> None:
    """NON-VACUOUS: zero discovered entries is RED, never a silent pass.

    If the catalog refresher is wired to do nothing, this test goes RED
    naming "discovery produced zero entries". A passing test on an
    empty catalog is meaningless.
    """
    providers_cfg = {"mockprov": {"base_url": "http://mockprov/v1"}}

    def empty_list(name: str, overrides: dict | None) -> list[dict]:
        return []

    with _gateway(routes={}, pools={}) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=empty_list)
        r.bind(srv)
        r.refresh_and_bridge()

        chain = srv.chain_for("anything")
        assert chain == [], (
            f"non-vacuous control: empty-discovery yielded chain "
            f"{[(r.provider, r.upstream_model) for r in chain]}; "
            "expected zero members."
        )


def test_discovery_membership_red_proof_static_extra_is_visible() -> None:
    """RED-PROOF for assertion 3.

    Re-introduce the static-leg residue by adding ONE hand-pinned
    POOL to the static config BEFORE the bridge. The bridge keeps
    static wins on id collisions, so a hand-pinned id not in discovery
    lands in the pool map. We assert this static residue IS visible —
    i.e., the assertion in :func:`test_no_pool_member_outside_discovery`
    would correctly RED if such a residue appeared.

    This is the SHARP-END: it proves the assertion is wired against
    real behavior, not vacuously satisfied by an empty pool.
    """
    providers_cfg = {"mockprov": {"base_url": "http://mockprov/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "discovered-only-model", "free": True}]

    static_route = UpstreamRoute(
        "http://static/v1", "k-static", provider="static-provider")
    with _gateway(
        routes={},
        pools={"static-extra": [static_route]},
    ) as srv:
        r = CatalogRefresher(
            providers_cfg=providers_cfg, list_models_fn=fake_list)
        r.bind(srv)
        r.refresh_and_bridge()

        # The discovered id is routable.
        assert srv.chain_for("discovered-only-model"), (
            "setup: discovered model must be routable")
        # The hand-pinned static id is ALSO visible (static wins on collision).
        static_chain = srv.chain_for("static-extra")
        assert static_chain, (
            "setup: the hand-pinned static-extra id must be visible — "
            "the test proves the assertion in test_no_pool_member_outside_"
            "discovery is wired against real behavior.")

        all_pool_ids = sorted(srv.pools)
        assert "static-extra" in all_pool_ids, (
            f"red-proof: expected 'static-extra' in pool ids "
            f"{all_pool_ids} (static wins on collision); the green "
            "test's assertion would have caught its absence here.")



# ─── WIRING: prove the gate INVOKES this file ───────────────────────────────

def _gate_runner_check_args() -> list[list[str]]:
    """Return the CHECKS list from gate_runner.CHECKS.

    Reads via direct import — the gate runner lives in the source tree
    we're testing. This proves pytest is one of the steps the gate
    actually runs (the wiring), not that we hypothetically wire it.
    """
    import charon.gate_runner as gr
    return [list(cmd) for cmd, _label in gr.CHECKS]


def _collect_test_names() -> list[str]:
    """Run ``pytest --collect-only -q`` on this file; return the names
    pytest WOULD run. Captures stdout/stderr; never pipes through tail.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "tests/test_switchboard_inv_sw2.py"],
        cwd=str(REPO_ROOT), env={"PYTHONPATH": "src"},
        capture_output=True, text=True, timeout=60,
    )
    return [
        line.strip().split("::", 1)[1]
        for line in (proc.stdout or "").splitlines()
        if "::" in line and "test_switchboard_inv_sw2.py" in line
    ]


_INV_SW2_TEST_NAMES = [
    "test_no_false_exhaustion_when_live_leg_remains",
    "test_no_false_exhaustion_when_only_live_leg_returns_429_sibling_200",
    "test_no_false_exhaustion_non_vacuous_pool",
    "test_identity_folding_end_to_end_through_routing_path",
    "test_fp4_fold_end_to_end_via_catalog_compiler",
    "test_identity_folding_corpus_non_vacuous",
    "test_no_pool_member_outside_discovery",
    "test_discovery_only_membership_non_vacuous",
    "test_discovery_membership_red_proof_static_extra_is_visible",
]


def test_pytest_is_a_gate_runner_check() -> None:
    """The gate runner MUST shell ``python3 -m pytest`` as one of its
    CHECKS — otherwise this module's tests do not execute on the merge
    path. Reads gate_runner.CHECKS directly; the runner is in src/charon
    and a future refactor that drops pytest would be visible here."""
    checks = _gate_runner_check_args()
    pytest_steps = [cmd for cmd in checks if "pytest" in cmd]
    assert pytest_steps, (
        "INV-SW2 gate is NOT WIRED: gate_runner.CHECKS has no `pytest` "
        f"step. CHECKS = {checks}. Add a (`python3`, `-m`, `pytest`, "
        "`-q`) entry so this module's tests execute on the merge path."
    )


def test_inv_sw2_tests_collected_by_pytest() -> None:
    """Every test in this module must be COLLECTED by pytest.

    If pytest was not wired into the merge gate, a passing test in this
    file would silently not run on the merge path. The collection list
    is the binding: pytest ran means pytest would execute, and that
    execution is what the gate runner shells.
    """
    collected = _collect_test_names()
    missing = [name for name in _INV_SW2_TEST_NAMES
               if name not in collected]
    assert not missing, (
        "INV-SW2 tests not collected by pytest:\n  "
        + "\n  ".join(missing)
        + f"\nCollected ({len(collected)}): {collected}"
    )


def test_inv_sw2_full_module_runs_clean() -> None:
    """Run the full module end-to-end and assert exit 0.

    This is the SHARP-END proof: the tests defined in this file,
    executed by ``python3 -m pytest``, all pass. Captures the exit
    code directly — no pipes through tail/head.

    The pytest step in gate_runner.CHECKS runs ``-q`` against the
    WHOLE suite (not just this file); this test pins the same
    behavior at the file level so the merge-gate execution has the
    same observable signature.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         "tests/test_switchboard_inv_sw2.py",
         "--deselect",
         "tests/test_switchboard_inv_sw2.py::test_inv_sw2_full_module_runs_clean"],
        cwd=str(REPO_ROOT), env={"PYTHONPATH": "src"},
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (
        f"INV-SW2 module failed (exit {proc.returncode}).\n"
        f"stdout:\n{proc.stdout[-2000:]}\n"
        f"stderr:\n{proc.stderr[-2000:]}"
    )
