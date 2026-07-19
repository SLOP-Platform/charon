## DOCS-TWO-MODE — two-mode onboarding review note

**Date:** 2026-06-27
**Branch:** feat/docs-two-mode
**Owns:** README.md, docs/getting-started.md

### What was done

- Replaced the Mode-A-only README intro (bold tagline + 3 bullets) with the
  operator-approved "Charon in 20 seconds" pitch, the "Which mode do I want?" table,
  and terse Mode A / Mode B quickstarts — all copy faithful to the approved draft.
- Added a one-line pointer: "New here? Start with [getting started](docs/getting-started.md)."
- Created `docs/getting-started.md` with the same approved content, expanded with
  the client connection table, Docker path, verify curl, and cross-links to deeper docs.
- All existing README anchors (`## Install`, `## Quick start`, `## Connect a client`,
  `## Failover`, `## Expose it / Docker`, `## Work engine (opt-in)`, `## License`)
  preserved intact. Deep Mode-B jargon (fenced coordinator, AIMD, positive-isolation,
  D0xx refs) remains in "Work engine (opt-in)" — not pulled into the landing section.

### Filename decision

Used `docs/getting-started.md` (not `docs/quickstart.md`). Rationale: "getting-started"
is the obvious landing-doc name and matches the lowercase `docs/docker.md` convention.
README pointer and the file's own title both use "getting started" consistently.

### Constraints verified

- Product-clean: no host-project or build-rig references.
- Agent- and provider-agnostic: `opencode acp` appears only as an *example* ACP backend.
- Commands accurate: all commands match the verified draft exactly (`charon setup`,
  `charon gateway`, `charon intake import`, `charon work --units … --backend acp
  --acp-cmd 'opencode acp'`, `charon ledger`, Docker commands).
- Scope: only `README.md` and `docs/getting-started.md` modified.
- Gate: 560 tests pass, ruff clean, mypy clean, boundary clean, version clean.
