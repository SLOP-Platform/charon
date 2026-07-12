tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/a1-land-gate
depends_on:
owns: /home/stack/charon-private/fleet/land.sh, /home/stack/charon-private/fleet/land-push.sh, /home/stack/charon-private/fleet/state/BRANCH-PROTECTION-NOTE.md
accept: |
  land-push runs NO gate today → a CI-red merge shipped this session. Add a REFUSE-ON-RED gate to the land path.
  DO:
  - In land.sh AND land-push.sh, before the merge/push, run `ruff check` + `mypy` + the repo gate (`python3 -m charon.cli gate`
    or the exact gate the CI required-check runs) against the branch's tree; ANY non-zero → ABORT the land with a clear
    message naming the failing check, and do NOT merge/push. Green → proceed as today.
  - Make it hard to bypass silently: the gate is the default path; any `--force`/skip must be explicit + logged.
  - Write fleet/state/BRANCH-PROTECTION-NOTE.md: the exact GitHub branch-protection required-check name + settings to
    turn on for SLOP-Platform/charon (belt-and-braces server-side enforcement), as an operator action item (this is a
    repo-setting the droid CANNOT apply itself — document it, don't fake it).
  FAIL-ON-REVERT: point land.sh at a branch with a deliberate ruff/mypy/gate failure → land ABORTS (non-zero, no merge);
  fix the failure → land proceeds. Revert the gate wiring → the red branch lands (proving the gate bites). Add a rig
  self-test under fleet/tests/ that drives both cases.
  GREEN-IS-NOT-PROOF: land.sh exiting 0 on a clean branch does NOT prove the gate runs — the self-test MUST exercise the
  RED branch and assert land refuses. A land.sh that only ever sees green is indistinguishable from no gate at all.
scope: |
  GAP-REGISTER A1 (greenlit, was un-ticketed). Mechanizes the red-merge-prevention class permanently; compounds across
  every future merge. Source: QUICKWINS-LEVERAGE.md #3. NOTE: separate from A2 (deny-list) which is operator-gated and
  is NOT a droid ticket. [[session-guardrails-two-tier]] [[never-ignore-preexisting-issues]]
ds: FLEET (unticketed → now ticketed). depends_on EMPTY — launch NOW. Owns land.sh + land-push.sh + a new note doc; no
  other live ticket owns the land scripts → zero owns-collision. Concurrency-safe with the whole wave.
