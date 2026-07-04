"""Tests for the curated model catalog + tier picker CLI (TIER-SELECT Phase-A)."""
from __future__ import annotations

from charon import model_catalog
from charon.cli import main

# ── pure catalog tests (no CLI, no filesystem) ──────────────────────

def test_catalog_nonempty():
    """catalog() returns entries."""
    entries = model_catalog.catalog()
    assert len(entries) > 0


def test_catalog_entries_have_required_fields():
    """Every entry has id, tier_hint in {low,med,high}, access, note."""
    for e in model_catalog.catalog():
        assert isinstance(e.id, str) and e.id
        assert e.tier_hint in ("low", "med", "high")
        assert isinstance(e.access, str) and e.access
        assert isinstance(e.note, str) and e.note


def test_catalog_ids_unique():
    """Catalog ids are unique."""
    ids = [e.id for e in model_catalog.catalog()]
    assert len(ids) == len(set(ids))


def test_catalog_stdlib_only():
    """model_catalog imports only stdlib modules (no third-party deps)."""
    import ast
    from pathlib import Path

    path = Path(model_catalog.__file__)
    source = path.read_text()
    tree = ast.parse(source)

    stdlib = {
        "__future__", "collections", "collections.abc",
        "dataclasses",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in stdlib, f"third-party import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative charon-internal import
            if node.module is None:
                continue
            top = node.module.split(".")[0]
            assert top in stdlib, f"third-party import: {node.module}"


def test_catalog_for_tier_filters_by_canonical():
    """catalog_for_tier('high') returns only high-tier entries."""
    high = model_catalog.catalog_for_tier("high")
    assert len(high) > 0
    for e in high:
        assert e.tier_hint == "high"


def test_catalog_for_tier_folds_aliases():
    """catalog_for_tier accepts aliases (frontier→high, strong→med, economy→low)."""
    for alias, canon in (("frontier", "high"), ("strong", "med"), ("economy", "low")):
        entries = model_catalog.catalog_for_tier(alias)
        assert len(entries) > 0
        for e in entries:
            assert e.tier_hint == canon


def test_catalog_for_tier_unknown_raises():
    """catalog_for_tier('bogus') raises ValueError."""
    import pytest
    with pytest.raises(ValueError):
        model_catalog.catalog_for_tier("bogus")


# ── CLI tests ───────────────────────────────────────────────────────

def test_tier_catalog_lists_entries(monkeypatch, tmp_path, capsys):
    """charon tier catalog prints curated options."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = main(["tier", "catalog"])
    out = capsys.readouterr().out
    assert rc == 0

    entries = model_catalog.catalog()
    for e in entries:
        assert e.id in out


def test_tier_catalog_filter_by_tier(monkeypatch, tmp_path, capsys):
    """charon tier catalog --tier strong lists only med-tier entries."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = main(["tier", "catalog", "--tier", "strong"])
    out = capsys.readouterr().out
    assert rc == 0

    for e in model_catalog.catalog():
        if e.tier_hint == "med":
            assert e.id in out

    for e in model_catalog.catalog():
        if e.tier_hint != "med":
            assert e.id not in out


def test_tier_set_from_catalog_merges(monkeypatch, tmp_path, capsys):
    """tier set --from-catalog writes catalog ids into tiers.json."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "set", "high", "--from-catalog",
               "claude-opus-4-8,gpt-5.5"])
    assert rc == 0

    from charon import config
    members = config.load_tiers()["members"]["high"]
    assert "claude-opus-4-8" in members
    assert "gpt-5.5" in members


def test_tier_set_from_catalog_rejects_non_catalog_id(monkeypatch, tmp_path, capsys):
    """tier set --from-catalog rejects an id not in the catalog."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "set", "high", "--from-catalog", "made-up-model"])
    out = capsys.readouterr().err
    assert rc != 0
    assert "not in the curated catalog" in out
    assert "made-up-model" in out


def test_tier_set_members_permissive(monkeypatch, tmp_path, capsys):
    """tier set --members persists any id (off-catalog included)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "set", "low", "--members", "my-custom-model"])
    assert rc == 0

    from charon import config
    assert config.load_tiers()["members"]["low"] == ["my-custom-model"]


def test_tier_set_from_catalog_merges_with_existing(monkeypatch, tmp_path, capsys):
    """from-catalog merges into existing members (does not replace)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    main(["tier", "set", "med", "--members", "custom-first"])
    capsys.readouterr()

    rc = main(["tier", "set", "med", "--from-catalog", "claude-sonnet-5"])
    assert rc == 0

    from charon import config
    members = config.load_tiers()["members"]["med"]
    assert "custom-first" in members
    assert "claude-sonnet-5" in members


def test_tier_set_from_catalog_empty_string_is_noop(monkeypatch, tmp_path):
    """Empty --from-catalog does nothing (no error)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    rc = main(["tier", "set", "high", "--from-catalog", ""])
    assert rc == 0


def test_tier_set_from_catalog_via_alias(monkeypatch, tmp_path, capsys):
    """set --from-catalog accepts an alias for the tier name."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "set", "frontier", "--from-catalog",
               "claude-opus-4-8"])
    assert rc == 0

    from charon import config
    assert "claude-opus-4-8" in config.load_tiers()["members"]["high"]
