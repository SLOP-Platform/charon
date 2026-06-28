"""Verify that .gitleaks.toml allowlists env-var bearer references and CI placeholder
tokens without weakening detection of real hardcoded secrets.

Requires gitleaks to be installed; tests are skipped otherwise.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from charon.land import run_gitleaks

GITLEAKS_AVAILABLE = shutil.which("gitleaks") is not None

pytestmark = pytest.mark.skipif(
    not GITLEAKS_AVAILABLE, reason="gitleaks not installed"
)

# Path to the repo-level config we ship
_REPO_ROOT = Path(__file__).parent.parent
_CONFIG = _REPO_ROOT / ".gitleaks.toml"


def _make_repo(tmp_path: Path, files: dict[str, str], *, with_config: bool) -> Path:
    """Initialise a bare git repo with the given files and optional config."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "T"], check=True)

    for rel, content in files.items():
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)

    if with_config:
        shutil.copy(_CONFIG, tmp_path / ".gitleaks.toml")

    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "test"], check=True
    )
    return tmp_path


# --- env-var bearer reference (no hardcoded value) ----------------------------

def test_envvar_bearer_is_clean(tmp_path: Path) -> None:
    """$ENV_VAR in an Authorization header must not be flagged (no config needed)."""
    repo = _make_repo(
        tmp_path,
        {".github/workflows/release.yml": (
            'curl -H "Authorization: Bearer $CHARON_GATEWAY_TOKEN" https://example.com\n'
        )},
        with_config=False,
    )
    result = run_gitleaks(str(repo))
    assert result.status in ("clean", "unavailable"), (
        f"env-var bearer reference should not be flagged; got {result}"
    )


# --- ci-smoke-token placeholder (allowlisted by .gitleaks.toml) ---------------

def test_ci_smoke_token_is_clean_with_config(tmp_path: Path) -> None:
    """ci-smoke-token must land clean when the repo ships .gitleaks.toml."""
    repo = _make_repo(
        tmp_path,
        {".github/workflows/release.yml": (
            'code=$(curl -s -o /dev/null -w \'%{http_code}\' \\\n'
            '  -H "Authorization: Bearer ci-smoke-token" http://127.0.0.1:8080/v1/models)\n'
        )},
        with_config=True,
    )
    result = run_gitleaks(str(repo))
    assert result.status in ("clean", "unavailable"), (
        f"ci-smoke-token should be allowlisted; got {result}"
    )


def test_ci_smoke_token_is_flagged_without_config(tmp_path: Path) -> None:
    """Baseline: without the allowlist config ci-smoke-token IS flagged (false positive)."""
    repo = _make_repo(
        tmp_path,
        {".github/workflows/release.yml": (
            'curl -H "Authorization: Bearer ci-smoke-token" http://example.com\n'
        )},
        with_config=False,
    )
    result = run_gitleaks(str(repo))
    # Either flagged (expected) or unavailable (gitleaks scan error)
    assert result.status != "clean", (
        "Without config, ci-smoke-token should be flagged by the default curl-auth-header rule"
    )


# --- real hardcoded secret (must STILL be caught even with .gitleaks.toml) ----

def test_hardcoded_token_still_flagged_with_config(tmp_path: Path) -> None:
    """A literal bearer token must not be silenced by .gitleaks.toml."""
    repo = _make_repo(
        tmp_path,
        {".github/workflows/deploy.yml": (
            'curl -H "Authorization: Bearer sk-live-abc123abcdef456789" https://api.example.com\n'
        )},
        with_config=True,
    )
    result = run_gitleaks(str(repo))
    assert result.status == "leaks", (
        f"Real hardcoded secret must still be flagged; got {result}"
    )
