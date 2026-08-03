# TASK-LIST-DURABILITY-GATE — Assertion A spec (design of record)

Status: **SPEC** (design-only; this ticket builds nothing — see §0.3).
Owner: `TASK-LIST-DURABILITY-GATE` (P0). Consumed by `SESSION-CLOSE-COMPLETENESS-GATE`
as its **Assertion A** ("HARNESS TASKS HAVE A DURABLE HOME" — that board names this
ticket as the assertion owner and says to land it independently and reference it).
Gate class: `rig-meta` — a boundary assertion, not a new detector.

---

## 0. Why this gate exists

### 0.1 The hole

`fleet/MANAGER-OPERATING-RULES.md:17` (§0 HARD STANDING DIRECTIVE) makes TWO
mechanisms mandatory for every coordinator session:

1. **(a) the harness task list** — `TaskCreate`/`TaskUpdate`/`TaskList` (the
   `todowrite` tool). The operator's words: "create an item the moment work is
   identified, BEFORE acting ... it survives every mid-turn redirect."
2. **(b) `fleet/pending.sh`** — the cross-session, monotonically-labelled operator
   action list, surfaced by `preflight.sh`; anything needing the OPERATOR goes here
   so it outlives the session.

The harness list is **session-scoped and writes nothing to the repo**: it exists to
survive mid-turn REDIRECTS, not sessions. Nothing checks the boundary, so any item
left only in the harness list dies silently with the session — **no trace to audit**.
That is the whole class. The absence of any prior session's list IS the evidence.

### 0.2 Measured loss (2026-08-02, recorded on the board ticket)

The session closed with **24 harness tasks, 15 still OPEN**. **SIX had no board
ticket** and would have been lost — including `LAUNCHER-LEAKGUARD-NONFATAL` (5 tabs
killed) and `SPILL-UP-CEILING-SSOT` (spill-up failing closed fleet-wide). They
survived only because the operator asked the question at close. Adjacent worse
shape, on record: a session reminded ~20 times to use the task tool, used it ZERO
times, and failed to deliver work promised in prose.

### 0.3 What this ticket is, and is not

- **Builds nothing.** `substrate: N/A`; both durable stores (board, `pending.sh`)
  already exist and are adopted. The novel slice is the **boundary assertion**:
  *no OPEN task may exist without a durable home*.
- **This spec is the single design of record** for Assertion A. The umbrella build
  ticket (`SESSION-CLOSE-COMPLETENESS-GATE`, which owns
  `fleet/checks/session-close-completeness.sh` + its test) implements A–E in
  `fleet/end-session.sh`; it reads this document for the precise A contract,
  including the exact RED conditions and the fail-on-revert proof it must carry.
- The reverse direction is **NOT in scope**: a board ticket need not appear in the
  harness list. The list is a working set; the board is the record.

---

## 1. The assertion (normative)

> At session close, **every OPEN harness task must map to a durable home** — a
> board ticket id, a live `pending.sh` operator action, or an explicit
> `[DROPPED — <reason>]`. An OPEN task with **no** such home = **RED**, and the
> close is REFUSED with each unmapped task named.

Two independent RED conditions (both fail-loud, both non-vacuous — §2, §3):

- **R1 — NO EXPORT.** The session did not export a task list at all (env unset,
  file missing, or unreadable). RED: "no harness task list exported — export your
  task list at close (`MANAGER-OPERATING-RULES` §0 makes it mandatory)."
- **R2 — UNMAPPED OPEN TASK.** The exported list contains an OPEN task whose text
  resolves to no durable home. RED, listing each unmapped line (line number + text).

GREEN: an export exists AND every OPEN task in it maps to a durable home. An
exported-but-empty list (or one whose tasks are all completed/dropped) is GREEN —
there is no OPEN task to map. **Absence of the export is RED; an empty export is
GREEN.** That distinction is the non-vacuity (see §3).

---

## 2. Input contract — how the list reaches the gate

The harness list is outside the repo by construction, so the gate cannot read it
directly. The SESSION must **export** it at close. Contract:

- **Env var `TASK_DURABILITY_TASK_LIST`** — absolute path to the exported task
  list file. Required.
- **File format** — one task per line, UTF-8. A line is:
  `<task text>` optionally followed by a status suffix `[<status>]`, where
  `<status>` ∈ {`pending`, `in_progress`, `completed`, `DROPPED — <reason>`}.
  Blank lines and lines beginning with `#` are ignored.
  - **OPEN** = status ∈ {`pending`, `in_progress`} **or** no status suffix.
  - **NOT OPEN** = status `completed`, or status `DROPPED — <reason>` (the drop IS
    the durable home — §4.3).
  - No other status value is recognized; an unrecognized suffix makes the task
    OPEN (fail-closed on ambiguity).
- **Test hooks** (used only by the fail-on-revert suite; never in production):
  `TASK_DURABILITY_BOARD_DIR` (default `fleet/board`), and the operator-action
  list path `TASK_DURABILITY_OPERATOR_ACTIONS` (default
  `fleet/state/OPERATOR-ACTIONS.md`).

The export is the **conversion path** the gate exists to demand
(`serial_justified`: never ship the check without it). Making the export itself a
RED condition (R1) is what forces every session to materialize its working set at
close instead of letting it evaporate.

---

## 3. Non-vacuity (GATE-CREATION-STANDARD S2)

`fleet/GATE-CREATION-STANDARD.md` S2: *the gate CANNOT pass on zero items, an empty
scan set, or an UNREACHABLE data source. Absence of evidence is a RED, never a
pass.* This gate satisfies S2 by construction:

- **Unreachable source** → R1 (no export file / unreadable) = RED.
- **Empty scan set** → an exported empty file is the SESSION'S OWN declaration
  "I have zero open tasks". That is a *reached* source with a real verdict, so it
  is GREEN — but the file must EXIST. A session that never exported anything
  cannot claim "nothing was open"; it gets R1.
- This is exactly the "worse shape" guard: the session that used the task tool zero
  times and delivered nothing can no longer close silently.

---

## 4. Durable-home resolution (R2 semantics)

For each OPEN task, the gate must find **at least one** of the following. Order of
evaluation is irrelevant; any hit resolves the task. No hit = R2 RED for that line.

### 4.1 Board ticket id

The task text contains a board ticket id that is the **stem of a live (non-parked)
file in `fleet/board/`**.

- Board file layout: `fleet/board/<ID>.md` (live) vs `fleet/board/<ID>.md.parked`
  (parked). **Parked tickets are NOT durable homes** — they are shelved, not
  active work.
- Matching: build the set of non-parked stems from `fleet/board/*.md` (strip
  `.md`, exclude `.parked`), then test whether the task text contains any stem as
  a word-boundary token. Example: task text `LAUNCHER-LEAKGUARD-NONFATAL (5 tabs
  killed)` → stem `LAUNCHER-LEAKGUARD-NONFATAL` exists as `fleet/board/LAUNCHER-LEAKGUARD-NONFATAL.md`
  → resolved.
- Do NOT derive ids by regex alone; match against the live stem SET. A token that
  looks like an id but has no board file is NOT a home (prevents gaming by
  free-text).

### 4.2 Live `pending.sh` operator action

The task text references a **currently open** operator action. `pending.sh`
(`fleet/pending.sh:22-27`) labels items `A`…`Z` then `#N`, persisted one-per-line
in `fleet/state/OPERATOR-ACTIONS.md` as `<LABEL>\t<text>`; `pending.sh done <label>`
retires a row.

- A task maps to an operator action iff **either**:
  - the task text contains a numeric label `#N` (N a positive integer) whose row is
    **present** in `OPERATOR-ACTIONS.md` at check time; **or**
  - the task text contains the full text of a row currently in
    `OPERATOR-ACTIONS.md` (label column alone is NOT sufficient for single-letter
    labels `A`–`Z` — a bare letter is not a durable reference; require label+text
    or a numeric `#N`).
- A RETIRED label (no live row) is NOT a home — the operator action no longer
  exists, so it cannot be where the work lives.

### 4.3 Explicitly dropped

The task line carries the literal marker `[DROPPED — <reason>]` (status suffix OR
inline). The drop IS the durable home: the session consciously closed the item and
recorded why. `<reason>` must be non-empty; a bare `[DROPPED]` with no reason is a
RED (a dropped task with no reason is an unmapped open task in disguise).

---

## 5. Wiring into `fleet/end-session.sh` (contract for the build ticket)

`fleet/end-session.sh` today checks work-loss in **GIT only** (handoff exists +
passes `handoff-check.sh`, branch-guard, clean tree, ahead-of-origin, second-repo
strand). It has no notion of an OPEN task without a home. Contract:

- **Phase 2, after `handoff-check` PASSES and BEFORE the commit / `SESSION CLOSED`
  print** (`fleet/end-session.sh:225-259`), invoke the assertion. On R1/R2 it must
  behave like every other refusal: print `end-session: REFUSING to close — ...`,
  return non-zero, commit NOTHING, do NOT print CLOSED.
- **FAIL LOUD (GATE-CREATION-STANDARD S5)**: non-zero exit; `set -uo pipefail`;
  the verdict lives in the exit code, not in log text. On R2, print **every**
  unmapped line as `  line <N>: <task text>` — naming each unmapped item is the
  whole point (silent pass = the false-green family of a registered-but-never-
  executing cron job).
- The assertion is registered where the umbrella's meta-check can see it (the
  SESSION-CLOSE-COMPLETENESS-GATE build wires it alongside B–E and its own
  fail-on-revert suite).
- It runs against the exported list **at close time**; it is not a background
  detector. (The umbrella's cadence-leg work is Assertion C, separate.)

---

## 6. Fail-on-revert proof (Done contract item 4)

The build ticket MUST ship a committed test proving BOTH directions (the umbrella
owns the test file; this spec fixes the assertions it must contain):

1. **RED on unmapped OPEN task.** Seed `TASK_DURABILITY_TASK_LIST` with a file
   containing one OPEN task with no board id, no live operator action, no
   `[DROPPED — reason]`. Assert the close REFUSES (non-zero) AND the task text is
   named in the output. **With the gate/assertion reverted (or the mapping check
   removed), the same close PASSES** — this is what pins the wiring.
2. **RED on no export.** Unset `TASK_DURABILITY_TASK_LIST` (and/or point at a
   missing file). Assert R1 RED. Reverting the R1 branch → the close passes.
3. **GREEN on full mapping.** All OPEN tasks mapped (one each via §4.1, §4.2,
   §4.3) → close proceeds.
4. **GREEN on empty export.** Exported file exists but contains no OPEN task
   (empty, or all `completed`/`DROPPED`) → close proceeds. Guards against the
   vacuous-pass regression in the other direction.
5. **Parked board id is NOT a home.** Task text matches a `.parked` stem → RED
   (unless another home resolves it). Proves the parked exclusion is real.
6. **Retired operator label is NOT a home.** Task references `#N` where the row was
   removed from `OPERATOR-ACTIONS.md` → RED.

Each assertion is hermetic (fixtures + the env hooks in §2); none touches the live
board or the live operator-action list.

---

## 7. Boundary & non-goals

- **Reverse direction NOT in scope**: a board ticket need not appear in the
  harness list (list = working set; board = record).
- The gate does NOT police whether the session *used* the task tool productively —
  it polices that whatever the session DID track has a durable home. Enforcing
  "you must create tasks" is the §0 rule + this gate's R1 (you must at least
  export).
- It does NOT check that the operator action is *answered* — `pending.sh`'s own
  preflight surfacing does that. It checks the action is the task's recorded home.
- GATE-CREATION-STANDARD cross-check: S1 red-proofed (fail-on-revert §6), S2
  non-vacuous (§3), S3 un-gamed (stems from live set, labels must be live),
  S5 fail-loud (§5), S6 deterministic (hermetic input set), S7 context-of-validity
  (this covers the close boundary only, not live DATA), S8 artifact-verified (the
  test reads the exported file, not the session's claim).

---

## 8. Sequencing

P0, depends on nothing, and must land before the next session accumulates its own
list (or the class repeats). Pairs with `FLEET-STATUS-BOARD` (makes the check
visible); this one closes the boundary where work stops being tracked at all.
The umbrella (`SESSION-CLOSE-COMPLETENESS-GATE`) depends on `SESSION-END-GATE-REPAIR`
and wires A–E together; Assertion A's contract is fixed HERE so the umbrella build
is mechanical.
