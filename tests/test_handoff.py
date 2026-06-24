from __future__ import annotations

from pathlib import Path

from charon import gitutil, handoff
from charon.acceptance import AcceptanceCheck
from charon.ledger import Ledger
from charon.router import StaticRouter


def _led(state_dir: Path, repo: Path) -> Ledger:
    checks = [AcceptanceCheck("a0", "test -f x.txt"), AcceptanceCheck("a1", "test -f y.txt")]
    return Ledger.create(state_dir, "t1", "goal", checks, str(repo), gitutil.head(repo))


def test_h1_resumable_when_complete(state_dir: Path, git_repo: Path) -> None:
    led = _led(state_dir, git_repo)
    assert handoff.is_resumable(led).ok is True


def test_h1_not_resumable_when_acceptance_missing(state_dir: Path, git_repo: Path) -> None:
    led = _led(state_dir, git_repo)
    led.acceptance = []  # corrupt: no acceptance
    r = handoff.is_resumable(led)
    assert r.ok is False
    assert any("acceptance" in m for m in r.missing)


def test_h3_idempotent_rehydration_is_provider_independent(state_dir: Path, git_repo: Path) -> None:
    led = _led(state_dir, git_repo)
    (git_repo / "x.txt").write_text("1")
    # derive remaining; then reload the ledger ("another provider") and re-derive.
    first = handoff.rehydrate_remaining(led)
    reloaded = Ledger.load(state_dir, "t1")
    second = handoff.rehydrate_remaining(reloaded)
    assert first == second == {"a1"}  # same remaining regardless of who reads


def test_h6_handoff_excludes_exhausted_backend() -> None:
    router = StaticRouter(backends=["alpha", "beta"])
    route = handoff.choose_next_backend(router, "codegen", exhausted="alpha")
    assert route.backend == "beta"
