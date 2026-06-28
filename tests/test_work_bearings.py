"""WORK-AGENT-BEARINGS — ACP dispatch prompt carries goal + body + accept.

Asserts at the dispatch seam: the `session/prompt` text the AcpBackend sends
to the agent contains the goal, the ticket body, AND the acceptance criteria.
Pattern mirrors test_tier_lifecycle.py's stub-subprocess approach.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from charon import gitutil
from charon.adapters.acp import AcpBackend, _build_prompt
from charon.api import RichWorkUnit
from charon.types import Budget, Tier, WorkUnit

# ---------------------------------------------------------------------------
# Stub ACP agent: speaks ACP over stdin/stdout; writes the session/prompt
# text to the file named in the STUB_CAPTURE_FILE env var so the test can
# inspect it without subprocess stdout capture (stdout is the ACP channel).
# ---------------------------------------------------------------------------

_CAPTURE_STUB = textwrap.dedent("""\
    import json, os, sys

    capture = os.environ.get("STUB_CAPTURE_FILE", "")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method, mid = msg.get("method", ""), msg.get("id")
        if method == "session/new":
            res: dict = {"sessionId": "s1"}
        elif method == "session/prompt":
            if capture:
                parts = msg.get("params", {}).get("prompt", [])
                text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
                with open(capture, "w") as f:
                    f.write(text)
            res = {}
        else:
            res = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}) + "\\n")
        sys.stdout.flush()
""")


def _dispatch(
    stub: Path, worktree: Path, unit: WorkUnit, capture_file: Path
) -> str:
    """Run one dispatch with the capture stub; return the prompt text received."""
    backend = AcpBackend(
        command=[sys.executable, str(stub)],
        name="test-acp",
        passthrough_env={"STUB_CAPTURE_FILE": str(capture_file)},
    )
    try:
        backend.dispatch(unit, Tier.HIGH, Budget(), worktree, {})
    finally:
        backend.kill()
    if capture_file.exists():
        return capture_file.read_text()
    return ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def worktree(tmp_path: Path) -> Path:
    wt = tmp_path / "wt"
    wt.mkdir()
    gitutil.init_repo(wt)
    return wt


def test_dispatch_prompt_contains_goal_body_and_accept(
    tmp_path: Path, worktree: Path
) -> None:
    """The ACP agent receives goal + body + acceptance criteria in the prompt."""
    stub = tmp_path / "stub.py"
    stub.write_text(_CAPTURE_STUB)
    capture = tmp_path / "prompt.txt"

    unit = RichWorkUnit(
        task_id="bearings-test",
        goal="Fix the retry logic",
        body="The retry logic in retry.py uses a fixed delay.\nSwitch to exponential back-off.",
        accept_text="pytest tests/test_retry.py -q",
    )
    prompt = _dispatch(stub, worktree, unit, capture)

    assert "Fix the retry logic" in prompt
    assert "exponential back-off" in prompt
    assert "pytest tests/test_retry.py -q" in prompt
    assert "Acceptance" in prompt  # the template header is present


def test_dispatch_prompt_accept_matches_gate_checks(
    tmp_path: Path, worktree: Path
) -> None:
    """The accept text shown to the agent is the SAME text the gate would run
    (one source of truth — no divergence between shown and judged)."""
    stub = tmp_path / "stub.py"
    stub.write_text(_CAPTURE_STUB)
    capture = tmp_path / "prompt.txt"

    gate_checks = ["pytest tests/test_a.py -q", "ruff check src/"]
    accept_text = "\n".join(gate_checks)
    unit = RichWorkUnit(
        task_id="gate-parity",
        goal="Add linting",
        body="Wire ruff into CI.",
        accept_text=accept_text,
    )
    prompt = _dispatch(stub, worktree, unit, capture)

    for check in gate_checks:
        assert check in prompt, f"gate check {check!r} missing from agent prompt"


def test_dispatch_prompt_no_secrets(tmp_path: Path, worktree: Path) -> None:
    """Secrets (tokens, keys) must not appear in the dispatch prompt."""
    stub = tmp_path / "stub.py"
    stub.write_text(_CAPTURE_STUB)
    capture = tmp_path / "prompt.txt"

    unit = RichWorkUnit(
        task_id="no-leak",
        goal="Patch the gateway",
        body="Adjust the timeout.",
        accept_text="pytest -q",
    )
    prompt = _dispatch(stub, worktree, unit, capture)

    # prompt content comes solely from unit fields — no env vars or creds
    assert "sk-" not in prompt  # no OpenAI-style API key
    assert "ANTHROPIC_API_KEY" not in prompt
    assert "OPENAI_API_KEY" not in prompt
    assert "Bearer " not in prompt


def test_plain_work_unit_prompt_is_goal_only(tmp_path: Path, worktree: Path) -> None:
    """A plain WorkUnit (no body/accept_text) still works — just sends the goal.
    Backward-compatibility: existing callers that pass WorkUnit are unaffected."""
    stub = tmp_path / "stub.py"
    stub.write_text(_CAPTURE_STUB)
    capture = tmp_path / "prompt.txt"

    unit = WorkUnit(task_id="plain", goal="Do the thing")
    prompt = _dispatch(stub, worktree, unit, capture)

    assert prompt == "Do the thing"


# ---------------------------------------------------------------------------
# Unit test for the prompt-builder in isolation (no subprocess needed).
# ---------------------------------------------------------------------------


def test_build_prompt_goal_only() -> None:
    unit = WorkUnit(task_id="t", goal="Just the goal")
    assert _build_prompt(unit) == "Just the goal"


def test_build_prompt_with_body_and_accept() -> None:
    unit = RichWorkUnit(
        task_id="t",
        goal="Goal text",
        body="Body text.",
        accept_text="pytest -q",
    )
    prompt = _build_prompt(unit)
    assert prompt.startswith("Goal text")
    assert "Body text." in prompt
    assert "Acceptance — your work must satisfy:" in prompt
    assert "pytest -q" in prompt
    # sections separated by blank line
    assert "\n\n" in prompt


def test_build_prompt_body_empty_omits_section() -> None:
    unit = RichWorkUnit(task_id="t", goal="G", body="", accept_text="pytest")
    prompt = _build_prompt(unit)
    assert "G" in prompt
    assert "Acceptance" in prompt
    # no extra blank lines from empty body
    assert prompt == "G\n\nAcceptance — your work must satisfy:\npytest"


def test_build_prompt_accept_empty_omits_section() -> None:
    unit = RichWorkUnit(task_id="t", goal="G", body="Some body.", accept_text="")
    prompt = _build_prompt(unit)
    assert "G" in prompt
    assert "Some body." in prompt
    assert "Acceptance" not in prompt
