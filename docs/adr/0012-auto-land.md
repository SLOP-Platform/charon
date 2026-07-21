# ADR-0012 — Opt-in, batch-atomic auto-land

> Post-MVP per ADR-0017 (fleet orchestration deferred; gateway MVP first).

> **NOTE 2026-07-21 (ADOPT-FIRST directive):** this ADR's "privileged core stays
> stdlib-only" clause is superseded — maintained runtime dependencies are allowed, no ADR
> required (adopt-first; hand-rolling last-resort). See ADR-0005 / ADR-0019 notes. The
> anti-dilution rule that the gateway request path stays untouched is unaffected.

Status: **Accepted** (2026-06-26). Builds on ADR-0007 D4/D5/D6 (propose-default land gate;
`land.py`), ADR-0010 D4 (scanner matrix; advisory-until-measured), ADR-0009 (sandbox/isolation),
ADR-0003 (default-deny / L0-propose). Honors ADR-0005 R3 / ADR-0007 D11 (anti-dilution: the
gateway request path and install footprint are untouched).

> **This is the highest-blast-radius feature in Charon.** It merges agent-produced code with
> **no human at the merge**. Parallelism multiplies a single ticket injection into N landings.
> Every safety mechanism below is REQUIRED, not optional, and the whole path is **off unless
> explicitly enabled**. Default remains propose (open a PR; a human merges).

## Context

ADR-0007 D4 made landing **propose-default** and D5 specified that auto-land, *when opted in*,
must be **batch-atomic + allowlisted + fail-closed**. D5 was deliberately not built then
(deferred behind the D10 tripwires; D006 records the deferral). ADR-0010 kept auto-land on the
**trust-extending** side of the line: gated, review-owned, built only behind an explicit
operator opt-in. The operator has now un-gated D5 for construction (D016), so this ADR builds
the path D5 designed — **without changing the propose-default for anyone who does not turn it
on.**

The land gate (`land_unit`) is an **integrity check, not an adversary model**: it catches
*broken* or *secret-leaking* code, not *clean, in-scope, test-passing, hostile* code. The
ticket is therefore the primary attack surface. Auto-land cannot make the gate an adversary
model; it can only make the gate **fail closed in every ambiguous case** and shrink the
attack surface to a declared allowlist, so the residual trust is small, explicit, and
operator-granted.

## Decisions

**D1 — Opt-in master switch, default OFF (never the default).** Auto-land runs only when the
engine-owned config says `enabled`. With it off, the batch entry point returns a HOLD
(propose) verdict and performs **no git mutation**. The switch and the allowlist are read from
**outside the worktree** (engine config in `config_dir()` / `CHARON_AUTOLAND`), so a unit can
never enable its own auto-land or widen its own allowlist by editing a repo file.

**D2 — Batch-atomic: one decomposition lands as ONE all-or-nothing unit.** A batch is gated
per-unit first; if **any** unit holds, the batch lands **NOTHING**. If all units propose, their
tips are merged onto a **throwaway integration branch in a disposable worktree** (never the live
checkout), the gate runs **once on the integrated tip**, and the base branch ref is advanced in
a **single compare-and-swap `update-ref`** only if green — else the integration is discarded.
Per-unit green ≠ integrated green; there is no orphaned half-land; the operation is idempotent.

**D3 — Path-allowlist: refuse any write outside the declared, engine-owned allowlist.** A
changed file must be both in the unit's declared `owned_paths` **and** on the auto-land
allowlist to land. Anything else HOLDS. An empty allowlist lands nothing (fail-closed).

**D4 — Sensitive-path human-hold ALWAYS, even on green.** Every path the gate / git / CI /
tooling itself executes or trusts (`conftest.py`/`tests/`, `.git/hooks`, `.github/`, `.claude/`,
build hooks, dependency manifests, install/setup scripts, …) forces a human hold even when the
unit is otherwise green — the diff-scope + acceptance gate cannot model "in-scope but hostile",
and these paths execute *inside* the gate. The config may extend the sensitive set; it may never
shrink it.

**D5 — Acceptance + tests run in a sandbox; worker-authored test/conftest never auto-lands.**
The unit's executable acceptance checks and test command run in the disposable
integration worktree (D013 sandbox posture applies), not the live tree. Because `tests/` and
`conftest.py` are sensitive (D4), worker-authored test code is held for human review rather than
executed-then-auto-landed.

**D6 — Scanners REQUIRED / fail-closed when auto-land is on (flip D007).** In propose-mode the
scanner matrix (ADR-0010 D4) is advisory: a finding, a missing tool, or a timeout never blocks.
Under auto-land the posture flips: a scanner **finding HOLDS**, and an eligible-but
**unavailable/timeout/errored** scanner **fails closed** (HOLD) — a check that cannot run must
never read as green. gitleaks is likewise `expected` (missing → HOLD) and any leak HOLDS.

**D7 — Fail-closed everywhere.** Any missing-but-expected check, any base-ref mismatch across the
batch, any git ambiguity, any unreadable diff → HOLD (propose), never auto-merge. The default of
every branch in the decision tree is HOLD.

## Consequences

- The propose-default path (`land_unit` with its existing defaults) is byte-for-byte unchanged;
  auto-land is additive and reached only through the new batch entry point with `enabled=True`.
- Residual trust = "clean, in-allowlist, non-sensitive, scanner-clean, test-passing code from a
  trusted ticket origin." For public installs or untrusted ticket origins, leave auto-land OFF
  (propose-only remains the only safe default — ADR-0007 D4).
- The privileged core stays stdlib-only: git and the scanners are invoked as external
  subprocesses, never imported. No new install footprint; the gateway request path is untouched.

See `docs/review-log/E8.md` for the 3-lens adversarial reconciliation
(privilege-escalation · injection/provenance · fail-open) that gated this build.
