# TOOL INVENTORY — owned tools, by trigger

Companion to MANAGER-OPERATING-RULES.md §11 (TOOL-FIRST / reuse-check). That
section states the RULE; this doc is the enumeration — map your intent below
to the exact command. Surfaced at SessionStart alongside the rules (see
bottom of this file for the wiring).

---

## TRIGGER INDEX (read this first)

| Your intent | Reach for |
|---|---|
| About to propose/create new work | `graphify explain "X"` + grep `board/*.md` for `owns:` (reuse-check) -> best-in-class tool eval (tool-first) -> `check_inert_code.py` (is it already built-but-dead?) |
| Reviewing / auditing code | `graphify path/explain`, `tools/check_inert_code.py`, full gate suite (`charon.cli gate`), `leak-guard.sh` |
| Validating the board / planning a wave | `validate_board.sh` -> `wci-contention.sh` -> `status.sh` -> `report.sh` |
| Ranking / trusting a model | `dogfood-eval.sh` -> `dogfood-to-scorecard.sh` -> `capability/grades.py` / `capability/assign.py` |
| Before land/merge | `charon.cli gate`, `preflight.sh`, `/security-review` |

---

## 1. Product code-graph / analysis — graphify

- Binary: `~/.local/bin/graphify` (symlink -> `~/.local/share/uv/tools/graphifyy/bin/graphify`), installed via `uv tool install graphifyy`. MCP server: `graphify-mcp` (same install).
- `graphify explain "X"` — plain-language explanation of a node + its neighbors in the graph. Use for reuse-check ("do we already have X?") and code review orientation.
- `graphify path "A" "B"` — shortest path between two nodes; use to answer "how does A reach B" / blast-radius questions.
- `graphify update <path>` — re-extract + rebuild `graphify-out/graph.json` from current source (no LLM needed; `--force` after refactors that delete code). **This is how you (re)generate the graph** — run from repo root, e.g. `graphify update /home/stack/code/charon`.
- `graphify cluster-only <path>` / `graphify label <path>` — re-cluster / re-name communities on an existing graph (LLM-assisted, optional).
- `graphify diagnose multigraph` — reports same-endpoint edge-collapse risk (graph QA).
- Live graph for charon: `/home/stack/code/charon/graphify-out/graph.json` (5.5MB, rebuilt 2026-07-13).
- `graphify-mcp` — same capabilities exposed as an MCP server for in-session tool calls instead of shelling out.

## 2. Keystone Framework (KSF)

- **Real location**: `/home/stack/code/keystone` (sibling dev checkout, package `keystone-framework`, console script `ksf = ksf.cli:main`). NOT installed on global PATH — invoke via its own venv: `/home/stack/code/keystone/.venv/bin/ksf --repo-root <target-repo> <command>`.
- Charon's `/home/stack/code/charon/.ksf/keystone.db` is a real SQLite DB (tables `decisions`, `built_inventory`, `backlog`, all empty — initialized but never populated; nothing has registered a module/decision against it yet).
- Charon does NOT depend on KSF at runtime — only two files are vendored verbatim into the product repo for the merge gate: `tools/_vendor/ksf_inert_code.py` + `tools/_vendor/ksf_gate_result.py` (see `tools/_vendor/README.md` for re-sync instructions). The live `ksf` CLI's other subcommands (reuse-check, module lifecycle, gate) are NOT wired into any fleet script today — this is a gap, not a dead end: they exist and work, they're just not called from `fleet/*.sh`.
- Subcommands (confirmed via `ksf --help`):
  - `ksf --repo-root <repo> reuse-check <name> [--threshold 0.90]` — **THE reuse-check invocation.** Token-Jaccard similarity (prefers graphify graph when present, else stdlib `difflib`/`tokenize` fallback) against existing `module.toml` surfaces + `src/`. Exit 1 if overlap >= threshold.
  - `ksf --repo-root <repo> module register <name> [--surface ...] [--force]` — registers a module; runs reuse-check first and BLOCKS registration on overlap unless `--force`.
  - `ksf --repo-root <repo> gate` — runs KSF's built-in gates (`ksf/gates/*.py`: coverage_ssot, wiring_alignment, redproof, inert_code, leak_guard, no_pipe_mask, no_skip_game, no_vacuous, fail_loud) via `GateRunner`.
  - `ksf --repo-root <repo> reconcile` — "reconcile-first": re-resolves every `close_proof`; falsified ones reopen to `status=open`.
  - `ksf --repo-root <repo> verify-self` — dogfood meta-harness (KSF verifying itself).
- Product-side adapter for the ONE vendored gate: `tools/check_inert_code.py` (see §3).

## 3. Product gate suite — `/home/stack/code/charon/tools/check_*.py`

Umbrella runner: `cd /home/stack/code/charon && PYTHONPATH=src python3 -m charon.cli gate` (per `tools/gates.json` id `charon-gate`; currently wires ruff, mypy, boundary, version, gate-registry — see `tools/gates.json` for the full registered set vs. what the umbrella actually invokes, they are not 1:1 today).

One line each (13 checks + registry):

- `check_arch.py` — architecture layer isolation: engine never imports gateway, no circular imports, stdlib-only core, product-clean.
- `check_boundary.py` — no SLOP/build-rig references leak into `src/`.
- `check_inert_code.py` — 0-caller unreachable public symbols in `src/charon` (built-but-never-wired); undisposed dead code fails, tracked ones read from `tools/inert-code-disposition.json`.
- `check_security.py` — bare excepts, secrets in source, hardcoded IPs, `eval`/`exec`/`shell=True`.
- `check_test_patterns.py` — duplicate test names, missing docstrings, parametrize ratio, oversized test functions.
- `check_public_clean.py` — personal/internal info leak guard (internal IPs, home paths, rig/host names, hex secrets) in tracked files — the public-repo-safety gate.
- `check_gate_registry.py` — self-validator: every gate in `gates.json` has a living enforcer, no two gates overlap.
- `check_no_rig_import.py` — product hot path never imports the build-rig grader (`benchmark`/`grader_daemon`).
- `check_version.py` — single source of truth for version in `pyproject.toml`.
- `check_workflows.py` — CI workflow policy: action-ref pin, fragile Windows-smoke patterns, packaging-trigger path scoping.
- `check_catalog_case_quant.py` — catalog/routing/config mismatch detector (casing + quantity drift).
- `check_decisions.py` — `DECISIONS.md` register integrity + cross-reference validity.
- `render_review_log.py` (in `gates.json` as `render-review-log`) — `docs/REVIEW-LOG.md` freshness vs. fragment directory.
- `gates.json` — the gate REGISTRY itself; every entry has `enforcer`, `covers`, `invariant`, `red_proof`. Read this file, don't guess what a gate does.

## 4. Fleet rig scripts — `/home/stack/charon-private/fleet/*.sh`

- `validate_board.sh` — PREFLIGHT GATE, run before launching ANY wave/opening tabs; exit 0 = safe to launch.
- `wci-contention.sh` — scans every ticket's `owns:` field; flags files owned by >= N tickets as a god-file DECOMPOSE CANDIDATE. `--generate` turns each candidate into a tracked `priority: 1` board ticket (`WCI-DEC-*`, one per PATH, idempotent, self-parking); `--strict` is the launch-time collision gate; `--ratchet DAYS` escalates an ignored auto-ticket. Fail-CLOSED: bad args / missing board / zero tickets scanned exit 2.
- `status.sh` — manager dashboard: ground-truth live droid processes + board/claim age + open PRs/CI (no heartbeat proxies).
- `report.sh` — renders the ONE canonical roadmap report from `state/ROADMAP.tsv` (edit the TSV, never hand-type status elsewhere).
- `preflight.sh` — REDS REGISTRY driver (build-rig only): re-verifies every known red deterministically against `reds.tsv`; closes only on a passing `check_cmd`.
- `decompose.sh` — DEC-DRIVER: runs the product decomposer engine on one broad ticket, emits N disjoint single-domain sub-tickets back to the board.
- `branch-reaper.sh` — reaps merged branches + stale worktrees; dry-run-by-default given delete blast radius.
- `land.sh` — THE sanctioned merge path: commit -> GATE (refuses on red) -> branch -> push -> PR -> merge -> sync local base. (Raw `git push`/`git merge` are deny-listed; this is the allowed wrapper.)
- `handoff.sh` — generates the machine-state section of `SESSION-HANDOFF.md` (`SESSION=<name> bash fleet/handoff.sh > fleet/SESSION-HANDOFF-<name>.md`).
- `model-scorecard.sh` — per-model x per-work-class performance ledger; subcommands `append | render | reviewed | --due`.
- `model-detention.sh` — scorecard -> assignment guardrail: a model that crosses a redline is DETAINED (dropped from that tier's failover chain for that work_class).
- `add-provider.sh` — ONE command to add a provider to the live Charon gateway (`fleet/add-provider.sh [--dry-run] <name> <base_url> <local-key-file> [model:upstream ...]`).
- `leak-guard.sh` — worktree-leak guard library: catches a droid that wrote into the MAIN checkout instead of its assigned worktree.

## 5. Dogfood/eval + capability tools

- `benchmark/dogfood-eval.sh <ticket-label> <ticket-brief-file> <model1> [model2 ...]` — Path C: ranks candidate gateway models by REAL small-ticket outcome under a monitored audit (the real trust signal, vs. synthetic S0-S6/T1-T12 pre-screens).
- `benchmark/dogfood-to-scorecard.sh` — maps a dogfood-eval `SUMMARY.md` into `model-scorecard.tsv` `source=live` append commands; does NOT write the ledger itself (owned by the `bench-grader` integrity user) — it generates a script the operator runs as `sudo -u bench-grader bash <generated-file>`.
- `capability/grades.py` — grades-provider: model x work_class capability signal (build #14), the read side of the scorecard.
- `capability/assign.py` — `assign()`: ticket -> best agent/model with a human-readable rationale, consuming grades.py's signal.

---

## Where MANAGER-OPERATING-RULES.md is surfaced at SessionStart

Wired in `/home/stack/code/charon/.claude/settings.local.json` (project-level,
NOT `~/.claude/settings.json`), `hooks.SessionStart[0].hooks`:

1. `cat /home/stack/charon-private/fleet/MANAGER-OPERATING-RULES.md` (statusMessage: "Manager operating rules")
2. `cd /home/stack/charon-private && bash fleet/report.sh` (statusMessage: "Waved roadmap (report.sh)")

Add this file to the SAME hooks array (a third `cat` entry) so the tool
inventory rides in on the same channel as the rules, e.g.:

```json
{
  "type": "command",
  "command": "cat /home/stack/charon-private/fleet/TOOL-INVENTORY.md 2>/dev/null || echo 'TOOL-INVENTORY doc missing'",
  "statusMessage": "Tool inventory"
}
```

(Global `~/.claude/settings.json` SessionStart hooks are unrelated — they run
`update_tasklist.py`, `update_wavemap.py`, `check_push_status.sh`,
`fleet/hooks/session-start.sh` (anti-clobber sync/staleness banner), and
`branch-reaper.sh` dry-run; none of them cat the rules doc.)
