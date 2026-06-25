"""The read-only web service layer (ADR-0004 D7/R3) — token gating, the 501 run
refusal, and the dashboard. Skipped unless the [service] extra is installed
(FastAPI/httpx); the core gate stays stdlib-only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")  # FastAPI's TestClient needs it

from fastapi.testclient import TestClient  # noqa: E402

from charon import api  # noqa: E402
from charon.service.app import app  # noqa: E402

client = TestClient(app)
TOKEN = "s3cret-token"


def test_healthz_is_open() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ungated_when_token_unset(monkeypatch) -> None:
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)
    assert client.get("/v1/runs").status_code == 200


def test_token_gate_blocks_and_allows(monkeypatch) -> None:
    monkeypatch.setenv("CHARON_SERVICE_TOKEN", TOKEN)
    assert client.get("/v1/runs").status_code == 401          # no token
    assert client.get("/v1/config").status_code == 401
    assert client.get("/").status_code == 401
    # accepted via Authorization: Bearer …
    assert client.get("/v1/runs", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    # …and via ?token= (so a browser URL works)
    assert client.get(f"/v1/runs?token={TOKEN}").status_code == 200
    # a wrong token is rejected
    assert client.get("/v1/runs", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_runs_endpoint_refuses_execution(monkeypatch) -> None:
    monkeypatch.setenv("CHARON_SERVICE_TOKEN", TOKEN)
    h = {"Authorization": f"Bearer {TOKEN}"}
    r = client.post("/v1/runs", json={"goal": "x", "accept": ["true"]}, headers=h)
    assert r.status_code == 501 and "worker container" in r.json()["detail"]


def test_dashboard_is_self_contained_html(monkeypatch) -> None:
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "charon · ledger" in body
    assert "http://" not in body and "https://" not in body  # no external assets (zero egress)


def test_auto_docs_are_disabled(monkeypatch) -> None:
    # FastAPI's /docs, /redoc, /openapi.json are ungated + load a CDN — disabled.
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_runs_listing_reflects_a_real_ledger(monkeypatch, tmp_path: Path) -> None:
    # the endpoints read DEFAULT_STATE_DIR (.charon) relative to cwd
    monkeypatch.delenv("CHARON_SERVICE_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    out = api.run_task(goal="web demo", accept=["test -f hello.txt"],
                       backend_name="mock", autonomy="L1")  # state_dir defaults to .charon
    body = client.get("/v1/runs").json()
    ids = [r["task_id"] for r in body["runs"]]
    assert out["task_id"] in ids
    got = client.get(f"/v1/runs/{out['task_id']}").json()
    assert got["verified"] == ["a0"] and got["remaining"] == []
