---
description: "DIRECTIVE — build new code holistically decomposed from the start (bounded, single-responsibility modules, clean seams); reuse by COMPOSITION not accretion; mechanize a LEADING gate so files never grow into god-files needing reactive decompose"
metadata: 
name: decomposed-by-design-not-reactive
node_type: memory
originSessionId: 02f0da30-0dc8-45ce-acbc-4cded96858db
type: feedback
tags: [decomposition, design, wci]
last_referenced: 2026-07-13
---
DIRECTIVE (operator, 2026-07-09): Stop the recurring god-file cycle we've fought since early SLOP. The anti-pattern: "reuse" by APPENDING to an existing file → it accretes responsibilities → becomes a god-file (proxy_server.py had 25 ticket-owners; cli.py=2043 lines; gateway.py, config.py) → contention → REACTIVE decompose → repeat.

**Desired state:** decompose BY DESIGN at creation time (leading, not lagging). When creating anything new (file/module/subsystem), lay it out holistically as bounded, single-responsibility modules with clean seams FROM THE START — the shape proxy_server.py has AFTER its split, but without the god-file-then-decompose trip. Apply the landscape / blast-radius / strategic lens at creation.

**Key rule — reuse by COMPOSITION, not ACCRETION:** DRY/reuse is still right, but reuse means import/compose an existing bounded module, NOT dump new code into it. "Bloat by addition" is the specific enemy.

**Mechanize it (this is the ask — build it into the work-engine, don't just remember it):**
1. Creation-time architecture design pass: any new capability's design MUST output a decomposed module layout (bounded files, responsibilities, seams) before code — a required brief section, not optional.
2. LEADING file/responsibility budget gate: complement `wci-contention.sh` (which flags ≥N-owner files AFTER the fact) with a budget check — a file approaching a line/responsibility/owner cap, OR a ticket whose `owns` would grow a file past budget, is flagged → decompose-first required.
3. A creation scaffolder ("engine that creates files"): given a capability spec, emit the decomposed module skeleton so the default IS decomposed.
4. Every build brief states module PLACEMENT + blast-radius + why-new-module-vs-addition.

Applies to BOTH product (charon) and the rig. Relates [[wci-ticket-decompose-method]] (the reactive detector to complement), [[charon-work-composition-intelligence]], [[charon-own-work-engine]] (where this lives), [[standing-blast-radius-lens]]. Status: doctrine captured; mechanization = design an ADR next (not yet built).
