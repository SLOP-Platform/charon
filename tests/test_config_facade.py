"""Facade integrity test — proves every public symbol from the config submodules
is re-exported through ``charon.config`` so no existing import breaks.

FAIL-ON-REVERT: remove a single re-export from ``config/__init__.py`` and this
test goes RED (``hasattr`` fails for the missing symbol).
"""
from __future__ import annotations

import ast
from pathlib import Path


def _public_names_of_module(source_path: Path) -> set[str]:
    """Parse a Python source file and collect every top-level public assignment
    (function, class, or simple variable — anything with a name that doesn't start
    with ``_``). This is how we compute what the old flat ``config.py`` exported:
    no ``__all__`` was defined, so every non-underscore top-level name was reachable
    as ``config.<name>``."""
    tree = ast.parse(source_path.read_text())
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    names.add(target.id)
    return names


def _config_submodule_source_files() -> list[Path]:
    config_pkg = Path(__file__).resolve().parent.parent / "src" / "charon" / "config"
    return sorted(
        p for p in config_pkg.glob("*.py")
        if p.name != "__init__.py"
    )


# ── collect every public name defined across all submodules ──────────────────

_EXPECTED: set[str] = set()
for _fp in _config_submodule_source_files():
    _EXPECTED |= _public_names_of_module(_fp)


def test_facade_re_exports_every_public_submodule_symbol():
    """Every public name defined in a config/ submodule MUST be present as a
    direct attribute of ``charon.config`` and MUST resolve to the same object
    as ``from charon.config.<submodule> import <name>``."""
    from charon import config as _cfg_pkg

    for name in sorted(_EXPECTED):
        pkg_attr = getattr(_cfg_pkg, name, _MISSING)
        assert pkg_attr is not _MISSING, (
            f"config.{name} is NOT re-exported in config/__init__.py"
        )
        # Resolve the canonical object from its authoring submodule
        mod = _resolve_submodule(name)
        assert mod is not None, f"cannot find source submodule for {name}"
        canonical = getattr(mod, name)
        assert pkg_attr is canonical, (
            f"config.{name} is {pkg_attr!r} (from {type(pkg_attr).__module__}), "
            f"expected {canonical!r} (from {mod.__name__})"
        )


def test_facade_has_no_spurious_re_exports():
    """The config facade MUST NOT accidentally re-export names from standard library
    or other packages that are imported internally by submodules — only the
    deliberate re-exports listed in ``__all__`` or imported in ``__init__.py``."""
    import charon.config as _cfg_mod
    from charon import config as _cfg_pkg

    # Build the set of intentionally re-exported names from __init__.py
    declared = set(getattr(_cfg_mod, "__all__", []))
    # Collect all non-private, non-dunder attributes on the config package
    actual_public = {
        n for n in dir(_cfg_pkg)
        if not n.startswith("_") and n not in _STDLIB_FALSE_POSITIVES
    }
    # Every name that is accessible on the package that isn't a stdlib artefact
    # MUST be in __all__ (and vice versa for the public surface we care about).
    extra = actual_public - declared
    # __path__, __spec__, __name__, etc are fine — filter those out
    extra -= _DUNDER_OK
    # Submodule names are automatically accessible as package attributes;
    # they are not deliberate re-exports and should not be in __all__.
    extra -= _SUBMODULE_NAMES
    assert not extra, (
        f"config/__init__.py exposes public name(s) not listed in __all__: {sorted(extra)}"
    )


# ── helpers ──────────────────────────────────────────────────────────────────

_MISSING = object()

# Names that Python injects onto every package and we should never flag.
_DUNDER_OK = {"__name__", "__doc__", "__package__", "__loader__", "__spec__",
              "__path__", "__file__", "__cached__", "__builtins__"}

# Standard-library names that sometimes leak via ``from __future__ import annotations``
# or other import side-effects in submodules.  These are not config symbols.
_STDLIB_FALSE_POSITIVES: set[str] = set()

# Submodule names that are accessible as package attributes (normal Python behaviour).
# They appear in dir() but are not deliberate re-exports.
_SUBMODULE_NAMES = {"annotations"}  # from __future__ import annotations
_SUBMODULE_NAMES |= {p.stem for p in Path(__file__).resolve().parent.parent.joinpath(
    "src", "charon", "config",
).glob("*.py") if p.name != "__init__.py"}

_NAME_TO_MODULE: dict[str, str] | None = None


def _build_name_map() -> dict[str, str]:
    """One-time build: {public_name -> submodule_name} by parsing every submodule."""
    result: dict[str, str] = {}
    config_pkg = Path(__file__).resolve().parent.parent / "src" / "charon" / "config"
    for fp in sorted(config_pkg.glob("*.py")):
        if fp.name == "__init__.py":
            continue
        mod_name = f"charon.config.{fp.stem}"
        for name in _public_names_of_module(fp):
            if name in result:
                raise AssertionError(
                    f"name {name!r} defined in both {result[name]} and {mod_name}"
                )
            result[name] = mod_name
    return result


def _resolve_submodule(name: str):
    """Return the submodule object where ``name`` was originally defined."""
    import importlib
    global _NAME_TO_MODULE
    if _NAME_TO_MODULE is None:
        _NAME_TO_MODULE = _build_name_map()
    mod_name = _NAME_TO_MODULE.get(name)
    if mod_name is None:
        return None
    return importlib.import_module(mod_name)
