# ADR-0009 — L3 unattended autonomy: the escalation gate

Status: **Proposed** (2026-06-26). Refines ADR-0001 §6 / ADR-0003 §7 (autonomy
ladder) and ADR-0002 §2.3 / INV-B4 (Mode-B container is the real boundary). Folds
in the Tier-4 reconciliation (PLAN-tier4 §6, REVIEW-LOG 2026-06-24) that gated L2+
behind the container. Reconciles a 3-lens adversarial review of this ticket (T7) —
see REVIEW-LOG 2026-06-26.

## Context

The autonomy ladder (L0 propose · L1 apply-reversible · L2 apply-with-consensus ·
L3 full-auto-within-fence) was already implemented as a per-op *predicate*
(`Fence.authorize`) plus a *container* check (`Fence.assert_environment`). The
container check refuses L2+ outside the Mode-B image unless the operator sets a
loud opt-out, `CHARON_ALLOW_UNCONTAINED_AUTONOMY=1`.

That left one latent privilege-escalation hole, which this ADR closes:

- `assert_environment` treats **L2 and L3 identically** — the *same* single
  `CHARON_ALLOW_UNCONTAINED_AUTONOMY=1` flag that an operator sets to test
  apply-with-consensus uncontained *also* silently authorizes **L3**: full-auto,
  **consensus gate removed**, applied unattended. One env var, set for the lower
  rung, grants the highest-blast-radius rung. There is no *per-rung* escalation
  gate — reaching the top of the ladder is not separately, explicitly authorized.

L3 is materially different from L2: at L2 an automated reviewer is still consulted
before `advance_lkg` (a residual, fail-closed check); at L3 that gate is removed
and work is applied with no in-loop check at all (PLAN-tier4 §2). Its precondition
must therefore be **strictly stronger** than L2's, not equal to it.

## Decisions

**D-ESC-1 — Per-rung, default-deny escalation gate.** Introduce
`AutonomyPolicy` (a small frozen dataclass in the already-owned `fence.py`) that
resolves a *requested* autonomy level against the environment with **per-rung**
preconditions, each default-deny:

- **L0** (propose-only): always grantable.
- **L1** (apply-reversible, `lkg` rollback): always grantable — fully reversible,
  local to the worktree, no consensus removed.
- **L2** (apply-with-consensus): grantable iff Mode-B container
  (`CHARON_CONTAINER_VERIFIED=1`) **or** the loud uncontained override
  (`CHARON_ALLOW_UNCONTAINED_AUTONOMY=1`). Unchanged from Tier 4.
- **L3** (full-auto, unattended, consensus removed): grantable iff the **L2**
  precondition holds **and** a *separate, distinct* explicit opt-in
  `CHARON_ALLOW_UNATTENDED=1` is set. The override that unlocks L2 testing does
  **not** reach L3.

**D-ESC-2 — Monotone, non-skipping ladder.** A rung is grantable only if *every*
lower rung's precondition also holds. The environment **ceiling** is the highest
contiguous grantable rung; the gate can never grant a rung over a forbidden one.
(With L3's precondition a superset of L2's this holds naturally, but it is encoded
explicitly so a future rung cannot bypass the climb.)

**D-ESC-3 — Fail-loud, never silently clamp.** The enforcement path
(`Fence.assert_environment`, already called once by `coordinator.run`) **raises
`FenceDenied`** when the requested level exceeds the ceiling — including
L3-requested-without-the-unattended-token. It does **not** silently downgrade to a
lower level, because an operator who believes they are running unattended L3 and is
silently dropped to L1 has a worse footgun than a loud refusal. A *non-raising*
`AutonomyPolicy.resolve()` / `.ceiling()` is exposed for inspection/diagnostics
(e.g. `doctor`), separate from enforcement.

**D-ESC-4 — Honesty register (carried, unchanged).** L3 is "no *consensus* gate,"
not "no fence." At L3 the escape scan, the scrubbed spawn env, and the
always-denied destructive ops (`DELETE`/`DEPLOY`) all still bind. The Mode-B
container remains the only real boundary for a *live* agent (INV-B4); the
escalation gate is a **policy** that prevents *accidental* escalation, not OS-level
isolation. It does not, by itself, stop a determined operator who sets all tokens.

**D-ESC-5 — Tokens are not reachable by the fenced agent.** `Fence.scrubbed_env`
allow-lists only `PATH/TERM/LANG/LC_ALL/TZ` (plus the HOME/git/`CHARON_FENCED`
overrides). The escalation tokens (`CHARON_CONTAINER_VERIFIED`,
`CHARON_ALLOW_UNCONTAINED_AUTONOMY`, `CHARON_ALLOW_UNATTENDED`) are therefore
**never** propagated into a spawned backend — a fenced agent cannot read them and
cannot forge a higher autonomy for the parent. Asserted by test.

## Consequences

- Closes the one-flag-grants-two-rungs hole: L3 now requires its own explicit,
  loud acknowledgement on top of the container/override.
- No new module and no new owned source file: the gate is one frozen dataclass +
  a delegating change to `assert_environment` inside `fence.py`, enforced at the
  single point `coordinator.run` already calls. `api.py` (default `autonomy="L0"`)
  and `decompose.py` (L2 path) are untouched and unaffected.
- Residual, disclosed (D-ESC-4): the gate is env-var based, so anything that can
  set the *orchestrator's* env can self-escalate. The structural boundary stays
  the container; the scrubbed env (D-ESC-5) keeps the tokens out of agent reach.
