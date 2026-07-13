"""search.py — memory.search MCP tool (stdlib-only, full-text + metadata).

Point-of-need retrieval over fleet/memory/markdown/*.md.  Parses YAML-like
frontmatter (tags, last_referenced), ranks by term frequency, returns top-N
results with snippet + file path.

Usage:
  python3 fleet/memory/search.py <query>          # human-readable
  python3 fleet/memory/search.py --json <query>   # JSON (MCP-callable)
  python3 fleet/memory/search.py --pin             # dump pinned core
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def _memory_dir() -> Path:
    return Path(__file__).resolve().parent / "markdown"


def _pin_file() -> Path:
    return Path(__file__).resolve().parent / "pin.md"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    fm: dict[str, Any] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            fm_text = text[4:end]
            body = text[end + 5 :]
            for line in fm_text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if ":" in line:
                    key, _, val = line.partition(":")
                    val = val.strip()
                    if val.startswith("[") and val.endswith("]"):
                        val = [v.strip() for v in val[1:-1].split(",") if v.strip()]
                    fm[key.strip()] = val
    return fm, body


def _load_files() -> dict[str, dict[str, Any]]:
    memdir = _memory_dir()
    if not memdir.is_dir():
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for f in sorted(memdir.glob("*.md")):
        text = f.read_text()
        fm, body = parse_frontmatter(text)
        entries[f.name] = {
            "path": str(f),
            "name": fm.get("name", f.stem),
            "description": fm.get("description", ""),
            "tags": fm.get("tags", []),
            "last_referenced": fm.get("last_referenced", ""),
            "body": body,
        }
    return entries


def _score(query: str, entry: dict[str, Any]) -> float:
    qlower = query.lower()
    words = set(re.findall(r"\w+", qlower))
    if not words:
        return 0.0

    score = 0.0
    body = entry["body"].lower()
    name = str(entry.get("name", "")).lower()
    desc = str(entry.get("description", "")).lower()

    for w in words:
        score += body.count(w) * 1.0
        score += name.count(w) * 5.0
        score += desc.count(w) * 3.0

    for tag in entry.get("tags", []):
        if tag.lower() in qlower:
            score += 2.0

    return score


def _snippet(body: str, query: str, context: int = 80) -> str:
    qlower = query.lower()
    qwords = re.findall(r"\w+", qlower)
    blower = body.lower()
    best_pos = 0
    best_count = 0
    for m in re.finditer(r"\b" + re.escape(qwords[0]) + r"\b", blower) if qwords else []:
        pos = m.start()
        count = sum(1 for w in qwords if blower[pos : pos + context * 2].count(w))
        if count > best_count:
            best_count = count
            best_pos = pos
    start = max(0, best_pos - context // 2)
    end = min(len(body), best_pos + context // 2 + context)
    snip = body[start:end]
    if start > 0:
        snip = "..." + snip
    if end < len(body):
        snip = snip + "..."
    return snip


def search(query: str, top_n: int = 10) -> list[dict[str, Any]]:
    entries = _load_files()
    scored = []
    for name, entry in entries.items():
        s = _score(query, entry)
        if s > 0:
            scored.append((s, name, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, name, entry in scored[:top_n]:
        results.append(
            {
                "file": name,
                "path": entry["path"],
                "title": entry["name"],
                "tags": entry["tags"],
                "last_referenced": entry["last_referenced"],
                "score": round(score, 1),
                "snippet": _snippet(entry["body"], query),
            }
        )
    return results


def dump_pinned() -> str:
    """Return the PINNED core markdown (loads at session start)."""
    pin = _pin_file()
    if pin.is_file():
        return pin.read_text()
    return ""


def dump_full() -> str:
    """Return the full memory set (legacy — used for comparison in tests)."""
    memdir = _memory_dir()
    if not memdir.is_dir():
        return ""
    parts = []
    for f in sorted(memdir.glob("*.md")):
        parts.append(f.read_text())
    return "\n\n---\n\n".join(parts)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: search.py [--json] [--pin] <query>", file=sys.stderr)
        sys.exit(1)

    json_mode = False
    pin_mode = False
    query_parts = []
    for a in args:
        if a == "--json":
            json_mode = True
        elif a == "--pin":
            pin_mode = True
        else:
            query_parts.append(a)

    if pin_mode:
        out = dump_pinned()
        if json_mode:
            print(json.dumps({"pinned": out}))
        else:
            print(out)
        return

    query = " ".join(query_parts)
    if not query:
        print("Usage: search.py [--json] <query>", file=sys.stderr)
        sys.exit(1)

    results = search(query)
    if json_mode:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"# {r['title']} (score: {r['score']})")
            print(f"  file: {r['file']}")
            print(f"  tags: {', '.join(r['tags'])}")
            print(f"  last_referenced: {r['last_referenced']}")
            print(f"  {r['snippet']}")
            print()


if __name__ == "__main__":
    main()
