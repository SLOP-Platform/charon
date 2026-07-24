# CHARON-FLOWCHART — review / decision note

> Per-ticket fragment; never append to the shared `docs/REVIEW-LOG.md`.
> Owned by ticket `CHARON-FLOWCHART`; this file is the lone exception to
> the `owns: docs/CHARON-FLOWCHART.md` scope for the purposes of leaving
> an audit trail of the build.

## What this ticket delivered

`docs/CHARON-FLOWCHART.md` — a single printable Mermaid `flowchart` map
of Charon's work path + data/request path + gates/quality lane, with a
WIRING / INERT / PARTIAL legend and a `fail-on-revert` self-lint
embedded at the foot of the file (per the ticket's `accept:` clause).

## Why a top chart + three sub-charts (not one monolithic diagram)

A single Charon-end-to-end diagram was attempted first; it exceeded the
practical Mermaid node density for a printable page. Splitting into
**top chart** (system-at-a-glance, ~30 nodes) + **Chart 1** (work intake
pipeline, ~20 nodes) + **Chart 2** (Switchboard data path, ~22 nodes,
the ADR-0011 selection algorithm in pseudo-code) + **Chart 3** (gates
grouped by where they fire, ~44 nodes including all 18 CI gates) gives
the operator one printable page per concern. Cross-references between
charts use the same node labels so an operator can read one and locate
the matching detail in another.

## Wiring truth — what was the actual source

The ticket referenced `fleet/state/WIRING-AUDIT-MATRIX.md`. That file
lives in the operator's private rig (`/home/stack/charon-private/fleet/`)
and is **not in this product repo** — confirmed by `ls fleet/`
(`No such file or directory`) on both this worktree and the main
checkout. The same role is filled here by `tools/inert-code-disposition.json`
(44 entries, 270 lines) plus direct grep evidence for symbols not
catalogued there. The flowchart cites both.

The disposition register gives per-symbol `disposition` verdicts:
**delete** (8 entries, all in `pricing_limits_checker.py`),
**wire** (1 entry, `tool_repair.RepairResult`),
**keep-pending-wiring-rider** (8 entries, RFL-5 `context_shaper`),
**keep-needs-triage** (1 entry, `service.get_app`),
**keep-pending-decision** (1 entry, `engine.reconcile.ReconcileFinding`),
**keep-detector-false-positive-{uvicorn-string-load,module-unreachable-cascade}**
(the rest — false positives of the AST-reachability detector, not
dead code).

## INERT / PARTIAL markings in the diagram

- **Dashed red border** = INERT or PARTIAL (built but not on the hot path).
  Used for `quota.QuotaTracker` (fully implemented, no production
  caller; `pricing_limits_checker.py:296` notes it as the canonical
  reference), `tool_repair` (default off; F29 follow-on, wired via
  `modules=` injection), `speculative` / `consensus` / `catalog_refresh`
  (opt-in modules — `gateway.py:90-110`).
- **Parallelogram shape** = opt-in / pending-wire (used for the same
  three opt-in modules plus `quota`).
- **Solid blue** = WIRED production component.
- **Orange fill** = gate (always a contract).

## Selection algorithm in Chart 2

The `routing_policy` selection order is reproduced as inline pseudo-code
in Chart 2's caption (the operator asked to see the algorithm, not just
the shape). The key bits:
- `chain_for(model)` → who CAN serve it.
- `capability_matrix.supports(work_class)` → capability match.
- `balance.is_drained(provider)` → skip drained (drain-then-park).
- `cost_class_priority` (free → expiring → prepaid → metered → premium)
  + `derived_cost_rank` (LIVE metered $).
- Cooldown EWMA as secondary tiebreak.
- Fail-loud structured 5xx envelope when chain empties
  (`forwarder._FUNDING_CLASS_LABEL` + `_FUNDING_CLASS_REARM`).
- Hand-typed `cost_rank` integer is DELETED (ADR-0016 step #6).

## accept: criteria — what was checked

| criterion | how verified |
|---|---|
| Mermaid `flowchart` block | `grep "```mermaid" docs/CHARON-FLOWCHART.md` → 4 blocks |
| Top chart shows whole flow at a glance | block 1 (TOP) is 100 lines, 37 nodes, 60 edges, 3 subgraphs |
| Coverage: WORK path | Chart 1 has NEED→intake→decompose→plan→board→claim→coordinator→lkg→land→PR, with `acceptance.verify` + `fence.detect_escape` gates on the path |
| Coverage: DATA/request path (Switchboard) | Chart 2 has request→gateway→normalize→guardrails→cache→spend→router→forwarder→provider→response_normalize→meter |
| Coverage: every merge/creation/quality gate | Chart 3 has all 5 gate groups; CI group lists the 18 entries from `tools/gates.json` by id |
| Node ≤ ~4 words + what it does | labels use `<br/>` to stack label + 3-7-word description |
| Edge labels: work/request/cost/signal | the top chart labels edges explicitly (e.g. "Plan", "DONE", "200 + usage", "urllib + key from env"); Chart 1/2 caption tables enumerate payloads |
| Legend: node types + WIRED/INERT styling | the `Legend` section covers shape + fill + border, including the dashed-red INERT rule |
| `fail-on-revert` check | `docs/CHARON-FLOWCHART.md` includes a `<!-- flowchart-mermaid-block -->` sentinel + a runnable self-lint script that asserts (1) file exists, (2) `mermaid` block present, (3) top-chart title literal present. Run from repo root: `python3 -c "import pathlib,re,sys; p=pathlib.Path('docs/CHARON-FLOWCHART.md'); s=p.read_text(); sys.exit(0 if ('\`\`\`mermaid' in s and 'Charon end-to-end at a glance' in s) else 1)"` |

## Known limitations / out of scope

1. **No CI enforcer registered**. The self-lint block in the `.md` is a
   doc-lint (per the ticket's `accept:` text "doc-lint OR test"), not a
   CI gate. Wiring a new `tools/check_charon_flowchart.py` + adding
   `tests/test_check_charon_flowchart.py` + a new entry in
   `tools/gates.json` would require touching files outside this ticket's
   `owns:` (the gates.json / new test / new tool). The script body is
   embedded in the file so a follow-on ticket can lift it verbatim.
2. **The mermaid diagrams were not actually rendered to SVG/PDF in this
   environment** (mmdc requires a Chrome headless-shell that the
   sandbox lacks; `libnspr4.so: cannot open shared object file`).
   Syntax was validated by bracket-balance check + 4-block structural
   inspection. GitHub's Mermaid renderer will produce the SVG/PDF when
   the file is merged (the `mermaid` fenced blocks are standard
   GitHub-Flavored Markdown).
3. **`docs/REVIEW-LOG.md` is regenerated by `tools/render_review_log.py`
   from this and every other fragment** — the operator expects to see
   this fragment roll up into the shared log on the next CI run.

## Sources I read (audit trail)

The full grep / read evidence is in the build's research log
(`/home/stack/.local/share/opencode/tool-output/tool_f69c83df3001cyjacSoMZx1rCe`,
882 lines) — kept for the next refresh.
