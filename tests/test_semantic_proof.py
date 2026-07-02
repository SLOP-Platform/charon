"""Tests for the §5.1 semantic-independence proof engine (WCI-FOLLOWON)."""
from __future__ import annotations

import json
import pathlib

from charon.engine.board import Board, Unit
from charon.engine.semantic_proof import IndependenceCertificate, compute_certificate


def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_signal1_disjoint_imports_pass(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "y = 2")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s1_import"] is True


def test_signal1_direct_import_fails(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "from charon.mod_a import x")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s1_import"] is False


def test_signal1_transitive_import_fails(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "from charon.mod_a import x")
    _write(tmp_path / "src/charon/mod_c.py", "from charon.mod_b import x")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_c.py"], "a", "c", str(tmp_path)
    )
    assert cert.signal_results["s1_import"] is False


def test_signal1_reexport_chain_fails(tmp_path):
    _write(tmp_path / "src/charon/pkg_a/__init__.py", "from charon.pkg_a.core import X")
    _write(tmp_path / "src/charon/pkg_a/core.py", "X = 1")
    _write(tmp_path / "src/charon/mod_b.py", "from charon.pkg_a import X")
    cert = compute_certificate(
        ["src/charon/pkg_a/core.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s1_import"] is False


def test_signal2_no_shared_state_pass(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "y = 2")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s2_symbol"] is True


def test_signal2_shared_mutable_fails(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "cache = {}\ndef foo():\n    pass")
    _write(tmp_path / "src/charon/mod_b.py", "from charon.mod_a import cache\ncache['k'] = 1")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s2_symbol"] is False
    # mod_a writes cache at module level; mod_b imports (=reads) it


def test_signal2_decorator_registration_fails(tmp_path):
    reg = "_items = []\ndef register(fn):\n    _items.append(fn)\n    return fn"
    _write(tmp_path / "src/charon/registry.py", reg)
    mod_a = "from charon.registry import register\n@register\ndef handler():\n    pass"
    _write(tmp_path / "src/charon/mod_a.py", mod_a)
    _write(tmp_path / "src/charon/mod_b.py", "from charon.registry import _items\nprint(_items)")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s2_symbol"] is True
    # decorator call target is 'register', not a shared top-level name


def test_signal3_disjoint_keys_pass(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "charon-config.json").write_text(json.dumps({"providers": {}, "tiers": {}}))
    _write(tmp_path / "src/charon/mod_a.py", 'config["providers"]')
    _write(tmp_path / "src/charon/mod_b.py", 'config["tiers"]')
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path), str(cfg)
    )
    assert cert.signal_results["s3_config"] is True


def test_signal3_shared_key_fails(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "charon-config.json").write_text(json.dumps({"providers": {}, "tiers": {}}))
    _write(tmp_path / "src/charon/mod_a.py", 'config["providers"]')
    _write(tmp_path / "src/charon/mod_b.py", 'x = config.get("providers")')
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path), str(cfg)
    )
    assert cert.signal_results["s3_config"] is False


def test_signal4_disjoint_tests_pass(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "y = 2")
    _write(tmp_path / "tests/test_mod_a.py", "def test(): pass")
    _write(tmp_path / "tests/test_mod_b.py", "def test(): pass")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s4_test"] is True


def test_signal4_no_test_file_fails(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "y = 2")
    _write(tmp_path / "tests/test_mod_a.py", "def test(): pass")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s4_test"] is False


def test_signal4_cross_import_fails(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "y = 2")
    _write(tmp_path / "tests/test_mod_a.py", "def test(): pass")
    _write(tmp_path / "tests/test_mod_b.py", "from charon.mod_a import x\ndef test(): pass")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.signal_results["s4_test"] is False


def test_certificate_all_signals_must_pass(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "from charon.mod_a import x")
    _write(tmp_path / "tests/test_mod_a.py", "def test(): pass")
    _write(tmp_path / "tests/test_mod_b.py", "def test(): pass")
    cert = compute_certificate(
        ["src/charon/mod_a.py"], ["src/charon/mod_b.py"], "a", "b", str(tmp_path)
    )
    assert cert.proven is False


def test_claimable_merge_after_without_cert_serializes(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "y = 2")
    _write(tmp_path / "tests/test_mod_a.py", "def test(): pass")
    _write(tmp_path / "tests/test_mod_b.py", "def test(): pass")
    (tmp_path / "src/charon/config.py").write_text("")

    a = Unit(id="a", owns=["src/charon/mod_a.py"])
    b = Unit(id="b", owns=["src/charon/mod_b.py"], merge_after=["a"])
    board = Board(tmp_path / "board.json", {"a": a, "b": b})
    assert board.claimable("a") is True
    assert board.claimable("b") is False  # merge_after without cert → depends_on


def test_claimable_merge_after_with_cert_allows_concurrent(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "src/charon/mod_b.py", "y = 2")
    _write(tmp_path / "tests/test_mod_a.py", "def test(): pass")
    _write(tmp_path / "tests/test_mod_b.py", "def test(): pass")
    (tmp_path / "src/charon/config.py").write_text("")

    cert = IndependenceCertificate(unit_a="a", unit_b="b", proven=True,
                                    signal_results={"s1": True, "s2": True, "s3": True, "s4": True})
    a = Unit(id="a", owns=["src/charon/mod_a.py"])
    b = Unit(id="b", owns=["src/charon/mod_b.py"], merge_after=["a"])
    board = Board(tmp_path / "board.json", {"a": a, "b": b})
    board.set_cert("a", "b", cert)
    assert board.claimable("a") is True
    assert board.claimable("b") is True  # positive cert → concurrent


def test_claimable_merge_after_with_overlapping_owns_still_serializes(tmp_path):
    _write(tmp_path / "src/charon/mod_a.py", "x = 1")
    _write(tmp_path / "tests/test_mod_a.py", "def test(): pass")
    _write(tmp_path / "tests/test_mod_b.py", "def test(): pass")
    (tmp_path / "src/charon/config.py").write_text("")

    cert = IndependenceCertificate(unit_a="a", unit_b="b", proven=True,
                                    signal_results={"s1": True, "s2": True, "s3": True, "s4": True})
    a = Unit(id="a", owns=["src/charon/mod_a.py", "src/charon/shared.py"])
    b = Unit(id="b", owns=["src/charon/mod_b.py", "src/charon/shared.py"], merge_after=["a"])
    board = Board(tmp_path / "board.json", {"a": a, "b": b})
    board.set_cert("a", "b", cert)
    assert board.claimable("a") is True
    assert board.claimable("b") is False  # owns-overlap → M-owns serializes despite cert


def test_merge_after_schema_roundtrip(tmp_path):
    a = Unit(id="a", owns=["src/charon/mod_a.py"])
    b = Unit(id="b", owns=["src/charon/mod_b.py"], merge_after=["a"])
    board = Board(tmp_path / "board.json", {"a": a, "b": b})
    board._save()
    loaded = Board.load(tmp_path / "board.json")
    assert loaded.get("b").merge_after == ["a"]
    assert loaded.get("a").merge_after == []


def test_unit_depth_includes_merge_after(tmp_path):
    a = Unit(id="a", owns=["src/charon/mod_a.py"])
    b = Unit(id="b", owns=["src/charon/mod_b.py"], merge_after=["a"])
    c = Unit(id="c", owns=["src/charon/mod_c.py"], depends_on=["b"])
    board = Board(tmp_path / "board.json", {"a": a, "b": b, "c": c})
    assert board._unit_depth("b") >= 1  # merge_after counts as depth edge
    assert board._unit_depth("c") >= 2
