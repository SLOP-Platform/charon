"""Tests for the neutral product-grade store (ADR-0017 product_grades path).

The store is the product-side half of the gateway MVP seam. The tests
here are FAIL-ON-REVERT: each one pins one property the overlay depends
on, so removing / changing the property breaks the overlay's contract
without the overlay test noticing — that is the load-bearing reason
both halves share this ticket.

Coverage:
  * The cold-start empty store is the SHARED sentinel
    (``ProductGradeStore.empty()``) — overlay keys off its identity.
  * The loader returns the empty store when the file is MISSING (the
    FAIL-OPEN cold start). The byte-identical cold-start test in
    ``test_grade_order.py`` depends on this.
  * The loader raises on an empty file (the refuse-on-empty contract —
    an operator-shipped empty list is a structural misconfiguration,
    not a no-op signal).
  * Unknown work_class / unknown grade / unknown schema version
    surface as load-time errors, NOT silent routing misses.
  * Round-trip: save → load produces an equal store.
  * ``load_cached`` memoises per-path (the hot path's no-per-request-
    parse invariant).
  * The store imports NO fleet code (rig→product leak boundary).

Stdlib-only (no litellm needed for these tests).
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from charon.capability import product_grades as pg
from charon.capability.product_grades import (
    DEFAULT_GRADES_FILENAME,
    ENV_OVERRIDE,
    SCHEMA_VERSION,
    EmptyGradeStore,
    InvalidGradeStore,
    ProductGradeEntry,
    ProductGradeStore,
    load_cached,
    resolve_default_path,
)

# ── empty-store sentinel (the cold-start signal) ─────────────────────────


class TestEmptyStoreSentinel:
    """``ProductGradeStore.empty()`` is the SHARED no-signal value.

    The overlay keys off ``store is ProductGradeStore.empty()`` — a
    distinct instance returned per call would defeat the identity
    comparison and silently degrade the overlay's cold-start to
    \"grade_unknown for every model\" (worse than chain order — it
    ranks the un-graded models differently).
    """

    def test_empty_is_shared_singleton(self):
        a = ProductGradeStore.empty()
        b = ProductGradeStore.empty()
        assert a is b, "empty() must return the same instance every call (overlay identity check)"

    def test_empty_has_no_entries(self):
        assert ProductGradeStore.empty().entries == ()

    def test_constructor_refuses_empty(self):
        """The constructor refuses the silent-empty path; only ``empty()``
        may produce it. A caller that constructs ``ProductGradeStore()``
        expecting the empty sentinel gets a loud refusal instead — that
        is the structural guard that prevents an accidental
        silent-empty from reaching the overlay."""
        with pytest.raises(EmptyGradeStore):
            ProductGradeStore()

    def test_constructor_refuses_empty_tuple(self):
        with pytest.raises(EmptyGradeStore):
            ProductGradeStore(entries=())


# ── lookups ───────────────────────────────────────────────────────────────


class TestLookups:
    """``grade_for`` / ``confidence_for`` return the cold-start
    sentinel for absent keys, NEVER raise on missing data."""

    def test_grade_for_returns_unknown_for_absent_key(self):
        s = ProductGradeStore(entries=(
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A"),
        ))
        assert s.grade_for("m2", "reasoning") == "unknown"
        assert s.grade_for("m1", "coding") == "unknown"

    def test_grade_for_returns_the_seeded_grade(self):
        s = ProductGradeStore(entries=(
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A"),
            ProductGradeEntry(model_id="m1", work_class="coding", grade="B"),
        ))
        assert s.grade_for("m1", "reasoning") == "A"
        assert s.grade_for("m1", "coding") == "B"

    def test_confidence_for_absent_key_returns_one(self):
        """The overlay's tie-break rule prefers real (1.0) over
        provisional (< 1.0); an absent entry defaults to 1.0 so a
        missing key never looks \"more provisional\" than a real one."""
        s = ProductGradeStore(entries=(
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A"),
        ))
        assert s.confidence_for("m2", "reasoning") == 1.0
        assert s.confidence_for("m1", "coding") == 1.0

    def test_confidence_for_present_key_returns_seeded(self):
        s = ProductGradeStore(entries=(
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A",
                              confidence=0.5),
        ))
        assert s.confidence_for("m1", "reasoning") == 0.5

    def test_models_for_work_class_dedupes(self):
        s = ProductGradeStore(entries=(
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A"),
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="B"),
            ProductGradeEntry(model_id="m2", work_class="reasoning", grade="A"),
            ProductGradeEntry(model_id="m1", work_class="coding", grade="A"),
        ))
        assert s.models_for("reasoning") == ("m1", "m2")
        assert s.models_for("coding") == ("m1",)
        assert s.models_for("translation") == ()


# ── entry validation ──────────────────────────────────────────────────────


class TestEntryValidation:
    """An entry with a typo'd work_class / grade / confidence surface
    as a construction error, NOT as a silent routing miss."""

    def test_unknown_work_class_raises(self):
        with pytest.raises(InvalidGradeStore):
            ProductGradeEntry(model_id="m1", work_class="reasoningish", grade="A")

    def test_unknown_grade_band_raises(self):
        with pytest.raises(InvalidGradeStore):
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A+")

    def test_negative_confidence_raises(self):
        with pytest.raises(InvalidGradeStore):
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A",
                              confidence=-0.1)

    def test_over_one_confidence_raises(self):
        with pytest.raises(InvalidGradeStore):
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A",
                              confidence=1.5)

    def test_empty_model_id_raises(self):
        with pytest.raises(InvalidGradeStore):
            ProductGradeEntry(model_id="", work_class="reasoning", grade="A")


# ── load / save round-trip ────────────────────────────────────────────────


class TestLoadSave:
    """The on-disk schema round-trips faithfully through load/save."""

    def _payload(self, *, version=SCHEMA_VERSION, entries=None):
        return {
            "version": version,
            "entries": entries if entries is not None else [
                {"model_id": "m1", "work_class": "reasoning", "grade": "A",
                 "confidence": 0.9, "samples": 7},
            ],
        }

    def test_round_trip_preserves_entries(self, tmp_path):
        path = tmp_path / "grades.json"
        s = ProductGradeStore(entries=(
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A",
                              confidence=0.9, samples=7),
            ProductGradeEntry(model_id="m2", work_class="coding", grade="B"),
        ))
        s.save(path)
        s2 = ProductGradeStore.load(path)
        assert s2.entries == s.entries

    def test_missing_file_returns_empty_store(self, tmp_path):
        """FAIL-OPEN cold start: a missing file returns the shared
        empty sentinel, NEVER raises. The overlay depends on this for
        the byte-identical cold-start behaviour."""
        s = ProductGradeStore.load(tmp_path / "absent.json")
        assert s is ProductGradeStore.empty()

    def test_empty_file_raises_empty_store(self, tmp_path):
        """Refuse-on-empty: an empty entries list is a structural
        misconfiguration, not a no-op. The overlay treats
        ``is_empty_store`` as \"no signal\"; an empty file would be
        ambiguous with a missing file."""
        path = tmp_path / "grades.json"
        path.write_text(json.dumps(self._payload(entries=[])))
        with pytest.raises(EmptyGradeStore):
            ProductGradeStore.load(path)

    def test_unknown_version_raises(self, tmp_path):
        """A future schema version is rejected, NEVER silently downgraded
        (a silent downgrade would mask an operator upgrade as a
        missing-grade cold start)."""
        path = tmp_path / "grades.json"
        path.write_text(json.dumps(self._payload(version=999)))
        with pytest.raises(InvalidGradeStore):
            ProductGradeStore.load(path)

    def test_malformed_json_raises_invalid(self, tmp_path):
        path = tmp_path / "grades.json"
        path.write_text("{ this is not valid json")
        with pytest.raises(InvalidGradeStore):
            ProductGradeStore.load(path)

    def test_non_object_root_raises(self, tmp_path):
        path = tmp_path / "grades.json"
        path.write_text("[]")
        with pytest.raises(InvalidGradeStore):
            ProductGradeStore.load(path)

    def test_non_list_entries_raises(self, tmp_path):
        path = tmp_path / "grades.json"
        path.write_text(json.dumps({"version": SCHEMA_VERSION, "entries": {}}))
        with pytest.raises(InvalidGradeStore):
            ProductGradeStore.load(path)

    def test_unknown_work_class_in_entry_raises(self, tmp_path):
        path = tmp_path / "grades.json"
        path.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "entries": [{"model_id": "m1", "work_class": "reasoningish", "grade": "A"}],
        }))
        with pytest.raises(InvalidGradeStore):
            ProductGradeStore.load(path)

    def test_missing_required_field_raises(self, tmp_path):
        path = tmp_path / "grades.json"
        path.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "entries": [{"model_id": "m1", "grade": "A"}],
        }))
        with pytest.raises(InvalidGradeStore):
            ProductGradeStore.load(path)

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "grades.json"
        s = ProductGradeStore(entries=(
            ProductGradeEntry(model_id="m1", work_class="reasoning", grade="A"),
        ))
        s.save(path)
        assert path.exists()
        s2 = ProductGradeStore.load(path)
        assert s2.entries == s.entries

    def test_round_trip_through_string(self, tmp_path):
        """The on-disk format is human-readable JSON (the format an
        operator seeds with ``jq`` / a config-management tool)."""
        path = tmp_path / "grades.json"
        path.write_text(textwrap.dedent("""
            {
              "version": 1,
              "entries": [
                {"model_id": "m1", "work_class": "reasoning", "grade": "A"},
                {"model_id": "m2", "work_class": "coding", "grade": "F",
                 "confidence": 0.5, "samples": 0}
              ]
            }
        """).strip())
        s = ProductGradeStore.load(path)
        assert s.grade_for("m1", "reasoning") == "A"
        assert s.grade_for("m2", "coding") == "F"
        assert s.confidence_for("m2", "coding") == 0.5


# ── load_cached ───────────────────────────────────────────────────────────


class TestLoadCached:
    """``load_cached`` memoises per resolved path — the hot-path
    invariant the overlay depends on (no per-request file parse)."""

    def test_caches_per_path(self, tmp_path, monkeypatch):
        # Clear any test-cross-contamination from the module cache.
        pg._clear_cache()

        path1 = tmp_path / "g1.json"
        path2 = tmp_path / "g2.json"
        path1.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "entries": [{"model_id": "m1", "work_class": "reasoning", "grade": "A"}],
        }))
        path2.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "entries": [{"model_id": "m2", "work_class": "coding", "grade": "B"}],
        }))

        a = load_cached(path1)
        b = load_cached(path1)
        assert a is b, "load_cached must return the same instance per path"

        c = load_cached(path2)
        assert c is not a, "distinct paths must cache independently"

    def test_missing_path_returns_shared_empty(self, tmp_path, monkeypatch):
        pg._clear_cache()
        s = load_cached(tmp_path / "absent.json")
        assert s is ProductGradeStore.empty()

    def test_home_arg_drives_default_path(self, tmp_path, monkeypatch):
        """``home=`` is the canonical per-test override (tests should
        NEVER rely on cwd; this is the friction that prevents
        accidental cross-test contamination)."""
        pg._clear_cache()
        monkeypatch.delenv(ENV_OVERRIDE, raising=False)
        home = tmp_path / "home"
        home.mkdir()
        # No file under home → empty sentinel
        s = load_cached(home=home)
        assert s is ProductGradeStore.empty()

    def test_env_var_overrides_home(self, tmp_path, monkeypatch):
        pg._clear_cache()
        env_path = tmp_path / "env.json"
        env_path.write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "entries": [{"model_id": "from-env", "work_class": "reasoning", "grade": "A"}],
        }))
        monkeypatch.setenv(ENV_OVERRIDE, str(env_path))
        s = load_cached(home=tmp_path / "home")  # home is ignored when env is set
        assert s.grade_for("from-env", "reasoning") == "A"

    def test_resolve_default_path_precedence(self, tmp_path, monkeypatch):
        monkeypatch.delenv(ENV_OVERRIDE, raising=False)
        # 1. No env, no home → cwd
        p = resolve_default_path()
        assert p.name == DEFAULT_GRADES_FILENAME
        # 2. With home → home/
        home = tmp_path / "h"
        p = resolve_default_path(home=home)
        assert p == home / DEFAULT_GRADES_FILENAME
        # 3. Env var wins
        monkeypatch.setenv(ENV_OVERRIDE, "/explicit/path.json")
        p = resolve_default_path(home=home)
        assert p == Path("/explicit/path.json")


# ── rig↔product boundary (the load-bearing leak guard) ───────────────────


class TestBoundary:
    """The product-grade store imports NO fleet / build-rig code.

    ADR-0017 mandates this boundary
    [[product-vs-build-rig-boundary]]: a rig→product leak would couple
    the product-side format to whatever the build-side matrix decides
    to do, defeating the purpose of a \"neutral product-owned format\".
    This test is the structural guard — it fails if a future refactor
    adds an import from ``charon.routing_policy.matrix`` (or any other
    build-rig module) into the product-grade module.
    """

    def test_product_grades_module_does_not_import_fleet_code(self):
        """Static guard: the product-grade module must not import any
        fleet / build-rig code at the AST level. This catches
        ``from charon.routing_policy.matrix import ...`` and similar
        leaks that the test-suite boundary check
        (``tools/check_boundary.py``) does NOT flag (it scans for
        host-project names only)."""
        import ast
        import inspect

        from charon.capability import product_grades as mod

        src = inspect.getsource(mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("charon.routing_policy"), (
                        f"product-grade store must not import fleet code: {alias.name!r}")
                    assert not alias.name.startswith("charon.scorecard"), (
                        f"product-grade store must not import fleet code: {alias.name!r}")
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                assert not mod_name.startswith("charon.routing_policy"), (
                    f"product-grade store must not import from {mod_name!r} "
                    "(rig→product leak boundary)")
                assert not mod_name.startswith("charon.scorecard"), (
                    f"product-grade store must not import from {mod_name!r} "
                    "(rig→product leak boundary)")
