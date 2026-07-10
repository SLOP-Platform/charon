# ADR — Decomposed-by-design creation engine

**Status:** DESIGN / design-of-record (design only; no product or rig code landed by this ADR).
**Date:** 2026-07-09
**Author:** design sub-session (Charon fleet manager)
**Applies to:** BOTH the product (`charon`, `/home/stack/code/charon`) and the build-rig
(`charon-private/fleet`).
**Drives from:** operator directive `decomposed-by-design-not-reactive` (2026-07-09).
**Relates:** ADR-0015 (work-composition-intelligence — the *reactive* WCI this makes *leading*),
`fleet/WCI-METHOD.md`, `fleet/wci-contention.sh`, `fleet/validate_board.sh`,
`charon.cli gate` / `tools/gates.json`, `fleet/BRIEF-TEMPLATE.md`,
memory `charon-own-work-engine`, `standing-blast-radius-lens`,
`wci-ticket-decompose-method`, `disjoint-owns-not-no-dependency`.

---

## 1. Context — the god-file cycle, and why reactive isn't enough

We have fought god-files since early SLOP. The anti-pattern is a loop:

1. **"Reuse" by ACCRETION** — new work is added by *appending* into an existing file
   ("it's related, so it goes here").
2. The file **accretes responsibilities** and becomes a god-file.
3. Multiple tickets then all need to touch it → **contention** (the `owns:` axis collides).
4. We **REACTIVELY decompose** it (behavior-preserving splits, facades, per-commit-green).
5. Repeat on the next file.

Grounded current reality (`wc -l src/charon/*.py`, 2026-07-09) — the tail of the distribution:

```
2043  src/charon/cli.py          <- the standing god-file
 861  src/charon/land.py
 738  src/charon/intake.py
 725  src/charon/proxy_server.py  <- ALREADY decomposed once (SR split), still large
 623  src/charon/config.py
 623  src/charon/gateway.py
 550  src/charon/connect.py
 493  src/charon/api.py
 480  src/charon/proxy.py
 ...
  98  src/charon/router.py        <- the SHAPE we want: bounded, single-responsibility
15108  total (43 modules)
```

The *well-shaped* modules in this same repo — `router.py` (98), `failover.py` (141),
`pools.py` (130), `translate.py` (142), `observability.py` (148) — cluster **under ~400 lines**,
one responsibility each. The files we have had to (or will have to) decompose all sit
**above ~600**. The repo's own distribution gives us calibrated thresholds (§4.2).

`fleet/wci-contention.sh` is our current mechanization, and it is **reactive by design**: it
scans board `owns:` fields and flags any file owned by ≥ N=4 tickets as a *DECOMPOSE CANDIDATE*
— i.e. it fires only **after** the backlog has already mis-sliced onto a god-file. It complements,
but does not replace, a leading control. (`proxy_server.py` reached **25 ticket-owners** before
the reactive split.) `WCI-METHOD.md` Step 3 is likewise a *trigger to refactor debt that already
exists*.

**Decision problem:** move the control from **lagging → leading**. Make new code start in the
shape `proxy_server.py` has *after* its split — bounded, single-responsibility modules with clean
seams — **without** the god-file-then-decompose round trip. Reuse must mean **COMPOSITION**
(import/compose a bounded module), never **ACCRETION** (append into a file). "Bloat by addition"
is the specific enemy.

---

## 2. Decision

Introduce a **decomposed-by-design creation engine**: four mechanization levers that make
decomposition the default at creation time, and make accretion cost more than composition. We
**keep** `wci-contention.sh` unchanged as the reactive safety net; the new levers are its leading
complement.

1. **Required creation-time Module Layout** — every new-code brief/ticket must declare the bounded
   modules it creates (responsibility + budget + seams + why-new-not-append). `validate_board.sh`
   HARD-FAILs a new-code ticket that lacks it.
2. **Leading budget gate** — a per-file budget (lines AND owner-count) that fails when a file is
   over budget, or when a ticket's `owns`/diff would push it over, with **ratchet-down
   grandfathering** so today's god-files warn (don't red the repo) until touched.
3. **Reuse-by-composition lint** — flags a *new responsibility* landing in an already-large file
   instead of a new module (accretion), with an escape-hatch marker for justified additions.
4. **Creation scaffolder** — given a Module Layout spec, emits the decomposed module skeleton
   (files + typed stubs + seams), refusing to emit over-budget or into an over-budget file, so the
   default artifact IS decomposed.

The through-line: **Lever 1 is the human/strategic design pass** (the landscape / blast-radius
lens applied at creation); **Levers 2–3 mechanically enforce** that the design was done and not
silently violated; **Lever 4 makes the decomposed path the path of least resistance** (its input
IS Lever 1's output). Prevention comes from Lever 1; Levers 2–4 make skipping it expensive.

---

## 3. Lever 1 — Required creation-time Module Layout

### 3.1 What counts as a "new-code" ticket

The requirement applies to tickets that **create new modules or subsystems**, detected cheaply as
either:

- `work_class` ∈ `{greenfield-feature, refactor}` (from the existing `work_class:` taxonomy in
  `capability/grades.py`), **or**
- any path in the ticket's `owns:` field that **does not yet exist on disk** (a new file). This is a
  single `os.path.exists()` per owned path, relative to the repo root — no parsing, no git.

Pure edits (`bugfix`, `tests`, `docs`, `frontend` touching existing bounded files) are **exempt** —
they neither create modules nor, by themselves, add responsibilities (Lever 2/3 still guard growth).

### 3.2 Section schema (added to `fleet/BRIEF-TEMPLATE.md`)

```
## Module Layout   (REQUIRED for new-code tickets)
For each NEW module this ticket creates:
- module: src/charon/<name>.py            # the bounded file (one per responsibility)
  responsibility: <ONE sentence, ONE responsibility>   # if you need "and", it's two modules
  budget: <=<N> lines                     # the size budget this module commits to (<= HARD, §4.2)
  seams: <imports/composes>               # e.g. imports charon.router, charon.pools (COMPOSITION)
  why-new: <why a new module, NOT an append to <existing>>   # the anti-accretion justification
```

Rules the section encodes (reviewed by a human/adversarial reviewer, not machine-graded):

- **One responsibility per module.** A responsibility line needing "and"/"plus"/a comma-list is a
  signal to split into two modules.
- **Seams are composition.** "seams" names the *existing bounded modules this one imports*, i.e.
  reuse-by-composition made explicit. If reuse is expressed as "add to `X`", that is accretion and
  must be rejected in review.
- **`why-new` is mandatory** and must answer *why this is a new module rather than a function added
  to an existing file* — the exact decision that, made lazily, creates god-files.

### 3.3 `validate_board.sh` check (HARD-FAIL)

Mirror the existing `## Dependencies & sequence` D&S check (already in `validate_board.sh`):

- For each **live** (not done, not parked) ticket that is a **new-code ticket** (§3.1), open its
  linked `prompt:` file and require a `## Module Layout` section (case-insensitive regex, same
  pattern as `_DS`).
- Missing → `RED  module-layout-missing: <ticket> is a new-code ticket (creates <new-path> /
  work_class=<wc>) but its prompt lacks a '## Module Layout' section — declare the bounded modules,
  budgets, seams, and why-new-not-append (fleet/ADR-DECOMPOSED-BY-DESIGN.md §3).`
- Structural-only: the validator checks the section **exists** and is non-empty. Semantic quality
  (is the responsibility truly singular? is `why-new` honest?) stays a **review-gate** judgment —
  same division of labor as the WCI enforcer ("semantic intent is NOT machine-checkable in bash —
  surfaced advisory only").

---

## 4. Lever 2 — Leading budget gate (flip contention lagging → leading)

### 4.1 Two dimensions

1. **Lines** — applies to product source (`src/charon/*.py`) and rig Python. Cheap: count `\n`.
2. **Owner-count** — applies to the **board** (rig): distinct live tickets whose `owns:` includes a
   file. This is exactly what `wci-contention.sh` already computes; Lever 2 turns it *leading* by
   evaluating it **at ticket-authoring / wave-launch time** and FAILING (not just advising) when an
   over-budget file would also cross the owner threshold.

### 4.2 Concrete starting thresholds (justified + tunable)

| Dimension | WARN (soft) | HARD (fail) | Justification |
|---|---|---|---|
| Lines / module | **400** | **600** | Repo's own bimodal distribution: well-shaped modules cluster < ~400; every file we have decomposed or must decompose sits > ~600. 400 = "you are leaving the healthy band"; 600 = "you are now a god-file." |
| Live owners / file | **3** | **4** | 4 aligns EXACTLY with `wci-contention.sh`'s default `N=4` DECOMPOSE-CANDIDATE threshold — the leading gate fails at the same point the reactive detector fires, so the two never disagree. 3 = "approaching; decompose before the 4th ticket lands." |

Thresholds live in one place (`tools/file_budget_baseline.json` header or a `BUDGET` constant in
the enforcer) so they are tunable without touching logic. Owner thresholds stay pinned to
`wci-contention.sh`'s `N` to keep leading/lagging in lockstep.

### 4.3 Where it runs

- **Product:** new enforcer `tools/check_file_budget.py` (domain `size` — a **new** domain added to
  `ALL_DOMAINS` in `check_gate_registry.py`, since the registry forbids two gates sharing a domain),
  registered in `tools/gates.json`, wired into `gate_runner.CHECKS` so it runs under
  `charon.cli gate` **and** CI. Scope: `src/charon/*.py` (the request-path / product surface).
- **Rig:** `validate_board.sh` adds the owner-count dimension — a file whose set of **live** owners
  would reach ≥ 4 while the file is also over the **line** WARN budget → `RED  budget-owner:
  decompose <file> before adding (N live owners on a >400-line file — split along seams first, then
  re-slice owns; WCI-METHOD Step 3)`. Line-budget for rig Python can reuse `check_file_budget.py`
  pointed at the rig tree (Phase 3).

### 4.4 Metric computation (cheap)

- Lines: `sum(1 for _ in open(path))` per `*.py` under scope. O(repo) newline count, sub-second.
- Owners: already produced by the `wci-contention.sh` awk aggregation; `validate_board.sh` already
  builds `path_owners`. No new scan.

### 4.5 Grandfathering — ratchet-down, never red the repo on day one

The hazard: turning on a 600-line HARD gate reds `cli.py`, `land.py`, `intake.py`,
`proxy_server.py`, `config.py`, `gateway.py` immediately and blocks all work. Avoid with a
**baseline + ratchet**:

- Commit `tools/file_budget_baseline.json` = a snapshot of every currently-over-budget file and its
  **current line count** (generated once: `check_file_budget.py --write-baseline`).
- Gate policy:
  - A file **in** the baseline: fails **only if it GREW** beyond its baseline count (ratchet-down —
    you may shrink it, never grow it). Being over 600 is *warned*, not blocked, as long as you don't
    make it worse. Each PR that trims it lowers the baseline (auto-updated on green).
  - A file **not** in the baseline (i.e. new or currently healthy): **HARD-fails at 600**, WARNs at
    400. New code is born under budget; healthy code cannot rot past the ceiling.
- Effect: day-one CI stays green; every *touch* of a god-file must at least not enlarge it, and the
  incentive is to peel responsibilities out (which shrinks it) — the monotonic path toward the
  decomposed shape without a big-bang refactor.

---

## 5. Lever 3 — Reuse-by-composition lint (accretion detector)

### 5.1 Heuristic

Fire when **a new responsibility lands in an already-large file** instead of a new module:

- The touched file is an **existing** file already ≥ the **WARN** line budget (400), **and**
- the ticket/diff **adds new top-level symbols** to it — count added lines matching
  `^(def |class |async def )` at column 0 in the file's diff (a *new* top-level `def`/`class` =
  a new responsibility), as opposed to edits *inside* existing symbols.

Cheap signal: `git diff --unified=0 <file>` + a column-0 `def/class` add count. N ≥ 1 new
top-level symbol added to an already-large file ⇒ flag.

### 5.2 False-positive controls

- **Size floor:** only fires on files already ≥ 400 lines. Small/young files grow freely.
- **Escape-hatch marker** (same pattern as the WCI `real-dep:` justification): a ticket may carry
  `accretion-ok: <file> <reason>` to declare a genuinely-cohesive extension (e.g. one more case in a
  dispatch table that must live with its peers). Marked → advisory, not blocking. Unmarked → flag.
- **Excludes tests** (`tests/**` naturally accretes cases — the whole point of a test file) and
  **pure docstring/comment/whitespace** additions (no new executable symbol).
- **Phase-gated severity:** advisory (WARN) in Phase 1–2; promotable to HARD in Phase 3 once
  false-positive rate is measured (see acceptance criteria).

### 5.3 Where it runs

Rig-first: a `fleet/checks/accretion.sh` (or a `charon.cli gate` sub-check on the product side)
invoked at PR/land time against the unit's diff. It complements Lever 2: Lever 2 catches *size*,
Lever 3 catches *the act of adding a responsibility* even before the size ceiling is hit.

---

## 6. Lever 4 — Creation scaffolder ("the engine that creates files")

### 6.1 Placement (memory `charon-own-work-engine`)

A native module `src/charon/scaffold.py` in the work-engine, fronted by `charon scaffold` (CLI) and
a thin `fleet/scaffold.sh` wrapper for rig use. **Dev/build-time only** — honors ADR-0007 **D11
anti-dilution**: not imported on the gateway request path, no install-footprint cost to gateway
users.

### 6.2 Interface

```
scaffold(layout: ModuleLayout) -> list[Path]
# ModuleLayout is parsed from the '## Module Layout' brief section (Lever 1) — one schema,
# one source of truth: the design you must write anyway IS the scaffolder's input.

charon scaffold --from-brief <brief.md>     # parse the section, emit skeletons
charon scaffold --dry-run                    # print the file plan, write nothing
```

Per declared module it emits:

- the module file with a **header docstring** carrying `responsibility`, `seams`, and the committed
  `budget` (so the intent is legible in-file);
- `import` lines for each declared **seam** (composition wired in, not stubbed prose);
- the declared public functions/classes as **typed stubs** raising `NotImplementedError`;
- a matching `tests/test_<module>.py` skeleton.

### 6.3 How it uses Levers 1–2 (enforcement by construction)

- **Refuses** to emit a module whose declared `budget` > HARD (600) — you cannot scaffold a planned
  god-file.
- **Refuses** to emit *into* an existing over-budget file — the only way to add to a large file
  through the scaffolder is to create a new bounded module and wire a seam (composition), which is
  precisely the behavior we want to be the default.
- Its input being Lever 1's section means: **write the layout once → validate_board accepts it →
  scaffolder materializes it.** The decomposed skeleton is the cheapest path to starting code.

---

## 7. Integration map

| Existing infra | Change |
|---|---|
| `fleet/wci-contention.sh` | **UNCHANGED** — kept as the reactive detector / safety net. Levers are its leading complement (owner threshold pinned to its `N`). |
| `fleet/validate_board.sh` | +Lever 1 check (`## Module Layout` required for new-code tickets); +Lever 2 owner-budget RED. Same style as existing D&S / work_class / WCI checks. |
| `fleet/BRIEF-TEMPLATE.md` | +`## Module Layout` section (schema §3.2); note it is REQUIRED for new-code tickets and is the scaffolder's input. |
| `charon.cli gate` / `tools/gates.json` / `tools/gate_runner.py` | +`file-budget` gate (new domain `size`, enforcer `tools/check_file_budget.py`) in `CHECKS`, `gates.json`, `ALL_DOMAINS`; runs in CI. |
| `tools/check_gate_registry.py` | add `"size"` to `ALL_DOMAINS`. |
| work-engine (`src/charon/`) | +`scaffold.py` (Lever 4), dev-time only (D11-safe). |
| `fleet/WCI-METHOD.md` | +a "Step 0 — decompose BY DESIGN at creation" pointer to this ADR (leading complement to Steps 2–3). |
| ADR-0015 (WCI) | this is the *leading* half of the same doctrine; a numbered **product** ADR (0016) should ratify the `src/` pieces (`check_file_budget.py`, `scaffold.py`, `size` domain) when built. |

---

## 8. Blast radius (required)

- **Existing tickets:** new-code tickets in flight will start RED on `validate_board.sh` until they
  add a `## Module Layout` section. Mitigation: Lever 1 lands **warn-only for one wave** (§9 Phase
  1), then flips to HARD — so no in-flight ticket is blocked without notice.
- **CI:** Lever 2 could red the whole repo on day one (six files > 600). The **baseline + ratchet**
  (§4.5) is the specific guard: day-one CI stays green; only *growth* of a baseline file or a *new*
  file over ceiling fails. Adds one sub-second check to `gate`/CI.
- **Fleet velocity:** small per-ticket authoring tax (write the Module Layout). Offset: Lever 4
  turns that same layout into generated skeletons, and decomposed-from-birth work has **zero
  reactive-decompose tax** later (the expensive part today: `proxy_server.py`'s 25-owner split, the
  looming `cli.py` split). Net: front-load minutes, save wave-scale wall-clock.
- **False-positive risk (gate blocking legit work):** the real risk. Controls: (a) baseline/ratchet
  never blocks pre-existing state; (b) Lever 3 excludes tests + has an `accretion-ok:` escape hatch;
  (c) Lever 3 ships advisory first, promoted to HARD only after the FP rate is measured (§10). The
  escape hatches are *marker-based* (auditable in the ticket), not silent overrides — same pattern
  as `real-dep:`.
- **Interaction with DRY / over-fragmentation (where's the line?):** the budget is a **CEILING, not
  a target** — never split a cohesive 120-line module to "look decomposed." Guards against
  fragmentation: (a) a **floor** — the scaffolder refuses/ warns on trivial modules (< ~40 lines /
  a single one-line function) and prefers composition into an existing bounded module; (b) Lever 1's
  `seams` field forces reuse-by-composition, so a new module with a responsibility that *overlaps*
  an existing one should import it, not duplicate it — caught in review. DRY still governs *what* is
  a responsibility; the budget governs *how big* one file of responsibilities may get. Mechanical
  fragmentation-detection is deliberately **not** in Phase 1 (open question Q3).
- **Migration of today's god-files:** none forced. Ratchet-down converts them from "must refactor
  now" into "may not grow; shrinks are rewarded." `cli.py` (2043), `land.py`, `intake.py`,
  `config.py`, `gateway.py`, `proxy_server.py` enter the baseline; each future touch nudges them
  down. Optional: schedule explicit decompose tickets (via the *reactive* `wci-contention.sh`) at
  normal priority — the leading gate just ensures no *new* god-files while we chip at old ones.
- **Does it PREVENT god-files or just move the friction?** Honestly, **both** — and that is the
  design. It *moves* friction from lazy accretion (cheap now, catastrophic later) to explicit design
  (a few minutes now). It *prevents* the pure-mechanical failure modes (unbounded growth via ratchet;
  new-file-over-ceiling via HARD gate; silent accretion via Lever 3). What it **cannot** mechanically
  guarantee is *good seams* — a bad decomposition can still pass the size gate. That residual is
  owned by Lever 1's human/adversarial design review (`standing-blast-radius-lens`). The mechanization
  makes the *bad* path (accrete silently) cost more than the *good* path (design + scaffold), which
  is the strongest lever short of AI-judging architecture quality.

---

## 9. Phased rollout

- **Phase 0 (this ADR):** design-of-record ratified. No code.
- **Phase 1 — leading budget, warn-only:** land `check_file_budget.py` + `size` domain + baseline
  snapshot, wired into `gate`/CI in **WARN mode** (reports, exit 0). Add `## Module Layout` to
  `BRIEF-TEMPLATE.md`; `validate_board.sh` Lever-1 check in **advisory** (WCI-ADVISORY) mode for one
  wave. Goal: observe hit-rate, collect the FP baseline, no blocking.
- **Phase 2 — flip to HARD (leading):** budget gate ratchet-down HARD-fails (grow-a-baseline-file /
  new-file-over-ceiling); `validate_board.sh` Module-Layout check HARD-fails for new-code tickets;
  owner-budget RED live. Lever 3 accretion lint lands **advisory**.
- **Phase 3 — scaffolder + accretion HARD:** land `scaffold.py` + `charon scaffold`; promote Lever 3
  to HARD once measured FP rate is acceptable; extend line-budget to the rig tree; ratify the product
  pieces as ADR-0016.

---

## 10. Acceptance criteria (how we know it works)

1. **No new god-files:** for a defined window after Phase 2, no *new* `src/charon/*.py` file crosses
   600 lines, and no baseline file grows (verified from git history of `file_budget_baseline.json` —
   entries only decrease or drop out).
2. **Layout coverage:** 100% of merged new-code tickets carry a `## Module Layout` section (grep the
   merged prompts).
3. **Leading beats lagging:** `wci-contention.sh` produces **fewer new** DECOMPOSE CANDIDATES over
   time (files reaching ≥4 owners) — the reactive detector should go quieter as the leading gate
   works.
4. **FP rate acceptable:** Lever 3 accretion flags overridden with `accretion-ok:` stay below an
   agreed threshold (e.g. < 20% of fires) before promoting it to HARD.
5. **Revert-detection (would fail if the gate is reverted):** a committed regression test —
   `tests/test_file_budget_gate.py` — that (a) asserts `file-budget` is registered in
   `tools/gates.json` with a living enforcer, and (b) constructs a temp `src/charon/_probe.py` of
   601 lines **not** in the baseline and asserts `check_file_budget.py` exits non-zero. If someone
   deletes/neuters the gate, this test goes RED. Mirror on the rig with a `fleet/tests/` case that
   feeds `validate_board.sh` a new-code ticket lacking `## Module Layout` and asserts exit 1.

---

## 11. Open questions for the operator

1. **Threshold ratification.** Adopt 400 WARN / 600 HARD lines and 3/4 owners? Or a different band?
   (These are calibrated to the current repo distribution; easy to tune.)
2. **`cli.py` (2043).** Baseline-and-ratchet it (no forced refactor, top open question), or schedule
   an explicit decompose ticket now given it is 3.4× the HARD ceiling and the standing worst offender?
3. **Fragmentation guard.** Do we want any *mechanical* over-fragmentation check (e.g. warn on a new
   module < 40 lines, or on N near-duplicate tiny modules), or leave the too-many-tiny-files failure
   mode entirely to review? (Phase-1 stance: review only.)
4. **Lever 3 severity timing.** Comfortable promoting the accretion lint to HARD in Phase 3 on a
   measured FP rate, or keep it permanently advisory?
5. **Product ADR number.** Ratify the `src/` pieces as **ADR-0016** when built, or fold into a
   revision of ADR-0015?
