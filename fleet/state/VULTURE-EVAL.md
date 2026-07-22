# VULTURE-EVAL — `vulture` vs hand-rolled `tools/check_inert_code.py`

**Ticket:** VULTURE-INVESTIGATE-RETIRE-INERT
**Date:** 2026-07-22
**Scope tested:** a rig CI dead-code check, evaluated as a REPLACEMENT for the
product's hand-rolled `tools/check_inert_code.py` (which wraps the vendored KSF
`inert_code` detector, `tools/_vendor/ksf_inert_code.py`).
**Vulture version tested:** `vulture 2.16` (`pip install --user vulture`; latest
was resolved, 2.16 — pinned as `vulture==2.16` in any adoption).
**Verdict: KEEP-HANDROLL / REJECT vulture for this replace-scope.**

Evidence-first per [[confirm-dont-trust-documentation]]. All numbers below are from
real runs against the live product tree `/home/stack/code/charon/src` (read-only)
and a purpose-built reproduction fixture — not docstrings.

---

## TL;DR

`vulture` is a **reference-counting** unused-symbol detector: a name is "used" if
it is referenced *anywhere in the scanned files*. The hand-roll is a
**reachability-from-entrypoint** detector: a public symbol is dead unless it is
reachable, by a BFS over the import/call graph, from a *real* entrypoint
(`pyproject [project.scripts]` / `__main__` guards). Those are different
algorithms, and the difference is the whole point:

- **Vulture MISSES the exact bug class the hand-roll exists to catch** — a
  mutually-referencing "built but never wired in" island (A→B, B→A, neither
  reachable). Reference-counting sees each as used; reachability sees both as
  dead. **Proven below: hand-roll FAILS the island, vulture PASSES it.**
- Vulture has **no registration-awareness and no `@inert_by_design` escape
  hatch** — the two features the prior KSF linter review cited when it rejected
  vulture for the product core.
- Vulture at its default confidence emits **156 findings vs the hand-roll's 66**,
  and the extra volume is a *different, noisier* class (unused local variables,
  dataclass fields, interface/protocol methods), not additional dead public
  symbols. Raising confidence to isolate the noise collapses it to 12 findings
  that are *only* unused locals — never the dead-public-symbol class at all.

The prior KSF review's REJECT was product/stdlib-scoped; re-tested honestly here
for the CI-check/replace scope, the registration-awareness loss is **real and
reproduced**, so KEEP-HANDROLL stands for this scope too.

---

## What the hand-roll catches, and how

`tools/check_inert_code.py` (adapter) + `tools/_vendor/ksf_inert_code.py`
(vendored KSF detector, stdlib `ast` only, zero pip deps):

- **Reachability BFS** from real entrypoints: `pyproject.toml [project.scripts]`
  + `.ksf/entrypoints.json` + `__main__`-guarded modules
  (`ksf_inert_code.py:240-271`, BFS at `:418-437`). A public top-level
  function/class with **zero production callers reachable from an entrypoint**,
  not registered, not `@inert_by_design` = RED
  (`ksf_inert_code.py:490-515`).
- **`@inert_by_design("reason")` allowlist** — an in-source, reason-bearing
  escape hatch (`ksf_inert_code.py:122-136`, `_has_inert_by_design`).
- **`__all__` / entrypoint / value-ref awareness** — exported API, script
  entrypoints, and first-class value references (decorators, kwargs, registry
  assignments) all count as reachable (`ksf_inert_code.py:110-120, 439-462,
  502-509`).
- **Green-without-hiding disposition ledger** — the Charon adapter additionally
  requires *every* 0-caller symbol to carry a structured
  `{reason, disposition ∈ wire|delete|keep-<why>}` entry in
  `tools/inert-code-disposition.json`, and **fails immediately on any UNtracked
  dead symbol** so newly-introduced dead code is caught on the same push
  (`check_inert_code.py:23-33, 112-119, 152-160`).
- **Determinism fix** — sorted first-match so the dead-set does not depend on
  `PYTHONHASHSEED` (`ksf_inert_code.py:274-284`, local patch to vendored KSF).

Real run (`PYTHONPATH=. python3 tools/check_inert_code.py`, product tree):

```
WORK-UNITS: 114
inert-code: 66 dead symbol(s) found, 66 tracked in inert-code-disposition.json
  [delete] charon.pricing_limits_checker.check_pricing_limits
  [keep-pending-wiring-rider] charon.context_shaper.shape
  [keep-detector-false-positive-module-unreachable-cascade] charon.engine.reconcile.reconcile_static
  ... (66 total, all with a structured disposition)
EXIT=0
```

68 disposition entries; all 66 currently-dead symbols tracked (2 stale entries
reported as info). The escape hatch in production is the disposition ledger, not
in-source decorators (0 `@inert_by_design` uses in `src/` today).

---

## What vulture catches on the same real tree

`python3 -m vulture src` (product tree, default `--min-confidence 60`):

- **156 findings**, broken down by kind:

  | kind             | count |
  |------------------|-------|
  | unused method    | 54    |
  | unused variable  | 50    |
  | unused function  | 32    |
  | unused attribute | 14    |
  | unused class     | 3     |
  | unused property  | 2     |

  The 50 "unused variable" + 14 "unused attribute" + most "unused method" hits are
  a **different bug class** than the hand-roll's dead-public-symbol target:
  local variables inside functions, dataclass/enum fields (e.g.
  `engine/reconcile.py:31 OBSOLETE`, `:40 INFO` — enum members), and
  interface/protocol methods (`adapters/acp.py:228 capabilities`,
  `adapters/mock.py:123 capabilities` — implementations of an ABC/Protocol seam).

- **Confidence does not isolate the target class.** Finding counts by confidence:

  | `--min-confidence` | findings |
  |--------------------|----------|
  | 60 (default)       | 156      |
  | 80                 | 12       |
  | 100                | 12       |

  The 12 high-confidence (≥80%) findings are **all unused *local* variables /
  unreachable-code** (`decompose_planner.py:483 self_inner`,
  `proxy_server.py:493 observability`, `routing_policy/drain.py:18 kwargs`,
  `forwarder.py:934 unreachable code`, …) — i.e. ruff/pyflakes `F841`/`F811`
  territory, **not** the dead-public-API class. There is no confidence setting at
  which vulture reports *the hand-roll's class and only that class*.

---

## The decisive gap: reachability vs reference-counting (reproduced)

Fixture (`/tmp/.../vgap/src/`): a real entrypoint plus a mutually-referencing
orphan island never imported by anything reachable.

```python
# src/app.py   — the only entrypoint (pyproject [project.scripts] vgap = "src.app:main")
def main():
    print("entry")
if __name__ == "__main__":
    main()

# src/orphan.py — never imported by app.py; each fn references the other
def dead_a():
    return dead_b()
def dead_b():
    return dead_a()
```

**Vulture** (`python3 -m vulture src`): **0 findings, rc=0 (PASS)** — `dead_a`
references `dead_b` and vice-versa, so each has reference count > 0 and neither is
flagged. This is exactly the "built but never wired in" defect.

**Hand-roll** (vendored KSF detector, same fixture, `modules=[]`):

```
hand-roll passed: False
  inert-code: src.orphan.dead_a unreachable (0 callers) and not registered
  inert-code: src.orphan.dead_b unreachable (0 callers) and not registered
```

**Hand-roll FAILS and flags both; vulture is blind to the whole island.** This is
not a tuning difference — it is a structural false-negative in vulture for the
precise bug class the gate was created for (the docstring cites `tool_repair.py`,
`capability/actuals.py::ActualsLedger`, `pricing_limits_checker.py`,
`engine/reconcile.py` + `board.set_cert()` as historical instances of exactly
this — `check_inert_code.py:11-15`).

---

## Comparison matrix

| dimension | hand-roll (`check_inert_code.py` + KSF) | vulture 2.16 |
|---|---|---|
| algorithm | reachability BFS from real entrypoints | reference-counting over scanned files |
| catches mutually-referencing dead island | **YES (proven)** | **NO (proven — passes it)** |
| registration-awareness (`modules`, entrypoints, `__all__`) | YES | NO |
| `@inert_by_design` reason-bearing allowlist | YES (in-source) | NO (flat whitelist file only) |
| green-without-hiding disposition ledger (newly-dead FAILS same push) | YES (structured `{reason, disposition}`) | NO (whitelist = silent suppression) |
| findings on real tree | 66 dead public symbols, all dispositioned | 156 (mixed classes) / 12 (locals only) |
| extra signal over hand-roll | — | unused locals/attrs — already ruff `F841`/`F401` territory |
| runtime dep | zero (stdlib `ast`) — aligns with stdlib-first core | adds a pinned pip dep |
| determinism | patched (sorted first-match, `PYTHONHASHSEED`-safe) | n/a |

---

## Why not ADOPT-DiD (run both, defense-in-depth)?

The ticket's replace-scope forbids "two overlapping dead-code checkers." Even as a
*purely additive* second signal, vulture's only material coverage *beyond* the
hand-roll is unused **local variables / imports / unreachable code** — which is
`ruff`'s pyflakes `F841`/`F401`/`F811` domain, a linter the product already runs.
So the DiD delta is (a) already covered elsewhere and (b) delivered at vulture's
noisiest, most false-positive-prone confidence band. The hand-roll's class
(unwired public symbols / dead islands) is one vulture *cannot* cover at any
setting. DiD buys a redundant noisy signal for a new pip dep — rejected.

---

## Verdict & reasoning

**KEEP-HANDROLL / REJECT** (`alignment: aligned`). Vulture is a genuinely good,
maintained tool for its own job (unused locals/imports), but it is a
**reference-counting** detector and therefore structurally cannot replace a
**reachability-from-entrypoint** dead-code gate: it passes the exact
mutually-referencing "built-but-never-wired" island the hand-roll is built to
catch (reproduced above), and it lacks the registration-awareness and
`@inert_by_design` / structured-disposition escape hatches that make the
hand-roll's zero-false-negative posture usable without silent suppression. The
prior KSF linter review reached the same conclusion for the product/stdlib scope;
re-tested honestly for the CI-check/replace scope, the conclusion holds. No
vulture wrapper/workflow/canary is shipped. The product's `check_inert_code.py`
is retained unchanged (not touched by this ticket).

**Deferred / not in scope:** none. Vulture could be adopted *separately* someday
as an unused-*locals* linter alongside ruff, but that is a different ticket with a
different scope and is not implied by this REJECT.
