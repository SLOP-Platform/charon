from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import threading

from charon.observability import Observability
from charon.types import ObsEvent, ObsTarget


class TestJsonlExport:
    def test_writes_line(self, tmp_path):
        jsonl_path = tmp_path / "log" / "events.jsonl"
        obs = Observability({"jsonl_path": str(jsonl_path)})
        event = ObsEvent(
            event_type="request_start", provider="openai", model="gpt-4", timestamp=1.5
        )
        obs.export(event, targets=[ObsTarget.JSONL])

        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["type"] == "request_start"
        assert parsed["provider"] == "openai"
        assert parsed["model"] == "gpt-4"
        assert parsed["timestamp"] == 1.5

    def test_appends(self, tmp_path):
        jsonl_path = tmp_path / "events.jsonl"
        obs = Observability({"jsonl_path": str(jsonl_path)})
        obs.export(ObsEvent(event_type="e1"), targets=[ObsTarget.JSONL])
        obs.export(ObsEvent(event_type="e2"), targets=[ObsTarget.JSONL])

        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "e1"
        assert json.loads(lines[1])["type"] == "e2"

    def test_creates_parent_dirs(self, tmp_path):
        jsonl_path = tmp_path / "deep" / "nested" / "dir" / "events.jsonl"
        obs = Observability({"jsonl_path": str(jsonl_path)})
        obs.export(ObsEvent(event_type="e1"), targets=[ObsTarget.JSONL])

        assert jsonl_path.exists()


class TestPrometheusMetrics:
    def test_format(self):
        obs = Observability()
        obs.export(ObsEvent(event_type="request_start"), targets=[ObsTarget.PROMETHEUS])
        obs.export(ObsEvent(event_type="request_start"), targets=[ObsTarget.PROMETHEUS])
        obs.export(ObsEvent(event_type="request_complete"), targets=[ObsTarget.PROMETHEUS])

        metrics = obs.get_metrics()
        lines = metrics.strip().splitlines()
        assert lines[0] == "# HELP charon_requests_total Total gateway requests by type"
        assert lines[1] == "# TYPE charon_requests_total counter"
        assert 'charon_requests_total{type="request_complete"} 1' in metrics
        assert 'charon_requests_total{type="request_start"} 2' in metrics

    def test_counter_increments(self):
        obs = Observability()
        for _ in range(5):
            obs.export(ObsEvent(event_type="test_event"), targets=[ObsTarget.PROMETHEUS])

        metrics = obs.get_metrics()
        assert 'charon_requests_total{type="test_event"} 5' in metrics

    def test_jsonl_also_increments_counter(self, tmp_path):
        jsonl_path = tmp_path / "events.jsonl"
        obs = Observability({"jsonl_path": str(jsonl_path)})
        obs.export(ObsEvent(event_type="request_start"), targets=[ObsTarget.JSONL])
        obs.export(ObsEvent(event_type="request_start"), targets=[ObsTarget.JSONL])

        metrics = obs.get_metrics()
        assert 'charon_requests_total{type="request_start"} 2' in metrics


class TestWebhookTarget:
    @staticmethod
    def _start_server():
        captured: dict = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                captured["body"] = json.loads(raw)
                captured["headers"] = dict(self.headers)
                captured["path"] = self.path
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"OK")

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        host, port = srv.server_address[:2]
        url = f"http://{host}:{port}/webhook"
        return url, srv, captured

    def test_posted(self):
        url, srv, captured = self._start_server()
        try:
            obs = Observability({"webhook_url": url, "webhook_secret": "secret"})
            event = ObsEvent(event_type="request_start", provider="p", model="m", timestamp=1.0)
            obs.export(event, targets=[ObsTarget.WEBHOOK])

            assert captured["body"]["type"] == "request_start"
            assert captured["body"]["provider"] == "p"
            assert captured["body"]["model"] == "m"
            assert captured["body"]["timestamp"] == 1.0
            assert "X-Charon-Signature" in captured["headers"]
        finally:
            srv.shutdown()

    def test_signature_valid(self):
        body_dict = {
            "type": "test",
            "provider": None,
            "model": None,
            "timestamp": 0.0,
            "data": {},
        }
        body = json.dumps(body_dict).encode("utf-8")
        secret = b"my-secret"
        expected_sig = hmac.new(secret, body, hashlib.sha256).hexdigest()

        url, srv, captured = self._start_server()
        try:
            obs = Observability({"webhook_url": url, "webhook_secret": "my-secret"})
            obs.export(ObsEvent(event_type="test"), targets=[ObsTarget.WEBHOOK])

            assert captured["headers"]["X-Charon-Signature"] == expected_sig
        finally:
            srv.shutdown()

    def test_failure_non_blocking(self, tmp_path):
        obs = Observability({"webhook_url": "http://127.0.0.1:1/nonexistent"})
        obs.export(ObsEvent(event_type="test"), targets=[ObsTarget.WEBHOOK])


class TestLangfuseTarget:
    def _start_langfuse_server(self):
        captured: dict = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                captured["body"] = json.loads(raw)
                captured["headers"] = dict(self.headers)
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"OK")

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        host, port = srv.server_address[:2]
        url = f"http://{host}:{port}/api/public/ingestion"
        return url, srv, captured

    def test_format(self):
        url, srv, captured = self._start_langfuse_server()
        try:
            obs = Observability({
                "langfuse_public_key": "pk-test",
                "langfuse_secret_key": "sk-test",
                "langfuse_url": url,
            })
            event = ObsEvent(
                event_type="my_observation",
                provider="p",
                model="m",
                timestamp=1700000000.0,
                data={"key": "val"},
            )
            obs.export(event, targets=[ObsTarget.LANGFUSE])

            body = captured["body"]
            assert "batch" in body
            assert len(body["batch"]) == 1
            batch_item = body["batch"][0]
            assert batch_item["type"] == "observation-create"
            assert batch_item["body"]["name"] == "my_observation"
            assert "startTime" in batch_item["body"]
            assert batch_item["body"]["metadata"] == {"key": "val"}

            auth = captured["headers"].get("Authorization", "")
            assert auth.startswith("Basic ")
        finally:
            srv.shutdown()


class TestNoConfig:
    def test_does_nothing(self, tmp_path):
        obs = Observability()
        obs.export(ObsEvent(event_type="test"))
        assert obs.get_metrics() == (
            "# HELP charon_requests_total Total gateway requests by type\n"
            "# TYPE charon_requests_total counter\n"
        )

    def test_does_nothing_with_empty_config(self, tmp_path):
        obs = Observability({})
        obs.export(ObsEvent(event_type="test"))
        assert obs.get_metrics() == (
            "# HELP charon_requests_total Total gateway requests by type\n"
            "# TYPE charon_requests_total counter\n"
        )


class TestThreadSafety:
    def test_concurrent_jsonl_writes(self, tmp_path):
        import concurrent.futures

        jsonl_path = tmp_path / "concurrent.jsonl"
        obs = Observability({"jsonl_path": str(jsonl_path)})

        def write_n(n: int):
            for i in range(n):
                obs.export(ObsEvent(event_type=f"e{i % 10}"), targets=[ObsTarget.JSONL])

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(write_n, 50) for _ in range(8)]
            concurrent.futures.wait(futures)

        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) == 400
        for line in lines:
            parsed = json.loads(line)
            assert parsed["type"].startswith("e")
