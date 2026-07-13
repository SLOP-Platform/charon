"""Tests for DEC-AST-WRAP — the change-surface adapter (decompose_surface).

The wrapper emits NO facts of its own; it delegates to the real ``semantic_proof``
AST engine.  These tests assert the emitted change-surface over a small fixture
module graph, including a genuine independence split, and pin a FAIL-ON-REVERT
guard: reverting the ``semantic_proof.compute_certificate`` call collapses the
provably-independent targets into one group, so the independence assertion goes
RED.  That is what proves the split comes from the engine, not a hardcode.
"""
from __future__ import annotations

import pathlib

from charon.decompose_surface import change_surface
from charon.engine import semantic_proof
from charon.engine.semantic_proof import IndependenceCertificate

ALPHA = "src/charon/alpha.py"
BETA = "src/charon/beta.py"
GAMMA = "src/charon/gamma.py"


def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _fixture(tmp_path: pathlib.Path) -> tuple[str, str]:
    """Build a small fixture repo; return (repo_root, empty_config_dir).

    alpha + beta are independent standalone modules (each with its own mapped
    test file, required by the engine's signal-4).  gamma imports alpha, so
    gamma is dependent on alpha.
    """
    _write(tmp_path / ALPHA, "ALPHA = 1\n\n\ndef fa():\n    return ALPHA\n")
    _write(tmp_path / BETA, "BETA = 2\n\n\ndef fb():\n    return BETA\n")
    _write(
        tmp_path / GAMMA,
        "from charon.alpha import ALPHA\n\n\ndef fg():\n    return ALPHA\n",
    )
    _write(
        tmp_path / "tests/test_alpha.py",
        "from charon.alpha import fa\n\n\ndef test_a():\n    assert fa() == 1\n",
    )
    _write(
        tmp_path / "tests/test_beta.py",
        "from charon.beta import fb\n\n\ndef test_b():\n    assert fb() == 2\n",
    )
    _write(
        tmp_path / "tests/test_gamma.py",
        "from charon.gamma import fg\n\n\ndef test_g():\n    assert fg() == 1\n",
    )
    return str(tmp_path), str(tmp_path / "no_such_config_dir")


def test_files_are_normalized_and_sorted(tmp_path):
    root, cfg = _fixture(tmp_path)
    surface = change_surface(["./" + BETA, ALPHA], repo_root=root, config_dir=cfg)
    assert surface["files"] == [ALPHA, BETA]


def test_independent_targets_split_into_two_groups(tmp_path):
    root, cfg = _fixture(tmp_path)
    surface = change_surface([ALPHA, BETA], repo_root=root, config_dir=cfg)

    # The core property: two provably-independent files -> two groups.
    assert surface["independence_groups"] == [[ALPHA], [BETA]]
    # Independent modules reach nothing of each other.
    assert surface["blast_radius"] == {ALPHA: [], BETA: []}
    # No import edges between them.
    assert surface["call_edges"] == []


def test_dependent_targets_collapse_to_one_group(tmp_path):
    root, cfg = _fixture(tmp_path)
    surface = change_surface([ALPHA, GAMMA], repo_root=root, config_dir=cfg)

    # gamma imports alpha -> not independent -> a single group.
    assert surface["independence_groups"] == [[ALPHA, GAMMA]]
    # gamma's blast radius reaches alpha; alpha reaches nothing.
    assert surface["blast_radius"][GAMMA] == [ALPHA]
    assert surface["blast_radius"][ALPHA] == []
    # The real import edge is surfaced.
    assert surface["call_edges"] == [[GAMMA, ALPHA]]


def test_fail_on_revert_independence_needs_the_engine(tmp_path, monkeypatch):
    """FAIL-ON-REVERT: reverting the semantic_proof call kills the split -> RED."""
    root, cfg = _fixture(tmp_path)

    # With the REAL engine, the independent targets split into two groups.
    real = change_surface([ALPHA, BETA], repo_root=root, config_dir=cfg)
    assert len(real["independence_groups"]) == 2  # guarded property

    # "Revert" the engine call: stub the certificate to never prove independence
    # (equivalent to deleting/neutralising the compute_certificate call).
    def _reverted(*args: object, **kwargs: object) -> IndependenceCertificate:
        return IndependenceCertificate(unit_a="", unit_b="", proven=False)

    monkeypatch.setattr(semantic_proof, "compute_certificate", _reverted)

    reverted = change_surface([ALPHA, BETA], repo_root=root, config_dir=cfg)
    # The split is GONE: everything collapses into one group. Had the wrapper
    # NOT depended on the real engine call, this would still be two groups and
    # the guarded assertion above could never be broken by reverting it.
    assert reverted["independence_groups"] == [[ALPHA, BETA]]
    assert len(reverted["independence_groups"]) != len(real["independence_groups"])
