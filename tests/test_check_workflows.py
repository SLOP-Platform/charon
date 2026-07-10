from __future__ import annotations

from pathlib import Path

from tools.check_workflows import main, scan_workflow_file

_GOOD = """\
name: Release

on:
  push:
    branches: [main]
    paths:
      - "src/**"
      - "pyproject.toml"
  pull_request:
    paths:
      - "src/**"

jobs:
  build:
    name: Build package
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Build image
        uses: docker/build-push-action@8b0d3ffb0e0a5b4c8e6c6c8f4a1f8f4a1f8f4a1f
        with:
          push: false

      - name: Run tests
        run: pytest -q
"""

_BAD_THIRD_PARTY_BARE_TAG = """\
name: Release

on:
  push:
    branches: [main]
    paths:
      - "src/**"

jobs:
  build:
    name: Build package
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Build image
        uses: docker/build-push-action@v6
"""

_BAD_FIRST_PARTY_SHA = """\
name: Release

on:
  push:
    branches: [main]
    paths:
      - "src/**"

jobs:
  build:
    name: Build package
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
"""

_BAD_START_PROCESS = """\
name: Windows EXE

on:
  workflow_dispatch:
  push:
    tags:
      - "v*"

jobs:
  build-exe:
    name: Build charon.exe
    runs-on: windows-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Smoke test
        run: |
          Start-Process -FilePath charon.exe -ArgumentList "--help"
          Start-Sleep -Seconds 2
"""

_BAD_MISSING_PATHS = """\
name: Windows EXE

on:
  push:
    branches: [main]

jobs:
  build-exe:
    name: Build charon.exe
    runs-on: windows-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Build
        run: pyinstaller packaging/charon.spec
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(content)
    return f


def test_good_fixture_has_no_violations(tmp_path: Path) -> None:
    f = _write(tmp_path, "release.yml", _GOOD)
    assert scan_workflow_file(f) == []
    assert main(str(tmp_path / ".github" / "workflows")) == 0


def test_third_party_action_bare_tag_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "release.yml", _BAD_THIRD_PARTY_BARE_TAG)
    violations = scan_workflow_file(f)
    assert any("docker/build-push-action" in v and "40-char commit SHA" in v for v in violations)


def test_first_party_action_full_sha_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "release.yml", _BAD_FIRST_PARTY_SHA)
    violations = scan_workflow_file(f)
    assert any("actions/checkout" in v and "major-version tag" in v for v in violations)


def test_start_process_in_run_block_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "windows-exe.yml", _BAD_START_PROCESS)
    violations = scan_workflow_file(f)
    assert any("Start-Process" in v for v in violations)


def test_packaging_workflow_missing_paths_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "windows-exe.yml", _BAD_MISSING_PATHS)
    violations = scan_workflow_file(f)
    assert any("missing paths" in v and "on.push" in v for v in violations)


def test_ci_yml_is_exempt_from_paths_requirement(tmp_path: Path) -> None:
    # Same shape as the missing-paths fixture but named ci.yml — the fast
    # pytest/lint gate is exempt from the packaging-trigger paths: rule.
    content = _BAD_MISSING_PATHS.replace("Windows EXE", "CI").replace(
        "build-exe", "test"
    )
    f = _write(tmp_path, "ci.yml", content)
    violations = scan_workflow_file(f)
    assert not any("missing paths" in v for v in violations)


def test_main_exits_nonzero_when_any_fixture_is_bad(tmp_path: Path) -> None:
    _write(tmp_path, "release.yml", _BAD_THIRD_PARTY_BARE_TAG)
    assert main(str(tmp_path / ".github" / "workflows")) == 1


def test_main_exits_zero_on_repo_workflows_directory_shape(tmp_path: Path) -> None:
    # sanity: an empty workflows dir is trivially clean
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True)
    assert main(str(d)) == 0
