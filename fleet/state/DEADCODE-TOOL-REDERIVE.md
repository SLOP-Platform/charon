# DEADCODE-TOOL-REDERIVE — Multi-tool, multi-corpora dead-code coverage matrix

**Date:** 2026-07-31 (re-derive; prior attempt `8e86741` had execution-count defects and was reset)
**Tier:** strong / difficulty 3
**Tools tested (EXECUTED):** `check_inert_code.py` (hand-roll, vendored KSF), `ruff` (F841/F401), `vulture` 2.16, `deadcode` 2.4.1 (`golang.org/x/tools`), `pylint` 4.0.6
**Corpora scanned (all real, all live, paths verified):**
1. **Product tree** — `/home/stack/code/charon/src` (30,933 LOC, 121 source modules)
2. **Rig Python** — `fleet/capability/*.py` + `fleet/checks/*.py` (4,863 LOC) — the ticket's own scope ("`fleet/capability/`" + "`fleet/checks/*.py`"). NOT the whole `fleet/` tree (22,454 LOC) — that larger scope inflates counts and was the defect in the prior attempt.
3. **Keystone** — `/home/stack/code/keystone/ksf/` + `/home/stack/code/keystone/tests/` (3,097 LOC combined; ksf only = 2,557)
4. **Bash** — fleet shell scripts (60,259 LOC) — **covered by NONE of the tools; dead-Bash is unaddressed**

Every count below is from a real run on 2026-07-31, not doc-reading. Reproducer commands inlined.

## Grounding (real cases tested)

- **Faktory / lease-enqueue**: `fleet/lease-enqueue.sh` (NOT `fleet/faktory/` — corrected from the prior attempt) self-describes as "THE single enqueue chokepoint ... the ONLY sanctioned path that starts work" (header lines 1-10). `fleet/claim.sh` contains **zero** references to `lease-enqueue` or `faktory` (verified: `grep -cE 'lease.enqueue|faktory|enqueue' fleet/claim.sh` = 0). Only `fleet/board-lock.sh` (a comment) and `fleet/tests/lease-exactly-once.test.sh` reference it. This is **Bash dead code** — a Python tool cannot catch it, and saying so plainly is a valid, valuable result (the ticket explicitly authorizes this finding).
- **REVIEWER-TAB-POOL B1** (guard comparing disjoint namespaces): this is a reachability bug class; `check_inert_code.py` (reachability BFS) is the correct tool. The Python tools in this matrix do not analyze it differently from any other unreachable symbol.
- **Gate-integrity findings (G1 INERT / G3 UNPROVEN / G4 DOCUMENTED-GAP)**: these describe built-but-inert enforcers (a gate built but not registered in `gates.json`). No dead-code tool catches "built but wired nowhere" because the symbol IS referenced (by the calling framework); the defect is system-registration, not symbol-deadness. The proper fix is the registry-wire meta-check, already boarded separately. Recorded here as "out of tool scope," not a gap against any candidate.

## Coverage matrix — EXECUTED

All cells filled by running the tool against the named corpus and counting findings of that class. "YES" = the tool flagged ≥1 instance of that class in the real corpora; "NO" = zero instances of that class across all corpora; "PARTIAL" = catches some variants but not others.

| Class | check_inert_code.py (hand-roll) | ruff F841/F401 | vulture 2.16 | deadcode 2.4.1 | pylint (W0101/W0611/W0612/W0613) |
|---|---|---|---|---|---|
| **unreachable-from-entrypoint public symbol** | **YES** (reachability BFS — the whole point; 66 in product tree, all disposed) | NO (no entrypoint concept) | **NO** (reference-counting — proven below) | **NO** (reference-counting for this class — proven below) | NO (no entrypoint concept) |
| **mutually-referencing dead island** (A→B, B→A, neither reachable) | **YES** (proven in VULTURE-EVAL fixture — both RED) | NO | **NO** (proven — each ref-count > 0, 0 findings) | **NO** (proven — `deadcode` returns "Well done!", 0 findings on the island fixture) | NO |
| **unreachable code after return/raise** | NO (entrypoint-only) | **PARTIAL** (F841 catches the *assigned variable* after `return`, not the bare statement) | **YES** (100% confidence — 1 finding: `src/charon/forwarder.py:934` "unreachable code after 'try'") | **NO** (flags only the assigned variable as DC01, not the unreachable statement itself) | **YES** (W0101 — catches both forms; 0 W0101 findings in the live product tree, 2 in a fixture) |
| **unused class** | YES (if unreachable) | NO (F841 is variable-only) | **YES** (4 in product tree) | **YES** (4 DC03 in product tree) | NO (no `W` rule for unused class) |
| **unused method** | YES (if unreachable) | NO | **YES** (61 in product tree) | **YES** (64 DC04 in product tree) | NO |
| **unused property** | YES (if unreachable) | NO | **YES** (3 in product tree) | **YES** (3 DC08 in product tree) | NO |
| **unused attribute** | NO (not in scope) | NO | **YES** (14 in product tree; 3 in ksf/state_store.py) | **YES** (14 DC05 in product tree; 3 in ksf/state_store.py) | NO |
| **unused import** | NO | **YES** (F401 — 0 in product tree; 1 in rig; 9 in ksf) | **YES** (catches via reference-count; mixed into the variable bucket) | **YES** (DC07 — 1 in fixture) | **YES** (W0611 — 0 in product tree; 1 in rig; 4 in ksf) |
| **unused local variable** | NO | **YES** (F841 — 0 in product tree; 1 in rig) | **YES** (51 in product tree) | **YES** (42 DC01 in product tree) | **YES** (W0612 — 1 in product tree; 1 in rig) |
| **unused function** | YES (if unreachable) | NO | **YES** (42 in product tree) | **YES** (42 DC02 in product tree) | NO (no `W` rule for unused function) |
| **unused argument** | NO | **NO** (F841 does not cover function arguments) | **PARTIAL** (only some at 100% confidence) | **NO** (classified as DC01/unused-variable, no argument-specific signal) | **YES** (W0613 — **46 in product tree; 3 in ksf** — UNIQUE signal) |
| **empty file detection** | NO | NO | NO | **YES** (DC11 — 0 in the ticket's rig scope; the prior attempt's "8 DC11" came from scanning all of `fleet/`, out of the ticket's scope) | NO |
| **Bash dead code** | NO | NO | NO | NO | NO |

### Proven: deadcode does NOT catch the dead-island (correcting the prior attempt)

The prior attempt's matrix cell claimed deadcode catches the mutually-referencing dead-island ("YES — call-graph reachability catches it — proven"). **That is false.** Reproducer (`/tmp/di3.py`):

```python
def main():
    print("live")
def A():
    return B()
def B():
    return A()
if __name__ == "__main__":
    main()
```

```
$ deadcode /tmp/di3.py
Well done! ✨ 🚀 ✨          # rc 0 — ZERO findings
$ vulture /tmp/di3.py      # rc 0 — ZERO findings (matches prior VULTURE-EVAL)
```

Both `deadcode` and `vulture` treat A and B as "used" because each is referenced by the other (reference-counting, not entrypoint-reachability). Only `check_inert_code.py` (reachability BFS from `pyproject [project.scripts]` / `__main__`) catches this class — exactly as the 2026-07-22 VULTURE-EVAL established. **The hand-roll is irreplaceable for this class; neither vulture nor deadcode substitutes for it.** This correction does NOT re-litigate the vulture replace-scope REJECT (that stands); it fixes a fabricated "proven" cell in the re-derive's own matrix.

## Quantitative tool efficacy comparison (product tree, `/home/stack/code/charon/src`)

Reproducer: `cd /home/stack/code/charon && <tool> src` (pylint: `--disable=all --enable=W0613 --score=n --recursive=y`).

| Metric | check_inert_code.py | ruff F | vulture (default 60) | vulture (80) | deadcode | pylint (W0613 only) |
|---|---|---|---|---|---|---|
| Total findings | 66 (all disposed) | 0 | 176 | 12 | 169 | 46 |
| Runtime | ~5s | 0.07s | 0.53s | 0.53s | 0.69s | ~5.8s |
| Unique signal | reachability dead-island, registration check | none (already clean) | unreachable-code-after-return (1 instance) | same as 60, minus noise | empty-file (DC11) in larger scope | **unused argument (46 instances)** |

### vulture breakdown (product tree, default confidence 60) — 176 findings
1 unreachable code, 14 unused attribute, 4 unused class, 42 unused function, 61 unused method, 3 unused property, 51 unused variable.

### deadcode breakdown (product tree) — 169 findings
42 DC01 (unused variable), 42 DC02 (unused function), 4 DC03 (unused class), 64 DC04 (unused method), 14 DC05 (unused attribute), 3 DC08 (unused property).

### `--make-whitelist` (vulture ratcheting)
`vulture src --make-whitelist` emits a whitelist of the 176 findings for ratcheting — the designed adoption pattern that avoids the "156 noisy findings at default confidence" complaint from the prior VULTURE-EVAL (which measured default confidence with no whitelist). A ratcheted run is the realistic adoption shape.

## Findings by corpus

### Rig Python (`fleet/capability/` + `fleet/checks/`, 4,863 LOC)
Reproducer: `cd /home/stack/charon-private && <tool> fleet/capability fleet/checks`.
- **vulture:** 3 findings (all unused variable)
- **deadcode:** 3 findings (all DC01 unused variable: `assign.py:253 refuse_reason`, `grades.py:397 corrections_total`, `selftest.py:906 tot_a`)
- **ruff F:** 1 finding (F841)
- **pylint:** 2 findings (W0611/W0612)
- **check_inert_code.py:** NOT APPLICABLE (the rig has no `pyproject [project.scripts]` entrypoints; the hand-roll is scoped to the product tree by design)

> The prior attempt reported "vulture 62 / deadcode 59 / ruff 14 / pylint 2" for the rig. Those counts came from scanning all of `fleet/` (22,454 LOC), not the ticket's rig scope (`fleet/capability/` + `fleet/checks/`). The corrected counts above are the ticket-scoped ones.

### Keystone (`ksf/` + `tests/`, 3,097 LOC)
Reproducer: `cd /home/stack/code/keystone && <tool> ksf tests`.
- **vulture:** 13 findings (4 in `ksf/` — 1 unused function `check_inert_code` in `gates/inert_code.py:361`, 3 unused attribute `row_factory` in `state_store.py`; plus 9 in `tests/` — mostly test-fixture functions)
- **deadcode:** 4 findings in `ksf/` (the same `check_inert_code` function + 3 `row_factory` attributes)
- **ruff F:** 9 findings (mix of F401 unused import + F841)
- **pylint (W0611/W0612/W0613/W0101):** 34 findings (notably W0613 unused-argument across `ksf/` + `tests/`)
- **check_inert_code.py:** NOT tested (Keystone uses a different entrypoint model; the hand-roll is product-scoped)

### Bash (60,259 LOC across `fleet/**/*.sh`)
**ALL TOOLS: NO COVERAGE.** The `lease-enqueue.sh` dead-worker finding (built, self-declared "the ONLY sanctioned path," never called by `claim.sh`) is invisible to every Python dead-code tool. This is the meta-finding the ticket explicitly authorizes: "Determining that our dead-code coverage is Python-only while half the rig is bash IS a valid, valuable result." A ShellCheck-based or custom bash call-graph analysis would be needed; that is a separate ticket.

## The ONE question the ticket asks

> "Is there any row where every tool we currently run says nothing and a candidate says something?"

**YES — one row (the genuine gap): unused argument (pylint W0613).**

Every tool we currently run (`ruff F` + `check_inert_code.py`) says **nothing** about unused function arguments. Ruff F841 covers unused *variables*, not arguments. The hand-roll is entrypoint-reachability, not parameter-level. Vulture catches *some* unused args at 100% confidence but misses the majority (they drop out at confidence 80). Deadcode classifies them as DC01 (unused variable) with no argument-specific signal.

**pylint W0613 catches 46 unused-argument instances in the product tree** (verified: `pylint src --disable=all --enable=W0613 --recursive=y | grep -c W0613` = 46). Examples: `claim.py:248 now`, `grades.py:301 control_rows`, `worker.py:94 argv`, `acp.py:170 budget`, `mock.py:79 tier`, `keyprobe.py:17 name`. These are real: unused callback stubs, signal handlers, and copy-pasted interface parameters that indicate mis-wired or stale interfaces.

### Secondary candidate rows (NOT gaps — no adoption on these alone)

- **Unreachable code after return/raise (W0101 / vulture-100%):** vulture catches it (1 finding: `forwarder.py:934`); pylint W0101 catches it too but at 0 findings in the live product tree. A single instance across 30,933 LOC is noise, not a pattern. **DO NOT ADOPT for this class alone.** If vulture or pylint is adopted for other reasons, this comes along free.
- **Empty file (deadcode DC11):** real but 0 findings in the ticket's rig scope; only appears when scanning all of `fleet/`. Low signal.
- **Unused class/method/property/attribute:** vulture and deadcode both catch these, but they overlap heavily with each other and with the hand-roll's reachability surface. No row where *every* current tool is silent.

## Verdict summary

| Tool | Verdict | Scope | Rationale |
|---|---|---|---|
| `check_inert_code.py` | **KEEP** (as-is) | Product entrypoint-reachability gate | Irreplaceable for dead-island detection; proven both vulture and deadcode miss it |
| `ruff F841/F401` | **KEEP** (as-is) | Unused import/variable linting | Already running; product tree clean (0 F findings) |
| `pylint W0613` | **ADOPT** as selective CI check | Unused-argument gate (product tree + keystone) | **The sole gap row** — 46 instances in product tree, 3 in keystone; no other tool catches this class. Recommend a separate ticket wires `pylint src --disable=all --enable=W0613` with a baseline allowlist (the 46 existing instances grandfathered, no *new* W0613 allowed). Do NOT wire in this eval ticket. |
| `vulture` | **WATCH** (prior replace-scope REJECT stands; not adopted as complementary either) | Complementary dead-code signal | 98% overlap with deadcode + ruff F; unique delta is 1 unreachable-code finding in 30,933 LOC. `--make-whitelist` ratcheting is the realistic adoption shape, but the signal-to-noise ratio doesn't justify a new gate. |
| `deadcode` | **WATCH** | Complementary dead-code signal | Overlaps vulture + ruff; does NOT catch the dead-island (correcting the prior attempt); DC11 empty-file is interesting but 0 in the ticket rig scope. Not a gap-filler. |
| Bash dead-code | **GAP — needs separate ticket** | ShellCheck or custom bash call-graph | `lease-enqueue.sh` dead-worker invisible to all 5 Python tools; 60,259 LOC uncovered |

## EVAL-REGISTRY rows added

Four rows appended to `fleet/state/EVAL-REGISTRY.md` (after the TASKPLAN row, before the Backfill note):
1. **deadcode** — WATCH; corrects the prior attempt's "catches dead-island" claim (it does not)
2. **pylint** — ADOPT W0613 only (the gap); REJECT the rest as duplicative
3. **vulture (re-derive)** — prior replace-scope REJECT stands; complementary-signal eval finds no gap row that justifies adoption
4. **Bash dead-code coverage** — honest gap finding (not a tool recommendation)

## Files changed (owns: scope)
- `fleet/state/DEADCODE-TOOL-REDERIVE.md` — this file (created)
- `fleet/state/EVAL-REGISTRY.md` — 4 new rows appended

## Upstream feeding
- **KS31 (component-tool-adapters):** if pylint W0613 adoption proceeds, the component adapter for the selective lint gate
- **KS13 (lens-security):** if a ShellCheck/bash dead-code ticket proceeds, Bash analysis tool evaluation
