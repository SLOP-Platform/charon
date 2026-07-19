repo: charon-private
DONE 2026-06-27 — validated on charon-vm; gaps captured into UX-POLISH/etc.
tier: n/a
difficulty: 1  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: generalist
branch: n/a
depends_on:
owns:
prompt:
status: DONE (operator-manual step completed; see state/done/PREFLIGHT marker).
scope: OPERATOR MANUAL STEP (not a droid build, not code). Run `charon setup` interactively
  ONCE — the only non-auto first-run step — to surface any first-run gap (config scaffold, key
  prompts, gateway/doctor) BEFORE the dogfood. De-risks DOGFOOD; quick.
note: TYPE operator/out-of-tree (manual operator action). depends_on EMPTY — runnable NOW. GATE:
  none upstream; it is itself the PREFLIGHT gate for DOGFOOD (run it before the first dogfood so
  first-run gaps surface early, not mid-dogfood). No product code, no PR, no merge. This `.parked`
  file exists only to track the step on the manager's plan — there is nothing for a droid to
  claim. Literal command for the operator:
    *****
    charon setup
    *****

## NOTE — DONE (closed 2026-06-27)

**Operator-run, manual — COMPLETE.** Ran `charon setup` once on charon-vm this session; it
surfaced many first-run gaps, now captured/fixed (folded into UX-POLISH and related tickets).
Closed via `state/done/PREFLIGHT` marker (mirrors how every other DONE ticket is represented:
`board/<ID>.md` + `state/done/<ID>`). There was never a droid build here — no `owns:`, no
`prompt:`, no branch, no PR.

TYPE: **operator/out-of-tree** (a manual first-run check, run by the operator, not the fleet).

Activation: operator runs `charon setup` once and reports any gap. Feeds DOGFOOD.
