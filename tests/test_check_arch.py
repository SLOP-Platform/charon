"""Red-proof tests for tools/check_arch.py.

Each test plants a specific defect and asserts the checker catches it.
The clean test asserts the real codebase passes.
"""
from __future__ import annotations

from pathlib import Path

import tools.check_arch as M


class TestCleanCodebase:
    def test_current_codebase_passes(self) -> None:
        violations = M.check_engine_isolation(Path("src"))
        assert violations == []
        violations = M.check_gateway_isolation(Path("src"))
        assert violations == []
        violations = M.check_circular_imports(Path("src"))
        assert violations == []
        violations = M.check_stdlib_only(Path("src"))
        assert violations == []
        violations = M.check_product_clean(Path("src"))
        assert violations == []


class TestEngineIsolation:
    def test_engine_imports_gateway_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        eng = src / "charon" / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text(
            "from charon.gateway import GatewayConfig\n"
        )
        violations = M.check_engine_isolation(src)
        assert len(violations) >= 1
        assert any("gateway" in v.lower() and "engine→forbidden" in v for v in violations)

    def test_engine_relative_import_of_proxy_server_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        eng = src / "charon" / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text(
            "from ..proxy_server import UpstreamRoute\n"
        )
        violations = M.check_engine_isolation(src)
        assert len(violations) >= 1
        assert any("proxy_server" in v.lower() and "engine→forbidden" in v for v in violations)

    def test_engine_imports_adapters_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        eng = src / "charon" / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text(
            "from charon.adapters.acp import AcpBackend\n"
        )
        violations = M.check_engine_isolation(src)
        assert len(violations) >= 1
        assert any("adapters" in v.lower() for v in violations)

    def test_engine_imports_cli_config_connect_providers_secrets_flagged(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        eng = src / "charon" / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        # All forbidden in one file
        (eng / "board.py").write_text(
            "from charon.cli import main\n"
            "from charon.config import SandboxPolicy\n"
            "from charon.connect import connect\n"
            "from charon.providers import parse_models\n"
            "from charon.secrets import load_secrets\n"
        )
        violations = M.check_engine_isolation(src)
        # Should flag all 5
        assert len(violations) >= 5

    def test_engine_legitimate_imports_clean(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        eng = src / "charon" / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        ports = src / "charon" / "ports"
        ports.mkdir(parents=True)
        (ports / "__init__.py").write_text("")
        (ports / "backend.py").write_text("class AgentBackend: pass\n")
        (eng / "scheduler.py").write_text(
            "from charon.types import Budget\n"
            "from charon.ledger import Ledger\n"
            "from charon.ports.backend import AgentBackend\n"
            "from .. import coordinator\n"
        )
        violations = M.check_engine_isolation(src)
        # types, ledger, ports.backend, coordinator are all allowed
        assert violations == []


class TestGatewayIsolation:
    def test_gateway_imports_engine_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        eng = src / "engine"
        eng.mkdir()
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text("class Board: pass\n")
        (src / "gateway.py").write_text(
            "from charon.engine.board import Board\n"
        )
        violations = M.check_gateway_isolation(src.parent)
        assert len(violations) >= 1
        assert any("engine" in v.lower() and "gateway→engine" in v for v in violations)

    def test_proxy_server_imports_engine_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        eng = src / "engine"
        eng.mkdir()
        (eng / "__init__.py").write_text("")
        (eng / "scheduler.py").write_text("def schedule(): pass\n")
        (src / "proxy_server.py").write_text(
            "from charon.engine.scheduler import schedule\n"
        )
        violations = M.check_gateway_isolation(src.parent)
        assert len(violations) >= 1
        assert any("engine" in v.lower() and "gateway→engine" in v for v in violations)

    def test_gateway_relative_import_of_engine_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        eng = src / "engine"
        eng.mkdir()
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text("class Board: pass\n")
        (src / "proxy_server.py").write_text(
            "from .engine.board import Board\n"
        )
        violations = M.check_gateway_isolation(src.parent)
        assert len(violations) >= 1
        assert any("engine" in v.lower() for v in violations)

    def test_gateway_legitimate_imports_clean(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "netutil.py").write_text("def is_loopback(): pass\n")
        (src / "gateway.py").write_text(
            "from charon.netutil import is_loopback\n"
        )
        (src / "proxy_server.py").write_text(
            "import json\n"
        )
        violations = M.check_gateway_isolation(src.parent)
        assert violations == []


class TestCircularImports:
    def test_no_cycles_in_clean_graph(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "a.py").write_text("from charon.b import b_func\n")
        (src / "b.py").write_text("from charon.c import c_func\n")
        (src / "c.py").write_text("")
        violations = M.check_circular_imports(src.parent)
        assert violations == []

    def test_simple_cycle_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "a.py").write_text("from charon.b import b_func\n")
        (src / "b.py").write_text("from charon.a import a_func\n")
        violations = M.check_circular_imports(src.parent)
        assert len(violations) >= 1
        assert any("circular-import" in v for v in violations)

    def test_three_node_cycle_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "x.py").write_text("from charon.y import y\n")
        (src / "y.py").write_text("from charon.z import z\n")
        (src / "z.py").write_text("from charon.x import x\n")
        violations = M.check_circular_imports(src.parent)
        assert len(violations) >= 1
        assert any("circular-import" in v for v in violations)

    def test_stdlib_imports_not_in_graph(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "a.py").write_text("import json\nimport os\nfrom pathlib import Path\n")
        violations = M.check_circular_imports(src.parent)
        assert violations == []


class TestStdlibOnly:
    def test_stdlib_and_charon_imports_clean(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "gateway.py").write_text(
            "import json\nimport os\nfrom pathlib import Path\n"
            "from charon.netutil import is_loopback\n"
        )
        violations = M.check_stdlib_only(src.parent)
        assert violations == []

    def test_third_party_import_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "gateway.py").write_text(
            "import requests\n"
        )
        violations = M.check_stdlib_only(src.parent)
        assert len(violations) >= 1
        assert any("stdlib-only" in v for v in violations)

    def test_third_party_from_import_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "proxy_server.py").write_text(
            "from flask import Flask\n"
        )
        violations = M.check_stdlib_only(src.parent)
        assert len(violations) >= 1
        assert any("stdlib-only" in v for v in violations)

    def test_relative_imports_always_allowed(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "gateway.py").write_text(
            "from .netutil import is_loopback\n"
        )
        violations = M.check_stdlib_only(src.parent)
        assert violations == []

    def test_subdirectory_files_not_checked(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon" / "sub"
        src.mkdir(parents=True)
        (src / "mod.py").write_text(
            "import requests\n"
        )
        # Only top-level glob("*.py") — sub/ files are not checked
        violations = M.check_stdlib_only(src.parent.parent)
        assert violations == []


class TestProductClean:
    def test_vendor_name_in_non_docstring_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        eng = src / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text(
            'API_BASE = "https://api.openai.com/v1"\n'
        )
        violations = M.check_product_clean(src.parent)
        assert len(violations) >= 1
        assert any("openai" in v for v in violations)

    def test_vendor_name_in_docstring_not_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        eng = src / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text(
            '"""Anthropic-compatible board module."""\n'
            "class Board:\n"
            '    """Uses openai protocol internally."""\n'
            "    pass\n"
        )
        violations = M.check_product_clean(src.parent)
        assert violations == []

    def test_vendor_in_long_template_not_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        eng = src / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text(
            f'HTML = "{">" * 300}deepseek provider{">" * 300}"\n'
        )
        violations = M.check_product_clean(src.parent)
        assert violations == []

    def test_vendor_name_in_gateway_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "gateway.py").write_text(
            'DEFAULT_BASE = "https://api.anthropic.com"\n'
        )
        violations = M.check_product_clean(src.parent)
        assert len(violations) >= 1
        assert any("anthropic" in v for v in violations)

    def test_vendor_in_proxy_server_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "proxy_server.py").write_text(
            'BACKUP = "https://api.deepseek.com/v1"\n'
        )
        violations = M.check_product_clean(src.parent)
        assert len(violations) >= 1
        assert any("deepseek" in v for v in violations)

    def test_engine_clean_content_passes(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "charon"
        eng = src / "engine"
        eng.mkdir(parents=True)
        (eng / "__init__.py").write_text("")
        (eng / "board.py").write_text(
            "import json\n"
            "class Board:\n"
            '    VERSION = "2.0"\n'
        )
        violations = M.check_product_clean(src.parent)
        assert violations == []


class TestModuleNameHelper:
    def test_module_name_top_level(self) -> None:
        assert M._module_name(Path("src/charon/gateway.py")) == "charon.gateway"

    def test_module_name_nested(self) -> None:
        assert M._module_name(Path("src/charon/engine/board.py")) == "charon.engine.board"

    def test_module_name_init(self) -> None:
        assert M._module_name(Path("src/charon/engine/__init__.py")) == "charon.engine"

    def test_module_name_no_charon(self) -> None:
        assert M._module_name(Path("other/pkg/mod.py")) is None

    def test_resolve_relative_current_pkg(self) -> None:
        assert M._resolve_relative("charon.engine", 1, "board") == "charon.engine.board"

    def test_resolve_relative_parent(self) -> None:
        assert M._resolve_relative("charon.engine", 2, "types") == "charon.types"

    def test_resolve_relative_no_module(self) -> None:
        assert M._resolve_relative("charon.engine", 3, None) == ""


class TestConfig:
    def test_engine_forbidden_set(self) -> None:
        assert "gateway" in M._ENGINE_FORBIDDEN
        assert "proxy_server" in M._ENGINE_FORBIDDEN
        assert "adapters" in M._ENGINE_FORBIDDEN
        assert "config" in M._ENGINE_FORBIDDEN
        # proxy_server decompose modules share the same forbidden gateway boundary.
        assert "proxy_console_assets" in M._ENGINE_FORBIDDEN
        assert "proxy_response" in M._ENGINE_FORBIDDEN
        assert "console_router" in M._ENGINE_FORBIDDEN
        assert "forwarder" in M._ENGINE_FORBIDDEN

    def test_vendor_names_set(self) -> None:
        assert "openai" in M._VENDOR_NAMES
        assert "anthropic" in M._VENDOR_NAMES
        assert "deepseek" in M._VENDOR_NAMES
