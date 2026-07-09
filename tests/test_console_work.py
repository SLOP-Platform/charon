"""P5 — work/board panel: /charon/work endpoint, read-only, no secrets rendered,
token-gated, and the hot-path unchanged.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from charon.acceptance import AcceptanceCheck
from charon.console_work import gather_runs
from charon.gitutil import head
from charon.ledger import Checkpoint, Ledger
from charon.proxy_server import GatewayProxyServer


def _mk_ledger(state_dir: Path, repo: Path, task_id: str, goal: str) -> Ledger:
    checks = [AcceptanceCheck("a0", "test -f done.txt")]
    return Ledger.create(state_dir, task_id, goal, checks, str(repo), head(repo))


class TestGatherRuns:
    def test_returns_empty_for_missing_state_dir(self, tmp_path: Path) -> None:
        assert gather_runs(str(tmp_path / "nonexistent")) == []

    def test_returns_empty_for_empty_state_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "state"
        d.mkdir()
        assert gather_runs(str(d)) == []

    def test_returns_runs_from_ledger_dirs(self, state_dir: Path, git_repo: Path) -> None:
        led = _mk_ledger(state_dir, git_repo, "t1", "fix the thing")
        led.append_checkpoint(Checkpoint(1, "mock", None, ["a0"], []))  # verified a0
        runs = gather_runs(str(state_dir))
        assert len(runs) == 1
        r = runs[0]
        assert r["run_id"] == "t1"
        assert r["task_id"] == "t1"
        assert r["goal"] == "fix the thing"
        assert r["status"] == "complete"
        assert r["checkpoints_count"] == 1
        assert r["verified_count"] == 1
        assert r["remaining_count"] == 0
        assert r["lkg_ref"] != ""
        assert isinstance(r["usage"], dict)
        assert "tokens_in" in r["usage"]
        assert "tokens_out" in r["usage"]
        assert "cost_usd" in r["usage"]

    def test_in_progress_when_remaining(self, state_dir: Path, git_repo: Path) -> None:
        led = _mk_ledger(state_dir, git_repo, "t1", "wip")
        led.append_checkpoint(Checkpoint(1, "mock", None, [], ["a0"]))
        runs = gather_runs(str(state_dir))
        assert runs[0]["status"] == "in-progress"

    def test_in_progress_when_locked(self, state_dir: Path, git_repo: Path) -> None:
        led = _mk_ledger(state_dir, git_repo, "t1", "locked")
        led.append_checkpoint(Checkpoint(1, "mock", None, ["a0"], []))
        (led.root / "lock").write_text("pid=1 t=0")
        runs = gather_runs(str(state_dir))
        assert runs[0]["status"] == "in-progress"

    def test_skips_corrupt_ledger(self, state_dir: Path, git_repo: Path) -> None:
        _mk_ledger(state_dir, git_repo, "ok", "ok goal")
        # corrupt a second ledger
        bad = state_dir / "bad"
        bad.mkdir()
        (bad / "ledger.json").write_text("{ not json")
        runs = gather_runs(str(state_dir))
        assert len(runs) == 1
        assert runs[0]["run_id"] == "ok"


class TestWorkEndpoint:
    @staticmethod
    def _build_proxy(state_dir: Path, git_repo: Path, token: str = "tok",
                     ) -> GatewayProxyServer:
        _mk_ledger(state_dir, git_repo, "t1", "fix the thing")
        return GatewayProxyServer(
            upstream_base="http://127.0.0.1:1/v1",
            token=token,
            model_ids=["gpt-4"],
            host="127.0.0.1",
        )

    @staticmethod
    def _get(url: str, *, token: str | None = None) -> tuple[int, dict | str]:
        headers: dict[str, str] = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            url, headers=headers, method="GET",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                return resp.status, json.loads(resp.read())
            return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if "application/json" in exc.headers.get("Content-Type", ""):
                return exc.code, json.loads(exc.read())
            return exc.code, exc.read().decode("utf-8", "replace")

    def test_work_endpoint_returns_200_html(self, state_dir: Path, git_repo: Path,
                                            monkeypatch) -> None:
        monkeypatch.chdir(git_repo.parent)  # so .charon resolves relative to our files
        charon_link = Path(".charon")
        if not charon_link.exists():
            charon_link.symlink_to(state_dir)
        try:
            proxy = self._build_proxy(state_dir, git_repo)
            proxy.serve_in_thread()
            try:
                status, body = self._get(proxy.url + "/charon/work", token="tok")
                assert status == 200
                assert isinstance(body, str)
                assert "Charon Work" in body
            finally:
                proxy.shutdown()
        finally:
            if charon_link.exists():
                charon_link.unlink()

    def test_work_endpoint_json_mode(self, state_dir: Path, git_repo: Path,
                                     monkeypatch) -> None:
        monkeypatch.chdir(git_repo.parent)
        charon_link = Path(".charon")
        if not charon_link.exists():
            charon_link.symlink_to(state_dir)
        try:
            proxy = self._build_proxy(state_dir, git_repo)
            proxy.serve_in_thread()
            try:
                status, body = self._get(
                    proxy.url + "/charon/work?json=1", token="tok",
                )
                assert status == 200
                assert isinstance(body, dict)
                assert len(body["runs"]) == 1
                assert body["runs"][0]["run_id"] == "t1"
            finally:
                proxy.shutdown()
        finally:
            if charon_link.exists():
                charon_link.unlink()

    def test_work_endpoint_no_secrets_in_response(self, state_dir: Path, git_repo: Path,
                                                   monkeypatch) -> None:
        monkeypatch.chdir(git_repo.parent)
        charon_link = Path(".charon")
        if not charon_link.exists():
            charon_link.symlink_to(state_dir)
        try:
            proxy = self._build_proxy(state_dir, git_repo)
            proxy.serve_in_thread()
            try:
                _, body = self._get(
                    proxy.url + "/charon/work?json=1", token="tok",
                )
                raw = json.dumps(body)
                assert "secret" not in raw.lower()
                assert "Bearer" not in raw
                assert "api_key" not in raw.lower()
                assert "key_env" not in raw.lower()
                assert "upstream_base" not in raw.lower()
            finally:
                proxy.shutdown()
        finally:
            if charon_link.exists():
                charon_link.unlink()

    def test_work_endpoint_unauthenticated_redirects_to_login(self) -> None:
        # SR-13: an unauthenticated browser GET to a /charon GUI route no longer
        # returns raw 401 JSON — it 302-redirects to the friendly login page. The
        # _get helper follows the redirect, so we land on the login form (200 HTML).
        proxy = GatewayProxyServer(
            upstream_base="http://127.0.0.1:1/v1",
            token="secret-token",
            model_ids=["gpt-4"],
            host="127.0.0.1",
        )
        proxy.serve_in_thread()
        try:
            status, body = self._get(proxy.url + "/charon/work")
            assert status == 200
            assert isinstance(body, str)
            assert 'action="/charon/login"' in body
            assert "Sign in" in body
        finally:
            proxy.shutdown()

    def test_v1_models_still_works_alongside_work_panel(
            self, state_dir: Path, git_repo: Path, monkeypatch) -> None:
        """Hot path unchanged: /v1/models returns model list, unaffected by the
        work panel addition."""
        monkeypatch.chdir(git_repo.parent)
        charon_link = Path(".charon")
        if not charon_link.exists():
            charon_link.symlink_to(state_dir)
        try:
            proxy = self._build_proxy(state_dir, git_repo)
            proxy.serve_in_thread()
            try:
                status, body = self._get(
                    proxy.url + "/v1/models", token="tok",
                )
                assert status == 200
                assert isinstance(body, dict)
                assert body["object"] == "list"
                assert "data" in body
            finally:
                proxy.shutdown()
        finally:
            if charon_link.exists():
                charon_link.unlink()
