# Ticket Optimization Pass (2026-06-28) — concurrency, efficiency, sequence, non-Claude-readiness

Manual WCI over the buildable backlog. Goal: max safe concurrency (no two writers per file),
dependency-minimizing waves, every ticket workable by a NON-Claude model via a NON-Claude agent
(self-sufficient goal+body, explicit owns, EXECUTABLE accept, agent-agnostic spec).

## File-ownership / collision matrix (buildable set)
| File | Ticket(s) | Verdict |
|---|---|---|
| `adapters/acp.py` | OBS-CAPTURE | sole writer (after fix below) |
| `proxy_server.py`, `console_work.py` | OBS-UI | sole writer |
| `connect.py` | CLIENT-CONNECT-GUI | sole writer |
| `api.py`, `ports/agent_launch.py` | ORCH-ROUTE | sole writer |
| `engine/{reconcile,scheduler,board}.py` | WCI | sole writer |
| `docs/adr/0015-*`, `docs/DECISIONS.md` | ADR-0015 | sole writer |
| (none — research/design) | DSGN-WCI-PROOF, OHMYPI-ASSESS | no files |

**One collision found & fixed:** OBS-CAPTURE originally "may extend to `engine/scheduler.py`" for a
log-path seam → that collides with WCI (owns `scheduler.py`). **Fix: scope OBS-CAPTURE to
`adapters/acp.py` ONLY** — derive the per-unit log path from the worktree `acp._start` already
receives (no runner change). Now every buildable ticket is the SOLE writer of its files → no merges
needed, all splits are already optimal (one writer per file).

## Optimal sequence (waves)
**WAVE 1 — launch all together (mutually disjoint, full concurrency):**
- ADR-0015 [opus] · DSGN-WCI-PROOF [opus, design] · OBS-CAPTURE [sonnet] · OBS-UI [opus] ·
  CLIENT-CONNECT-GUI [sonnet] · ORCH-ROUTE [opus] · OHMYPI-ASSESS [sonnet, research]
- Rationale: zero shared files; ADR-0015 + DSGN-WCI-PROOF also unblock Wave 2/3 the soonest.

**WAVE 2 — after ADR-0015 merges:**
- WCI [opus] (`real-dep: ADR-0015` — must build against a signed design). Disjoint from any
  leftover Wave-1 work (OBS-CAPTURE is now acp-only), so it overlaps freely.

**WAVE 3 — after WCI merges AND DSGN-WCI-PROOF approved:**
- WCI-FOLLOWON [opus] (auto-slice; needs BOTH the MVP and the §5.1 proof). LARGE; deferred per
  operator until production-ready.

**WAVE 4 — after all build work merges:**
- ATC [audit] — adversarial review of everything committed (see ATC ticket). Runs LAST so it audits
  the integrated whole.

## Non-Claude readiness (per ticket: self-sufficient goal+body ✓, explicit owns ✓, EXECUTABLE accept, agent-agnostic ✓)
The work-spec (## Why / ## What to build) is the agent-facing, product/agent-agnostic part — no
Claude- or Claude-Code-specific instructions; the fleet CONSTRAINTS block (submit.sh / draft PR /
STOP) is HARNESS-facing and ignored when a unit is run via `charon work` (the engine commits +
gates + lands). Each ticket now carries an `accept:` line (executable, what the gate runs):
| Ticket | accept |
|---|---|
| OBS-CAPTURE | `PYTHONPATH=src python3 -m pytest -q tests/test_acp_capture.py` |
| OBS-UI | `PYTHONPATH=src python3 -m pytest -q tests/test_console_work.py` |
| CLIENT-CONNECT-GUI | `PYTHONPATH=src python3 -m pytest -q tests/test_connect_gui.py` |
| ORCH-ROUTE | `PYTHONPATH=src python3 -m pytest -q tests/test_agent_launch_routing.py` |
| WCI | `PYTHONPATH=src python3 -m pytest -q tests/test_reconcile.py` |
| ADR-0015 / DSGN-WCI-PROOF / OHMYPI-ASSESS | design/research — human sign-off, no executable gate |
| ATC | produces a findings doc + fix-tickets — human-reviewed |

## Older on-hold (NOT in this pass — revisit at production-readiness)
DOGFOOD (out-of-tree, no collision), DSGN-WRITEBACK (design), TIER-RECS, PROD-INSTALL pt.2,
UX-POLISH. Several touch `cli.py` → sequence at activation; not scheduled here.
