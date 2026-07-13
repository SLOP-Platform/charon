#!/usr/bin/env python3
"""migrate.py — one-shot migration: copy memory markdown files into fleet/memory/markdown/
with added frontmatter (tags + last_referenced).

Source: ~/.claude/projects/-home-stack-code-charon/memory/*.md
Dest:   fleet/memory/markdown/*.md

Run from repo root:
  python3 fleet/memory/migrate.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

TAG_MAP: dict[str, list[str]] = {
    "charon": ["charon"],
    "ksf": ["ksf", "design"],
    "fleet": ["fleet", "build-rig"],
    "droid": ["fleet", "droid"],
    "manager": ["manager"],
    "operator": ["operator"],
    "adversarial": ["review"],
    "review": ["review"],
    "bench": ["benchmark"],
    "gateway": ["gateway", "charon"],
    "slop": ["slop", "mediastack"],
    "bridge": ["bridge", "session"],
    "session": ["session"],
    "decompos": ["decomposition", "wci"],
    "wci": ["wci", "decomposition"],
    "pool": ["pool", "routing"],
    "rout": ["routing"],
    "free-tier": ["free-tier", "routing"],
    "drain": ["drain", "routing"],
    "meter": ["meter", "billing"],
    "cost": ["cost", "billing"],
    "deploy": ["deploy", "ops"],
    "guardrail": ["guardrail"],
    "present": ["presentation"],
    "roadmap": ["roadmap"],
    "handoff": ["handoff"],
    "project": ["project"],
    "product": ["product"],
    "production": ["production"],
    "subsession": ["subsession"],
    "token": ["token-economy"],
    "context": ["context", "token-economy"],
    "optimiz": ["optimization"],
    "blast": ["blast-radius"],
    "standing": ["standing-rule"],
    "directive": ["directive"],
    "feedback": ["feedback"],
    "cadence": ["cadence"],
    "doctrine": ["doctrine"],
    "repo": ["repo", "hygiene"],
    "mismatch": ["catalog"],
    "catalog": ["catalog"],
    "fail": ["failover"],
    "silent": ["debugging"],
    "bug": ["bug", "debugging"],
    "gpt-5": ["openai"],
    "deepseek": ["deepseek"],
    "model": ["model"],
    "tier": ["tier"],
    "quality": ["quality"],
    "parallel": ["parallel"],
    "engine": ["engine"],
    "program": ["program"],
    "pricing": ["pricing", "billing"],
    "billing": ["billing"],
    "provider": ["provider"],
    "config": ["config"],
    "ci": ["ci"],
    "docker": ["docker", "ci"],
    "test": ["test"],
    "gate": ["gate"],
    "green": ["test"],
    "pipeline": ["ci"],
    "blueprint": ["blueprint"],
    "reuse": ["reuse"],
    "design": ["design"],
    "method": ["methodology"],
    "methodolog": ["methodology"],
    "rule": ["rule"],
    "hopper": ["hopper"],
    "build": ["build-rig"],
    "rig": ["build-rig"],
    "concise": ["presentation"],
    "vision": ["vision"],
    "phase": ["cadence"],
    "pause": ["cadence"],
    "slow": ["cadence"],
    "modular": ["modularity"],
    "audit": ["audit", "hygiene"],
    "data": ["data"],
    "guard": ["guard"],
}

TODAY = datetime.now(UTC).strftime("%Y-%m-%d")


def derive_tags(filename: str) -> list[str]:
    name = Path(filename).stem.lower()
    tags: set[str] = set()
    for key, vals in TAG_MAP.items():
        if key in name:
            tags.update(vals)
    if not tags:
        tags.add("memory")
    return sorted(tags)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            fm_text = text[4:end]
            body = text[end + 5 :]
            fm = {}
            for line in fm_text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if ":" in line:
                    key, _, val = line.partition(":")
                    fm[key.strip()] = val.strip()
            return fm, body
    return {}, text


def build_frontmatter(tags: list[str], last_referenced: str = TODAY) -> str:
    return f"---\ntags: [{', '.join(tags)}]\nlast_referenced: {last_referenced}\n---\n"


def migrate_file(src: Path, dst: Path) -> None:
    text = src.read_text()
    fm, body = parse_frontmatter(text)

    tags = derive_tags(src.name)
    fm["tags"] = f"[{', '.join(tags)}]"
    fm["last_referenced"] = TODAY

    lines: list[str] = []
    lines.append("---")
    for key in sorted(fm):
        if key in ("tags", "last_referenced"):
            continue
        lines.append(f"{key}: {fm[key]}")
    lines.append(f"tags: [{', '.join(tags)}]")
    lines.append(f"last_referenced: {TODAY}")
    lines.append("---")

    out = "\n".join(lines) + "\n" + body.lstrip()
    dst.write_text(out)


def main() -> None:
    src_dir = Path(os.path.expanduser("~/.claude/projects/-home-stack-code-charon/memory"))
    fleet_root = Path(__file__).resolve().parent.parent
    dst_dir = fleet_root / "memory" / "markdown"

    if not src_dir.is_dir():
        print(f"ERROR: source directory not found: {src_dir}", file=sys.stderr)
        sys.exit(1)

    dst_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for f in sorted(src_dir.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        dst = dst_dir / f.name
        migrate_file(f, dst)
        count += 1
    print(f"Migrated {count} memory files to {dst_dir}")


if __name__ == "__main__":
    main()
