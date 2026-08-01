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


def test_disappeared_model_marked_unavailable(tmp_path: Path) -> None:
    """A model that was in a prior poll but is absent from a subsequent poll
    is marked ``enabled: false, refresh_disabled: true`` in models.json —
    it is NOT silently left routable."""
    providers_cfg = {"rotprov": {"base_url": "http://rp.test/v1"}}

    seen: dict[str, list[dict]] = {
        "first":  [{"id": "rotated-out", "free": True}],
        "second": [{"id": "still-here", "free": True}],
    }
    poll_order = ["first", "second"]
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
    assert second_raw["rotated-out"].get("refresh_disabled") is True


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
