"""GatewayReviewer — real consensus reviewer via the loopback Charon gateway.

Calls an OpenAI-compatible chat-completions endpoint (the local gateway running
on ``CHARON_REVIEW_BASE_URL``, defaulting to ``http://127.0.0.1:8080/v1``) and
asks the configured model to judge whether a completed unit's outcome has any
blocking issues.  All I/O is stdlib-only (``urllib.request``).

No provider keys go in the repo.  Config is read from env at call time:
  CHARON_REVIEW_BASE_URL  — gateway base URL  (default: http://127.0.0.1:8080/v1)
  CHARON_REVIEW_MODEL     — model id to use    (default: charon-reviewer)
  CHARON_GATEWAY_TOKEN    — Bearer token        (required if gateway token is set)

If either the base URL or gateway is unreachable, or the model returns an
unparseable verdict, this raises ``ReviewerError`` and the coordinator's
existing fail-closed path handles it.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from ..ports.reviewer import Findings, ReviewerError
from ..types import Outcome, WorkUnit

_DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
_DEFAULT_MODEL = "charon-reviewer"

_SYSTEM_PROMPT = """\
You are a code-change reviewer for an autonomous agent harness.
You receive a description of a work unit and the outcome of its execution.
Identify ONLY hard-blocking issues: security violations, broken contracts,
data-loss risks, or clear functional regressions.  Style and minor quality
issues are NOT blocking.
Reply with ONLY a JSON object with this shape (no markdown, no preamble):
{"blocking": ["<issue text>", ...]}
Return {"blocking": []} if there are no blocking issues.
"""


def _build_user_message(unit: WorkUnit, outcome: Outcome) -> str:
    parts = [
        f"Task goal: {unit.goal}",
        f"Task id: {unit.task_id}",
        f"Outcome status: {outcome.status.value}",
    ]
    if outcome.commit:
        parts.append(f"Commit produced: {outcome.commit}")
    if outcome.note:
        parts.append(f"Agent note: {outcome.note}")
    return "\n".join(parts)


def _parse_findings(text: str) -> Findings:
    """Parse model reply → Findings.  Unparseable ⇒ fail-closed (blocking)."""
    text = text.strip()
    try:
        obj: Any = json.loads(text)
        blocking = obj.get("blocking", [])
        if not isinstance(blocking, list):
            raise ValueError("blocking is not a list")
        return Findings(blocking=[str(b) for b in blocking])
    except (json.JSONDecodeError, ValueError, AttributeError):
        return Findings(blocking=[f"reviewer returned unparseable response: {text[:200]}"])


class GatewayReviewer:
    """Calls the loopback gateway's chat-completions endpoint to review a unit.

    ``base_url``, ``model``, and ``token`` default to env-var lookups so the
    caller can override in tests without environment mutation.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        token: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        raw_base = base_url or os.environ.get("CHARON_REVIEW_BASE_URL", _DEFAULT_BASE_URL)
        self._base_url = raw_base.rstrip("/")
        self._model = model or os.environ.get("CHARON_REVIEW_MODEL", _DEFAULT_MODEL)
        self._token = token if token is not None else os.environ.get("CHARON_GATEWAY_TOKEN")
        self._timeout_s = timeout_s

    def review(self, unit: WorkUnit, outcome: Outcome) -> Findings:
        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_message(unit, outcome)},
            ],
            "max_tokens": 256,
            "temperature": 0,
        }).encode()

        url = f"{self._base_url}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise ReviewerError(f"gateway HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ReviewerError(f"gateway unreachable: {exc.reason}") from exc
        except Exception as exc:
            raise ReviewerError(f"reviewer error: {exc}") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ReviewerError(f"unexpected gateway response shape: {exc}") from exc

        return _parse_findings(content)
