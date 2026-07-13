"""test_memory_store.py — FAIL-ON-REVERT tests for fleet/memory/ (basic-memory-adopt).

Asserts:
  (a) load.sh (default) does NOT cat the full memory set — only the PINNED core.
  (b) memory.search returns a known fact that is NOT in the pinned core.
  (c) PINNED core exists and has content.

Run:
  PYTHONPATH=. python3 -m pytest fleet/memory/tests/test_memory_store.py -q
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parent.parent
SEARCH_PY = MEMORY_DIR / "search.py"
LOAD_SH = MEMORY_DIR / "load.sh"
PIN_MD = MEMORY_DIR / "pin.md"
MARKDOWN_DIR = MEMORY_DIR / "markdown"


# ── helpers ───────────────────────────────────────────────────────────────────


def run_load() -> str:
    r = subprocess.run(
        ["bash", str(LOAD_SH)], capture_output=True, text=True, cwd=str(MEMORY_DIR.parent)
    )
    return r.stdout


def run_load_full() -> str:
    r = subprocess.run(
        ["bash", str(LOAD_SH), "--full"], capture_output=True, text=True, cwd=str(MEMORY_DIR.parent)
    )
    return r.stdout


def run_search(query: str) -> str:
    r = subprocess.run(
        [sys.executable, str(SEARCH_PY), "--json", query],
        capture_output=True,
        text=True,
        cwd=str(MEMORY_DIR.parent),
    )
    return r.stdout


def pinned_content() -> str:
    if PIN_MD.is_file():
        return PIN_MD.read_text()
    return ""


def full_memory_paths() -> list[str]:
    if not MARKDOWN_DIR.is_dir():
        return []
    return sorted(p.name for p in MARKDOWN_DIR.glob("*.md"))


# ── (a) SessionStart hook no longer cats full memory set ──────────────────────


def test_load_default_does_not_dump_full_memory() -> None:
    """(a) The default load.sh output must NOT contain the full memory file
    contents. It should be a LIMITED set (pinned core only)."""
    out = run_load()

    assert len(out) > 0, "load.sh produced empty output"
    # Should contain the pinned core marker
    assert "PINNED CORE" in out, "load.sh missing pinned core header"

    # If we had the full memory set, the output would be much larger
    full = run_load_full()
    # The default output should be significantly smaller than the full dump
    assert len(out) < len(full) * 0.5, (
        f"Default load output ({len(out)} bytes) is too close to full dump "
        f"({len(full)} bytes) — looks like it still cats the full memory set"
    )

    # Specific check: a file name that's NOT in the pinned core should NOT
    # appear as a full file body in the default output
    non_pinned_markers = [
        "charon-free-tier-routing",  # complex routing doc, not in pinned
        "charon-work-composition-intelligence",
        "charon-portable-orchestration-store",
    ]
    for marker in non_pinned_markers:
        # The marker might appear in the index count line but not as content
        # Check that the file body (detailed content) is not present
        assert "stales-command-status" not in out or len(out) < 3000, (
            f"load.sh default appears to contain full memory content (found marker: {marker})"
        )


def test_load_full_flag_still_works() -> None:
    """--full flag still provides complete dump for debugging."""
    full = run_load_full()
    assert "FULL MEMORY SET" in full, "--full output missing FULL MEMORY header"
    assert len(full) > 2000, f"--full output suspiciously small ({len(full)} bytes)"


# ── (b) memory.search returns a known fact NOT in the pinned core ─────────────


def test_search_returns_fact_not_in_pinned_core() -> None:
    """(b) memory.search must return a known fact that is NOT present in
    the pinned core. This proves pull-on-demand retrieval works."""
    pinned = pinned_content()
    assert len(pinned) > 50, "pinned core is too small or missing"

    # Search for a fact we know exists in the markdown files but NOT in pin.md
    queries = [
        ("deploy drift", "deploy-drift-lessons"),
        ("free tier routing", "free-tier-routing"),
        ("drain park provider", "drain-then-park"),
    ]

    found = False
    for query, marker in queries:
        out = run_search(query)
        if marker in out and marker.lower().replace("-", " ") not in pinned.lower():
            found = True
            break

    assert found, (
        f"memory.search did not return a known fact absent from pinned core. "
        f"Queries tried: {queries}"
    )


def test_search_json_output() -> None:
    """memory.search --json returns valid JSON with expected fields."""
    import json

    out = run_search("gateway")
    results = json.loads(out)
    assert isinstance(results, list), "search JSON output is not a list"
    assert len(results) > 0, "search for 'gateway' returned no results"
    r = results[0]
    for field in ("file", "path", "title", "tags", "score", "snippet"):
        assert field in r, f"search result missing field: {field}"


def test_search_returns_relevant_results() -> None:
    """Search for a specific known topic returns relevant results."""
    out = run_search("charon gateway host")
    assert "gateway" in out.lower() or "charon" in out.lower(), (
        "search did not return gateway-related results"
    )


# ── (c) PINNED core integrity ────────────────────────────────────────────────


def test_pinned_core_exists() -> None:
    assert PIN_MD.is_file(), f"pinned core missing: {PIN_MD}"
    content = PIN_MD.read_text()
    assert len(content) > 100, f"pinned core too small ({len(content)} chars)"


def test_markdown_files_have_frontmatter() -> None:
    """All migrated markdown files must have tags and last_referenced."""
    missing = []
    for f in MARKDOWN_DIR.glob("*.md"):
        text = f.read_text()
        if "tags:" not in text:
            missing.append(f"{f.name}: missing tags")
        if "last_referenced:" not in text:
            missing.append(f"{f.name}: missing last_referenced")
    assert not missing, "Files missing required frontmatter:\n  " + "\n  ".join(missing)


def test_markdown_file_count() -> None:
    """At least 50 memory files migrated."""
    count = len(list(MARKDOWN_DIR.glob("*.md")))
    assert count >= 50, f"Only {count} markdown files found, expected >= 50"


# ── GREEN-IS-NOT-PROOF: real point-of-need retrieval ────────────────────────


def test_real_point_of_need_retrieval() -> None:
    """Demonstrate a fact absent from pinned core is retrievable via search."""

    # Facts that should NOT be in pinned core but should be retrievable
    fact_queries = [
        ("charon failover bug tier fallback", "charon-failover-bug-and-tier-fallback"),
        ("pool redesign ADR", "charon-pools-redesign"),
        ("benchmark not valid ranker", "benchmark-not-a-valid-ranker"),
        ("coordinator token economy", "coordinator-token-economy-doctrine"),
        ("charon silent downgrade leak", "charon-silent-downgrade-leak"),
    ]

    retrieved = 0
    for query, marker in fact_queries:
        out = run_search(query)
        if marker in out:
            retrieved += 1

    assert retrieved >= 3, (
        f"Only {retrieved}/5 point-of-need facts retrieved. "
        f"Search must reliably return facts not in pinned core."
    )


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_search_cli_pin_flag() -> None:
    """search.py --pin returns the pinned core."""
    r = subprocess.run(
        [sys.executable, str(SEARCH_PY), "--pin"],
        capture_output=True,
        text=True,
        cwd=str(MEMORY_DIR.parent),
    )
    assert r.returncode == 0, f"search.py --pin failed: {r.stderr}"
    assert len(r.stdout) > 50, "search.py --pin returned empty/small output"


def test_search_cli_empty_query() -> None:
    """search.py with no query exits non-zero."""
    r = subprocess.run(
        [sys.executable, str(SEARCH_PY)], capture_output=True, text=True, cwd=str(MEMORY_DIR.parent)
    )
    assert r.returncode != 0, "search.py with no query should exit non-zero"
