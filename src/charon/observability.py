"""Observability module — export gateway events to JSONL, Prometheus, webhook,
and Langfuse backends.  Stdlib-only; thread-safe; non-blocking on failure.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from charon.types import ObsEvent, ObsTarget


class Observability:
    def __init__(self, config: dict | None = None):
        self._jsonl_path: Path | None = None
        self._webhook_url: str | None = None
        self._webhook_secret: str | None = None
        self._langfuse_public_key: str | None = None
        self._langfuse_secret_key: str | None = None
        self._langfuse_url: str = "https://cloud.langfuse.com/api/public/ingestion"
        self._counters: dict[str, int] = {}
        self._lock = threading.RLock()
        if config:
            if config.get("jsonl_path"):
                self._jsonl_path = Path(config["jsonl_path"])
            if config.get("webhook_url"):
                self._webhook_url = config["webhook_url"]
                self._webhook_secret = config.get("webhook_secret", "")
            if config.get("langfuse_url"):
                self._langfuse_url = config["langfuse_url"]
            if config.get("langfuse_public_key") and config.get("langfuse_secret_key"):
                self._langfuse_public_key = config["langfuse_public_key"]
                self._langfuse_secret_key = config["langfuse_secret_key"]

    def export(self, event: ObsEvent, targets: list[ObsTarget] | None = None) -> None:
        data = {
            "type": event.event_type,
            "provider": event.provider,
            "model": event.model,
            "timestamp": event.timestamp,
            "data": event.data,
        }
        if targets is None:
            targets = []
            if self._jsonl_path is not None:
                targets.append(ObsTarget.JSONL)
            if self._webhook_url is not None:
                targets.append(ObsTarget.WEBHOOK)
            if self._langfuse_public_key is not None:
                targets.append(ObsTarget.LANGFUSE)

        for target in targets:
            if target == ObsTarget.JSONL:
                self._export_jsonl(data)
            elif target == ObsTarget.PROMETHEUS:
                self._increment_counter(event.event_type)
            elif target == ObsTarget.WEBHOOK:
                self._export_webhook(data)
            elif target == ObsTarget.LANGFUSE:
                self._export_langfuse(event)

    def get_metrics(self) -> str:
        with self._lock:
            lines = [
                "# HELP charon_requests_total Total gateway requests by type",
                "# TYPE charon_requests_total counter",
            ]
            for event_type, count in sorted(self._counters.items()):
                lines.append(
                    f'charon_requests_total{{type="{event_type}"}} {count}'
                )
            return "\n".join(lines) + "\n"

    def _export_jsonl(self, data: dict) -> None:
        with self._lock:
            if self._jsonl_path is None:
                return
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(data, ensure_ascii=False) + "\n"
            with open(self._jsonl_path, "a", encoding="utf-8") as fh:
                fh.write(line)
            event_type = data.get("type", "")
            self._counters[event_type] = self._counters.get(event_type, 0) + 1

    def _increment_counter(self, event_type: str) -> None:
        with self._lock:
            self._counters[event_type] = self._counters.get(event_type, 0) + 1

    def _export_webhook(self, data: dict) -> None:
        if self._webhook_url is None:
            return
        try:
            body = json.dumps(data).encode("utf-8")
            secret_bytes = (self._webhook_secret or "").encode("utf-8")
            sig = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
            req = urllib.request.Request(
                self._webhook_url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Charon-Signature": sig,
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:  # noqa: BLE001 — non-blocking by design
            pass

    def _export_langfuse(self, event: ObsEvent) -> None:
        if self._langfuse_public_key is None:
            return
        ts = event.timestamp if event.timestamp else time.time()
        dt = datetime.fromtimestamp(ts, tz=UTC)
        body_dict = {
            "batch": [
                {
                    "type": "observation-create",
                    "body": {
                        "name": event.event_type,
                        "startTime": dt.isoformat(),
                        "metadata": event.data,
                    },
                }
            ]
        }
        try:
            body = json.dumps(body_dict).encode("utf-8")
            auth_str = base64.b64encode(
                f"{self._langfuse_public_key}:{self._langfuse_secret_key}".encode()
            ).decode()
            req = urllib.request.Request(
                self._langfuse_url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {auth_str}",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:  # noqa: BLE001 — non-blocking by design
            pass
