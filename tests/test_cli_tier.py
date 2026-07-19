"""Tests for the `charon tier` CLI subcommand (DTC tier-abstraction)."""
from __future__ import annotations

from charon.cli import main


def test_tier_init_seeds_defaults(monkeypatch, tmp_path, capsys):
    """init writes tiers.json with order, legacy aliases, and Anthropic day-one members."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = main(["tier", "init"])
    assert rc == 0

    from charon import config
    tiers = config.load_tiers()
    assert tiers["order"] == ["low", "med", "high"]
    assert tiers["members"]["low"] == ["haiku"]
    assert tiers["members"]["med"] == ["sonnet"]
    assert tiers["members"]["high"] == ["opus"]
    assert tiers["aliases"]["opus"] == "high"
    assert tiers["aliases"]["sonnet"] == "med"
    assert tiers["aliases"]["haiku"] == "low"
    assert tiers["aliases"]["frontier"] == "high"
    assert tiers["aliases"]["strong"] == "med"
    assert tiers["aliases"]["economy"] == "low"


def test_tier_init_is_idempotent(monkeypatch, tmp_path, capsys):
    """init can be run multiple times safely."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert main(["tier", "init"]) == 0
    assert main(["tier", "init"]) == 0


def test_tier_ranks_emits_canonical_and_alias_rows(monkeypatch, tmp_path, capsys):
    """ranks prints canonical (low/med/high) and all alias rows; machine-parseable."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "ranks"])
    out = capsys.readouterr().out
    assert rc == 0

    lines = dict(line.split() for line in out.strip().splitlines() if line.strip())
    assert lines["low"] == "1"
    assert lines["med"] == "2"
    assert lines["high"] == "3"
    assert lines["opus"] == "3"
    assert lines["sonnet"] == "2"
    assert lines["haiku"] == "1"
    assert lines["frontier"] == "3"
    assert lines["strong"] == "2"
    assert lines["economy"] == "1"


def test_tier_ranks_legacy_fallback_absent_file(monkeypatch, tmp_path, capsys):
    """ranks works even when tiers.json is absent — uses the legacy defaults."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = main(["tier", "ranks"])
    out = capsys.readouterr().out
    assert rc == 0
    lines = dict(line.split() for line in out.strip().splitlines() if line.strip())
    assert lines["low"] == "1"
    assert lines["med"] == "2"
    assert lines["high"] == "3"
    assert lines["opus"] == "3"


def test_tier_resolve_anthropic_returns_sole_member(monkeypatch, tmp_path, capsys):
    """resolve --executor anthropic returns the sole member of a tier."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "resolve", "high", "--executor", "anthropic"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == "opus"


def test_tier_resolve_accepts_alias(monkeypatch, tmp_path, capsys):
    """resolve accepts an alias (opus → high tier)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "resolve", "opus", "--executor", "anthropic"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == "opus"


def test_tier_resolve_picks_cheapest_when_multiple(monkeypatch, tmp_path, capsys):
    """resolve picks the cheapest (free-first, then cost_rank) Anthropic member."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon import config
    config.add_model("cheap-ant", provider="anthropic", free=True, cost_rank=0)
    config.add_model("pricey-ant", provider="anthropic", free=False, cost_rank=500)
    config.set_tiers(
        order=["low", "med", "high"],
        members={"low": ["pricey-ant", "cheap-ant"], "med": ["sonnet"], "high": ["opus"]},
        aliases={"opus": "high", "sonnet": "med", "haiku": "low"},
    )
    capsys.readouterr()

    rc = main(["tier", "resolve", "low", "--executor", "anthropic"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == "cheap-ant"


def test_tier_resolve_skips_non_anthropic_members(monkeypatch, tmp_path, capsys):
    """resolve --executor anthropic skips models with a non-anthropic provider."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon import config
    config.add_model("openai-model", provider="openai", free=False, cost_rank=100)
    config.add_model("ant-model", provider="anthropic", free=False, cost_rank=200)
    config.set_tiers(
        order=["low", "med", "high"],
        members={"low": ["openai-model", "ant-model"], "med": ["sonnet"], "high": ["opus"]},
        aliases={"opus": "high", "sonnet": "med", "haiku": "low"},
    )
    capsys.readouterr()

    rc = main(["tier", "resolve", "low", "--executor", "anthropic"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == "ant-model"


def test_tier_resolve_no_anthropic_member_exits_nonzero(monkeypatch, tmp_path, capsys):
    """resolve exits non-zero when no anthropic-runnable member exists."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon import config
    config.add_model("only-openai", provider="openai", free=False, cost_rank=100)
    config.set_tiers(
        order=["low", "med", "high"],
        members={"low": ["only-openai"], "med": [], "high": []},
        aliases={},
    )
    capsys.readouterr()

    rc = main(["tier", "resolve", "low", "--executor", "anthropic"])
    assert rc != 0


def test_tier_resolve_absent_file_falls_back_to_legacy(monkeypatch, tmp_path, capsys):
    """resolve works without tiers.json, falling back to legacy Anthropic members."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = main(["tier", "resolve", "high", "--executor", "anthropic"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == "opus"


def test_tier_set_and_list_round_trip(monkeypatch, tmp_path, capsys):
    """set updates tier members; list reflects the new state."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "set", "low", "--members", "haiku,mini-model"])
    assert rc == 0
    capsys.readouterr()

    from charon import config
    assert config.load_tiers()["members"]["low"] == ["haiku", "mini-model"]

    rc = main(["tier", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "low" in out
    assert "haiku" in out
    assert "mini-model" in out


def test_tier_list_absent_config_shows_legacy_defaults(monkeypatch, tmp_path, capsys):
    """list degrades gracefully when tiers.json is absent."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = main(["tier", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "low" in out
    assert "med" in out
    assert "high" in out


def test_tier_set_unknown_tier_exits_nonzero(monkeypatch, tmp_path):
    """set exits non-zero for unknown tier names."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    rc = main(["tier", "set", "extreme", "--members", "some-model"])
    assert rc != 0


def test_tier_set_via_alias(monkeypatch, tmp_path, capsys):
    """set accepts an alias and resolves to the canonical tier."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    main(["tier", "init"])
    capsys.readouterr()

    rc = main(["tier", "set", "opus", "--members", "opus,opus-alt"])
    assert rc == 0

    from charon import config
    assert config.load_tiers()["members"]["high"] == ["opus", "opus-alt"]


def test_tier_resolve_unknown_model_id_is_not_anthropic(monkeypatch, tmp_path, capsys):
    """FAIL-ON-REVERT: an UNKNOWN model id must NOT count as Anthropic-runnable.

    `_tier_resolve._is_anthropic` used to `return True` for any id absent from
    the catalog. That fall-through meant a typo'd, renamed, or simply
    unregistered id was silently classified as Anthropic and handed to the
    executor — a bespoke string match drifting from the
    `providers.is_anthropic_route` SSOT, which is the exact drift class PR #173
    fixed gateway-wide.

    Here the tier's only member is registered to a NON-Anthropic provider and
    the second member is not in the catalog at all. Neither is Anthropic, so
    resolve must exit non-zero rather than emitting the unknown id. Restoring
    the `return True` fall-through turns this red.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon import config
    config.add_model("known-openai", provider="openai")
    config.set_tiers(
        order=["low", "med", "high"],
        members={"low": ["known-openai", "totally-unregistered-id"], "med": [], "high": []},
        aliases={},
    )
    capsys.readouterr()

    rc = main(["tier", "resolve", "low", "--executor", "anthropic"])
    out = capsys.readouterr().out.strip()
    assert rc != 0, "unknown model id must not be treated as Anthropic-runnable"
    assert "totally-unregistered-id" not in out
