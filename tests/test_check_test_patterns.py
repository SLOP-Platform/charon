"""Red-proof tests for tools/check_test_patterns.py.

Each test creates temp files with specific anti-patterns and verifies the
checker flags them. Clean tests assert the real codebase passes error-free.
"""

from __future__ import annotations

from pathlib import Path

import tools.check_test_patterns as M


class TestCleanCodebase:
    def test_current_codebase_has_no_errors(self) -> None:
        errors, warnings = M.scan_tests("tests")
        assert errors == [], f"unexpected errors: {errors}"


class TestDuplicateNames:
    def test_duplicate_module_function_names_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "test_dup.py").write_text(
            "def test_foo():\n"
            '    """First."""\n'
            "    pass\n\n"
            "def test_foo():\n"
            '    """Second — shadows first."""\n'
            "    pass\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_dup.py")
        assert len(errors) == 1
        assert "duplicate test function name" in errors[0]
        assert "test_foo" in errors[0]

    def test_unique_names_clean(self, tmp_path: Path) -> None:
        (tmp_path / "test_clean.py").write_text(
            "def test_one():\n"
            '    """One."""\n'
            "    pass\n\n"
            "def test_two():\n"
            '    """Two."""\n'
            "    pass\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_clean.py")
        assert errors == []

    def test_class_methods_same_name_different_classes_not_flagged(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "test_classes.py").write_text(
            "class TestA:\n"
            "    def test_foo(self):\n"
            '        """A."""\n'
            "        pass\n\n"
            "class TestB:\n"
            "    def test_foo(self):\n"
            '        """B."""\n'
            "        pass\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_classes.py")
        assert errors == []


class TestMissingDocstrings:
    def test_missing_docstring_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "test_nodoc.py").write_text(
            "def test_no_docstring():\n"
            "    pass\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_nodoc.py")
        assert errors == []
        doc_warnings = [w for w in warnings if "has no docstring" in w]
        assert len(doc_warnings) == 1
        assert "test_no_docstring" in doc_warnings[0]

    def test_present_docstring_not_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "test_doc.py").write_text(
            "def test_with_docstring():\n"
            '    """Catches the class of bug where..."""\n'
            "    pass\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_doc.py")
        assert errors == []
        doc_warnings = [w for w in warnings if "has no docstring" in w]
        assert len(doc_warnings) == 0


class TestParametrizeRatio:
    def test_low_parametrize_ratio_warned(self, tmp_path: Path) -> None:
        content = ""
        for i in range(10):
            content += (
                f"def test_func_{i}():\n"
                f'    """Test {i}."""\n'
                f"    assert True\n\n"
            )
        (tmp_path / "test_low_param.py").write_text(content)
        errors, warnings = M.check_file(tmp_path / "test_low_param.py")
        assert errors == []
        ratio_warnings = [w for w in warnings if "parametrize ratio" in w]
        assert len(ratio_warnings) == 1
        assert any("parametrize ratio" in w for w in warnings)

    def test_adequate_parametrize_ratio_not_warned(self, tmp_path: Path) -> None:
        content = (
            "import pytest\n\n"
            "@pytest.mark.parametrize('x', [1])\n"
        )
        for i in range(3):
            content += (
                f"def test_param_{i}(x):\n"
                f'    """Test {i}."""\n'
                f"    assert x == 1\n\n"
            )
        (tmp_path / "test_ok_param.py").write_text(content)
        # Actually one test with a parametrize decorator, ratio is 1/3 > 0.1
        errors, warnings = M.check_file(tmp_path / "test_ok_param.py")
        assert errors == []
        ratio_warnings = [w for w in warnings if "parametrize ratio" in w]
        assert len(ratio_warnings) == 0

    def test_zero_test_functions_no_ratio_warning(self, tmp_path: Path) -> None:
        (tmp_path / "test_empty.py").write_text(
            "x = 1\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_empty.py")
        assert errors == []
        ratio_warnings = [w for w in warnings if "parametrize ratio" in w]
        assert len(ratio_warnings) == 0


class TestLineCount:
    def test_function_over_50_lines_warned(self, tmp_path: Path) -> None:
        lines = ["def test_big():"]
        lines.append('    """Big test."""')
        for i in range(60):
            lines.append(f"    x = {i}")
        (tmp_path / "test_big.py").write_text("\n".join(lines))
        errors, warnings = M.check_file(tmp_path / "test_big.py")
        assert errors == []
        line_warnings = [w for w in warnings if "lines" in w and "max" in w]
        assert len(line_warnings) == 1
        assert "test_big" in line_warnings[0]

    def test_function_under_50_lines_not_warned(self, tmp_path: Path) -> None:
        (tmp_path / "test_small.py").write_text(
            "def test_small():\n"
            '    """Small."""\n'
            "    assert True\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_small.py")
        assert errors == []
        line_warnings = [w for w in warnings if "lines" in w and "max" in w]
        assert len(line_warnings) == 0


class TestStrictMode:
    def test_strict_mode_exits_nonzero_on_warnings(self, tmp_path: Path) -> None:
        (tmp_path / "test_nodoc.py").write_text(
            "def test_no_docstring():\n"
            "    pass\n"
        )
        exit_code = M.main(["check_test_patterns.py", str(tmp_path), "--strict"])
        assert exit_code != 0

    def test_strict_mode_no_warnings_exits_zero(self, tmp_path: Path) -> None:
        (tmp_path / "test_clean.py").write_text(
            "import pytest\n\n"
            "@pytest.mark.parametrize('x', [1])\n"
            "def test_ok(x):\n"
            '    """Clean."""\n'
            "    assert x == 1\n"
        )
        exit_code = M.main(["check_test_patterns.py", str(tmp_path), "--strict"])
        assert exit_code == 0


class TestSyntaxError:
    def test_syntax_error_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "test_broken.py").write_text("def test_broken(\n")
        errors, warnings = M.check_file(tmp_path / "test_broken.py")
        assert len(errors) == 1
        assert "syntax error" in errors[0]


class TestClassTestMethods:
    def test_class_method_warns_on_missing_docstring(self, tmp_path: Path) -> None:
        (tmp_path / "test_cls.py").write_text(
            "class TestFoo:\n"
            "    def test_bar(self):\n"
            "        pass\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_cls.py")
        assert errors == []
        doc_warnings = [w for w in warnings if "has no docstring" in w]
        assert len(doc_warnings) == 1

    def test_class_method_with_docstring_passes(self, tmp_path: Path) -> None:
        (tmp_path / "test_clsdoc.py").write_text(
            "class TestFoo:\n"
            "    def test_bar(self):\n"
            '        """Catches the class of bug where..."""\n'
            "        pass\n"
        )
        errors, warnings = M.check_file(tmp_path / "test_clsdoc.py")
        assert errors == []
        doc_warnings = [w for w in warnings if "has no docstring" in w]
        assert len(doc_warnings) == 0
