---
description: Roadmap/sequence/status lists render as SIMPLE plain-text 3 columns (id · name · STATUS) grouped by wave — no markdown boxes/tables
metadata: 
name: roadmap-display-plaintext-columns
node_type: memory
originSessionId: a95dc541-223e-4053-8197-6848f0322d6b
type: feedback
tags: [roadmap]
last_referenced: 2026-07-13
---
FEEDBACK (2026-07-11): for roadmap / build-sequence / status lists, the operator wants **simple plain text, NOT markdown boxes/tables**. Layout:

```
Project 5    Router

WAVE 1    Sense
R1    meter-model-provider    DONE
R4    meter-wire              DONE
R5    cost-rank-auto          DONE

WAVE 2    DECIDE (BRAIN)
R2    router-core             NEXT
R3    capability-matrix       DESIGN
```

- Project header line on top; a blank line then each `WAVE n    <Wave Name>` header; ticket rows = three space-aligned columns `id  name(kebab)  STATUS`.
- STATUS uppercase (DONE / NEXT / DESIGN / PARKED / BUILDING).
- Blank line between waves.

Refines [[present-findings-in-color-tables]] — color tables are still right for FINDINGS/decisions/status dashboards; this plain-column form is specifically for roadmap/sequence output (and should inform `fleet/report.sh` / the roadmap HTML generator later).

**MECHANIZED (2026-07-11) — stop re-deriving this every session.** The canonical renderer is `fleet/report.sh` (reads `state/ROADMAP.tsv`, emits Project → Wave → tickets). HARD RULE now in MANAGER-OPERATING-RULES §9: ANY roadmap / "work by project" / "list tickets" / sequence request (mid-session OR at end) is answered by running `fleet/report.sh` and presenting its output **VERBATIM** — NEVER prepend/substitute a summary, rollup, or counts-table (that editorializing was the recurring regression; caught 2026-07-11). Auto-surfaced at SessionStart via a hook in the charon product `.claude/settings.local.json` (runs report.sh right after the rules cat) so the format is on screen before any session improvises. If report.sh output ever looks wrong, fix `state/ROADMAP.tsv` / report.sh — do not hand-render a substitute.
