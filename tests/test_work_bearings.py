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
from charon.engine.board import Unit
from charon.engine.scheduler import CoordinatorRunner
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


# ---------------------------------------------------------------------------
# END-TO-END `charon work` dispatch: a board Unit driven through the WORK-PATH
# runner (CoordinatorRunner) must reach the ACP agent with goal + body + accept.
# This is the coverage WORK-AGENT-BEARINGS' groundwork lacked: it proved the
# prompt builder and `charon run`, but the `charon work` path dispatched a PLAIN
# WorkUnit, so the agent there got the title alone. We drive a real Unit through
# the runner (NOT a hand-built RichWorkUnit) so the carry is proven end to end.
# ---------------------------------------------------------------------------


def _run_unit_through_runner(
    tmp_path: Path, unit: Unit, stub: Path, capture: Path
) -> None:
    """Drive ``unit`` through the work-path CoordinatorRunner with the capture
    stub as the warm ACP backend. The runner builds the dispatched WorkUnit from
    the board Unit, so a successful capture proves body + accept survive the
    carry. Nested worktree (``…/sandbox/repo``) keeps the fence's guard_dir — the
    worktree's parent — clean, and the stub/capture/state live OUTSIDE it so the
    escape scan sees no stray writes."""
    worktree = tmp_path / "sandbox" / "repo"
    worktree.mkdir(parents=True)
    gitutil.init_repo(worktree)
    runner = CoordinatorRunner(
        state_dir=str(tmp_path / "state"),
        backend_factory=lambda u, checks: {
            "acp": AcpBackend(
                command=[sys.executable, str(stub)],
                name="acp",
                passthrough_env={"STUB_CAPTURE_FILE": str(capture)},
            )
        },
        max_checkpoints=1,  # one dispatch is enough to capture the prompt
    )
    runner(unit, str(worktree), cost_gate=None)


def test_work_path_dispatch_carries_goal_body_and_accept(tmp_path: Path) -> None:
    """End-to-end: a board Unit driven through the work-path runner sends a
    `session/prompt` whose text contains the goal, the body, AND the acceptance
    criteria — the bearings the `charon work` path previously dropped."""
    stub = tmp_path / "stub.py"
    stub.write_text(_CAPTURE_STUB)
    capture = tmp_path / "prompt.txt"

    accept = ["test -f sentinel.txt", "test -x check.sh"]
    unit = Unit(
        id="work-bearings-e2e",
        tier="opus",
        owns=["src/x.py"],
        goal="Carry full bearings to the work agent",
        body="The work path dispatched a plain unit.\nThread body + accept through.",
        accept=accept,
    )
    _run_unit_through_runner(tmp_path, unit, stub, capture)

    assert capture.exists(), "the work-path dispatch never sent a session/prompt"
    prompt = capture.read_text()
    assert "Carry full bearings to the work agent" in prompt  # goal
    assert "Thread body + accept through." in prompt  # body
    # the accept text shown is the SAME checks the gate executes (one source of
    # truth) — each, joined by newlines, present verbatim.
    for check in accept:
        assert check in prompt, f"accept check {check!r} missing from work prompt"
    assert "Acceptance" in prompt  # the bearings template header


def test_work_path_dispatch_no_secrets(tmp_path: Path) -> None:
    """The work-path prompt is built solely from Unit fields — no creds leak in."""
    stub = tmp_path / "stub.py"
    stub.write_text(_CAPTURE_STUB)
    capture = tmp_path / "prompt.txt"

    unit = Unit(
        id="work-bearings-noleak",
        tier="opus",
        owns=["src/x.py"],
        goal="Patch the gateway",
        body="Adjust the timeout.",
        accept=["test -f ok"],
    )
    _run_unit_through_runner(tmp_path, unit, stub, capture)

    prompt = capture.read_text()
    assert "sk-" not in prompt
    assert "ANTHROPIC_API_KEY" not in prompt
    assert "OPENAI_API_KEY" not in prompt
    assert "Bearer " not in prompt


def test_work_path_unit_without_body_still_dispatches_goal(tmp_path: Path) -> None:
    """A board Unit with no body still dispatches — the goal (and accept) reach
    the agent; the empty body section is simply omitted (backward-compatible)."""
    stub = tmp_path / "stub.py"
    stub.write_text(_CAPTURE_STUB)
    capture = tmp_path / "prompt.txt"

    unit = Unit(
        id="work-bearings-nobody",
        tier="opus",
        owns=["src/x.py"],
        goal="Just the goal here",
        accept=["test -f ok"],
    )
    _run_unit_through_runner(tmp_path, unit, stub, capture)

    prompt = capture.read_text()
    assert prompt.startswith("Just the goal here")
    assert "test -f ok" in prompt
