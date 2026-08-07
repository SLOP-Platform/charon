"""CATALOG-REFRESH-PERSIST — FAIL-ON-REVERT tests for the write-back path.

DONE CONTRACT — RED then GREEN, hermetic + offline (injectable poller, no real networks):

  a. A poll discovering a NEW model persists it, and it SURVIVES a restart.
     Revert the write-back → RED.  **This is the whole defect.**
  b. A model that disappears from a provider's /models is marked unavailable,
     not left routable.  (The Zen rotation case.)
  c. ``free`` and price fields from the poll land in the catalog — a
     provider-reported free model ends up ``free: true``.  (The
     ``free=False``-on-free-models bug.)
  d. MERGE-SAFETY (ANTI-OVER-BLOCK): an operator ``enabled: false`` and a
     hand-added entry both SURVIVE a refresh.  Revert → RED.
     Clobbering operator intent is worse than staleness.
  e. A provider whose poll FAILS keeps its last-good entries (guards the
     existing stale-but-usable behaviour from regressing) AND its failure is
     surfaced in the status summary.
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from charon.proxy_server import GatewayProxyServer
from charon.routing_policy.catalog_refresh import CatalogRefresher


@contextmanager
def _server(**kw) -> Iterator[GatewayProxyServer]:
    srv = GatewayProxyServer(**kw)
    try:
        yield srv
    finally:
        try:
            srv.server_close()
        except Exception:  # noqa: BLE001
            pass


# ── a. persist-new-model: survives a restart (THE core defect test) ──────────
def test_discovered_model_persists_and_survives_restart(tmp_path: Path) -> None:
    """A model discovered by the poller is written to models.json and survives
    a simulated restart (Refresher re-constructed against the same state dir).

    RED when the write-back is reverted: the file is absent or the model
    is missing from it after restart."""
    providers_cfg = {"newprov": {"base_url": "http://np.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "brand-new-model", "free": False,
                 "cost_input": 1.5e-6, "cost_output": 4.5e-6}]

    r = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=fake_list,
    )
    with _server(routes={}, pools={}) as srv:
        r.bind(srv)
        r.refresh_and_bridge()

    models_path = tmp_path / "models.json"
    assert models_path.exists(), (
        "models.json must be created by refresh_and_bridge — this is the defect")

    raw = json.loads(models_path.read_text())
    assert "brand-new-model" in raw, (
        "discovered model must be persisted in models.json")
    entry = raw["brand-new-model"]
    assert entry.get("provider") == "newprov"
    assert entry.get("upstream_model") == "brand-new-model"
    assert entry.get("free") is False
    assert entry.get("cost_input") == 1.5e-6
    assert entry.get("cost_output") == 4.5e-6
    assert entry.get("refreshed_via") == "newprov"
    assert entry.get("refreshed_at") is not None

    r2 = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=fake_list,
    )
    with _server(routes={}, pools={}) as srv2:
        r2.bind(srv2)
        r2.refresh_and_bridge()
    chain = srv2.chain_for("brand-new-model")
    assert chain, "model must be routable after a simulated restart"


# ── b. rotation: disappeared model marked unavailable ───────────────────────
def test_disappeared_model_marked_unavailable(tmp_path: Path) -> None:
    """A model that was in a prior poll but is absent from a subsequent poll
    is marked ``enabled: false, refresh_withdrawn: true`` in models.json — it is
    NOT silently left routable, and NOT marked ``refresh_disabled`` (that flag is
    the operator's opt-out; an auto-withdrawal must stay reversible so the model
    comes back on its own when the provider re-advertises it)."""
    providers_cfg = {"rotprov": {"base_url": "http://rp.test/v1"}}

    seen: dict[str, list[dict]] = {
        "first":  [{"id": "rotated-out", "free": True}],
        "second": [{"id": "still-here", "free": True}],
        "third":  [{"id": "rotated-out", "free": True}],
    }
    poll_order = ["first", "second", "third"]
    call_count = 0

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        nonlocal call_count
        phase = poll_order[min(call_count, len(poll_order) - 1)]
        call_count += 1
        return list(seen.get(phase, []))

    r = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=fake_list,
    )
    with _server(routes={}, pools={}) as srv:
        r.bind(srv)
        r.refresh_and_bridge()

    assert call_count == 1
    models_path = tmp_path / "models.json"
    first_raw = json.loads(models_path.read_text())
    assert "rotated-out" in first_raw
    assert first_raw["rotated-out"].get("enabled") is not False

    r.refresh_now()
    assert call_count == 2

    second_raw = json.loads(models_path.read_text())
    assert "rotated-out" in second_raw
    assert second_raw["rotated-out"].get("enabled") is False
    assert second_raw["rotated-out"].get("refresh_withdrawn") is True
    # NOT the operator opt-out flag — otherwise the withdrawal is permanent.
    assert second_raw["rotated-out"].get("refresh_disabled") is not True

    # The provider re-advertises it → it must come back WITHOUT a hand edit.
    r.refresh_now()
    assert call_count == 3
    third_raw = json.loads(models_path.read_text())
    assert third_raw["rotated-out"].get("enabled") is True
    assert not third_raw["rotated-out"].get("refresh_withdrawn")


# ── c. free-flag: provider free=True lands as free=True in catalog ───────────
def test_free_flag_from_provider_lands_in_catalog(tmp_path: Path) -> None:
    """A provider advertising ``free: true`` must produce ``free: true`` in
    models.json — fixing the ``free=False``-on-genuinely-free-models bug."""
    providers_cfg = {"freeprov": {"base_url": "http://fp.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "freebie", "free": True, "cost_input": 0.0}]

    r = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=fake_list,
    )
    with _server(routes={}, pools={}) as srv:
        r.bind(srv)
        r.refresh_and_bridge()

    models_path = tmp_path / "models.json"
    raw = json.loads(models_path.read_text())
    assert "freebie" in raw
    assert raw["freebie"].get("free") is True, (
        "provider-reported free model must get free=True in the catalog")


# ── d. merge-safety: operator intent survives refresh ─────────────────────────
def test_enabled_false_survives_refresh(tmp_path: Path) -> None:
    """An operator who sets ``enabled: false`` (via ``set_model_enabled`` or
    hand-edit) must find that flag still ``False`` after a refresh."""
    models_cfg = {"opmodel": {"provider": "opprov", "enabled": False}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "opmodel", "free": True}]

    models_path = tmp_path / "models.json"
    models_path.write_text(json.dumps(models_cfg))

    providers_cfg = {"opprov": {"base_url": "http://op.test/v1"}}
    r = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=fake_list,
    )
    with _server(routes={}, pools={}) as srv:
        r.bind(srv)
        r.refresh_now()

    raw = json.loads(models_path.read_text())
    assert "opmodel" in raw
    assert raw["opmodel"].get("enabled") is False, (
        "operator-set enabled:false must survive a refresh — this is the "
        "MERGE-SAFETY anti-over-block rule")


def test_hand_added_entry_survives_refresh(tmp_path: Path) -> None:
    """A hand-authored entry with ``upstream_base`` (P1/P2 direct) must NOT
    be overwritten by discovery on a matching model id."""
    models_cfg = {
        "handmodel": {
            "upstream_base": "http://my-endpoint.test/v1",
            "upstream_model": "my-real-id",
            "free": False,
            "cost_input": 9e-6,
        }
    }

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "handmodel", "free": True, "cost_input": 1e-6}]

    models_path = tmp_path / "models.json"
    models_path.write_text(json.dumps(models_cfg))

    providers_cfg = {"someprov": {"base_url": "http://sp.test/v1"}}
    r = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=fake_list,
    )
    with _server(routes={}, pools={}) as srv:
        r.bind(srv)
        r.refresh_now()

    raw = json.loads(models_path.read_text())
    assert "handmodel" in raw
    entry = raw["handmodel"]
    assert entry.get("upstream_base") == "http://my-endpoint.test/v1", (
        "hand-set upstream_base must survive a refresh")
    assert entry.get("upstream_model") == "my-real-id"
    assert entry.get("free") is False, (
        "hand-set free=False must survive a refresh (price not clobbered either)")
    assert entry.get("cost_input") == 9e-6, (
        "hand-set cost_input must survive a refresh")


# ── e. stale-but-usable on provider failure ─────────────────────────────────
def test_stale_but_usable_and_failure_surfaced(tmp_path: Path) -> None:
    """A provider whose poll FAILS keeps its last-good entries (stale-but-usable)
    and its failure is surfaced in the status summary."""
    providers_cfg = {"flaky": {"base_url": "http://f.test/v1"}}

    state = {"up": True}

    def flaky_list(name: str, overrides: dict | None) -> list[dict]:
        if not state["up"]:
            raise RuntimeError("provider unreachable")
        return [{"id": "keep-me", "free": True, "cost_input": 2e-6}]

    r = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=flaky_list,
    )
    with _server(routes={}, pools={}) as srv:
        r.bind(srv)
        r.refresh_and_bridge()
        assert srv.chain_for("keep-me"), "setup: model routable after first poll"

        state["up"] = False
        r.refresh_and_bridge()
        assert srv.chain_for("keep-me"), (
            "a failed refresh must keep last-good entries (stale-but-usable)")

    status = r.status_summary()
    assert "providers" in status
    assert "flaky" in status["providers"]
    prov_status = status["providers"]["flaky"]
    assert "failed" in prov_status, (
        "failed poll must surface failure in status summary")
    assert "keep-me" in prov_status["failed"] or "RuntimeError" in prov_status["failed"]


# ── f. status_summary reflects last refresh time ──────────────────────────────
def test_status_summary_shows_last_refresh_and_counts(tmp_path: Path) -> None:
    """status_summary() reports last_refresh timestamp and per-provider counts."""
    providers_cfg = {"sprov": {"base_url": "http://s.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "model-a", "free": False}, {"id": "model-b", "free": True}]

    r = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=fake_list,
    )
    with _server(routes={}, pools={}) as srv:
        r.bind(srv)
        before = time.time()
        r.refresh_and_bridge()
        after = time.time()

    status = r.status_summary()
    assert status["last_refresh"] is not None
    assert before <= status["last_refresh"] <= after
    assert status["providers"]["sprov"]["ok"] is True
    assert status["providers"]["sprov"]["models_discovered"] == 2


# ── g. id normalization: discovered and hand-id fold to same key ──────────────
def test_normalized_id_merge(tmp_path: Path) -> None:
    """A model discovered as ``My-Model`` (provider-returned) and a hand entry
    as ``mymodel`` (normalized) must merge, not duplicate."""
    models_cfg = {
        "mymodel": {
            "provider": "sprov",
            "upstream_model": "My-Model",
            "upstream_base": "http://s.test/v1",
        }
    }

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        return [{"id": "My-Model", "free": False, "cost_input": 1e-6}]

    models_path = tmp_path / "models.json"
    models_path.write_text(json.dumps(models_cfg))

    providers_cfg = {"sprov": {"base_url": "http://s.test/v1"}}
    r = CatalogRefresher(
        providers_cfg=providers_cfg,
        state_dir=tmp_path,
        list_models_fn=fake_list,
    )
    with _server(routes={}, pools={}) as srv:
        r.bind(srv)
        r.refresh_now()

    raw = json.loads(models_path.read_text())
    keys = list(raw.keys())
    assert len(keys) == 1, (
        f"normalized id merge should produce one key, got {keys}")
    assert "mymodel" in keys


# ══ MONEY-PATH ADVERSARIAL REGRESSIONS (catalog-wipe class) ═════════════════
# Each of these FAILED against the original WIP. A catalog wipe kills every
# route on the gateway, so "refuse to write" beats "write something".

def test_empty_200_poll_never_withdraws_catalog(tmp_path: Path) -> None:
    """A provider answering HTTP 200 with an EMPTY model list must NOT be
    believed. A lapsed key / downgraded plan / soft rate-limit all look exactly
    like this, and treating it as truth withdraws every model that provider
    serves — a total catalog wipe. Last-good must survive, and the provider must
    be reported as FAILED, not OK."""
    calls = {"n": 0}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"id": "keep-me", "free": True}, {"id": "keep-me-too"}]
        return []  # the attack

    r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=tmp_path,
                         list_models_fn=fake_list)
    r.refresh_now()
    after_good = json.loads((tmp_path / "models.json").read_text())
    assert set(after_good) == {"keep-me", "keep-me-too"}

    r.refresh_now()
    after_empty = json.loads((tmp_path / "models.json").read_text())
    assert set(after_empty) == {"keep-me", "keep-me-too"}
    for mid, entry in after_empty.items():
        assert entry.get("enabled") is not False, f"{mid} was withdrawn by an empty poll"
        assert entry.get("refresh_withdrawn") is not True

    # FAIL-LOUD: an empty poll is a failure, never a silent success.
    status = r.status_summary()
    assert "failed" in status["providers"]["p"]
    assert status["providers"]["p"].get("ok") is not True


def test_unreadable_models_json_is_never_overwritten(tmp_path: Path) -> None:
    """If the existing models.json cannot be parsed, the refresher must REFUSE
    to write. Falling back to ``{}`` and writing would replace a catalog we
    merely failed to READ with an empty one — every route dies."""
    models_path = tmp_path / "models.json"
    corrupt = '{"hand-tuned": {"provider": "p", "upstream_mo'   # truncated write
    models_path.write_text(corrupt)

    r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=tmp_path,
                         list_models_fn=lambda n, o: [{"id": "newly-found"}])
    r.refresh_now()

    assert models_path.read_text() == corrupt, "corrupt catalog was overwritten"

    # ...and it must SAY SO rather than degrade quietly.
    status = json.loads((tmp_path / "catalog_refresh_status.json").read_text())
    assert status["healthy"] is False
    assert "unreadable" in (status["persist_error"] or "")


def test_total_provider_failure_writes_no_empty_catalog(tmp_path: Path) -> None:
    """When every provider fails there is nothing to persist. The refresher must
    not create/overwrite models.json with ``{}``."""
    def boom(name: str, overrides: dict | None) -> list[dict]:
        raise RuntimeError("401 unauthorized")

    r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=tmp_path,
                         list_models_fn=boom)
    r.refresh_now()

    models_path = tmp_path / "models.json"
    assert not models_path.exists() or json.loads(models_path.read_text()) != {}, (
        "a total failure wrote an empty catalog")


def test_status_file_makes_cadence_observable_from_outside(tmp_path: Path) -> None:
    """BAR ITEM 2: an outside observer must be able to prove WHEN the refresher
    last ran and whether it worked, without reading logs or the process."""
    r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=tmp_path,
                         list_models_fn=lambda n, o: [{"id": "m1", "free": True}])
    before = time.time()
    r.refresh_now()

    status_path = tmp_path / "catalog_refresh_status.json"
    assert status_path.exists(), "no externally-observable cadence marker"
    status = json.loads(status_path.read_text())
    assert status["last_attempt"] >= before
    assert status["last_persist"] >= before
    assert status["healthy"] is True
    assert status["failed_providers"] == []
    assert status["providers"]["p"]["models_discovered"] == 1


def test_status_file_written_even_when_everything_fails(tmp_path: Path) -> None:
    """FAIL-LOUD: the cadence marker must be written on a FAILED cycle too —
    otherwise a refresher that has been dead for weeks is indistinguishable from
    one that just ran cleanly."""
    def boom(name: str, overrides: dict | None) -> list[dict]:
        raise RuntimeError("connection refused")

    r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=tmp_path,
                         list_models_fn=boom)
    r.refresh_now()

    status = json.loads((tmp_path / "catalog_refresh_status.json").read_text())
    assert status["healthy"] is False
    assert status["failed_providers"] == ["p"]
    assert "connection refused" in status["providers"]["p"]["failed"]


def test_free_flag_flip_is_persisted_and_detectable(tmp_path: Path) -> None:
    """§B4 catalog rot: ``minimax-m3-free`` billed real money despite ``-free``
    in its id. When a provider stops advertising a model as free, the catalog
    must record ``free: false`` — the name must never be what decides billing."""
    calls = {"n": 0}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"id": "minimax-m3-free", "free": True, "cost_input": 0.0}]
        return [{"id": "minimax-m3-free", "free": False, "cost_input": 0.15}]

    r = CatalogRefresher(providers_cfg={"p": {}}, state_dir=tmp_path,
                         list_models_fn=fake_list)
    r.refresh_now()
    assert json.loads((tmp_path / "models.json").read_text())["minimax-m3-free"]["free"] is True

    r.refresh_now()
    entry = json.loads((tmp_path / "models.json").read_text())["minimax-m3-free"]
    assert entry["free"] is False, "withdrawn free tier stayed 'free' in the catalog"
    assert entry["cost_input"] == 0.15


# ══ BAR ITEM 5: the GATE cannot be silently unregistered ════════════════════

def test_persist_safety_gate_is_registered() -> None:
    """The catalog-persist-safety gate must stay wired into BOTH the gate
    registry and the gate runner. Unregistering it is how this protection would
    rot back off."""
    root = Path(__file__).resolve().parents[1]
    gates = json.loads((root / "tools" / "gates.json").read_text())
    ids = [g["id"] for g in gates]
    assert "catalog-persist-safety" in ids, f"gate missing from gates.json: {ids}"

    runner = (root / "src" / "charon" / "gate_runner.py").read_text()
    assert "check_catalog_persist_safety" in runner, (
        "check_catalog_persist_safety.py not referenced in gate_runner.py CHECKS")
    assert (root / "tools" / "check_catalog_persist_safety.py").exists()


def test_persist_safety_gate_passes_against_current_code() -> None:
    """The gate must actually be GREEN here — a registered gate nobody runs is
    worse than no gate."""
    import subprocess
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/check_catalog_persist_safety.py"],
        cwd=root, capture_output=True, text=True, timeout=120, check=False)
    assert proc.returncode == 0, (
        f"catalog-persist-safety gate is RED:\n{proc.stdout}\n{proc.stderr}")
