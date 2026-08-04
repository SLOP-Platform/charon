repo: charon
tier: strong
priority: 1
difficulty: 2
work_class: money-path
branch: fix/park-cooldown-split
owns: src/charon/litellm_plane/park_cooldown.py, tests/test_gw_bridge4_park_cooldown.py
depends_on:
dep-kind:
serial_justified: |
  One behaviour change and the red-proof that inverts the two existing tests which currently CEMENT
  the behaviour being removed. Splitting them would land either a change whose green tests
  contradict it, or tests that fail against unchanged code — the exact failure D-012 already warned
  about when the same shape came up in forwarder.py.
work_class_note: money-path — it governs whether a PARKED provider can be dispatched to. Parking
  exists to stop spend; a guard that restores parked legs undoes it.
note: |
  ⛔ OPERATOR-APPROVED 2026-08-04 — see D-018 in fleet/state/DECISIONS.md. This DELIBERATELY narrows
  a previously operator-declared "non-negotiable" invariant (the sole-leg guard). It is on the
  record as a decision, not a session's unilateral override.

  ## THE DEFECT
  `src/charon/litellm_plane/park_cooldown.py:146-192`:
    - `park_cooldown_filter_chain` merges Charon PARK state and litellm Router COOLDOWN into ONE
      exclusion set (`excluded_provider_ids`).
    - `sole_leg_guard(live, original)` then returns `list(original)` whenever `live` is empty —
      restoring the FULL chain, PARKED LEGS INCLUDED.
  That is precisely the behaviour D-012 outlawed in `forwarder.py`, reimplemented in the litellm
  plane. **Zero `src/` callers today (verified 2026-08-04) — no live leak. This is pre-emptive, and
  the reason to do it now is that adopting the litellm plane later would silently reintroduce the
  money leak D-012 just closed.**

  ## WHY THE MERGE IS WRONG — two different kinds of exclusion
  | | PARK | COOLDOWN |
  |---|---|---|
  | cause | operator/config decision | transient upstream failure |
  | cost of retrying anyway | **real money** | free |
  | correct never-strand behaviour | **fail with a 503** | retry the cooled leg |
  The never-strand guard is CORRECT for cooldown and is a money leak for park. Merging them forces
  one answer onto two different questions.

  ## REQUIRED BEHAVIOUR (D-018)
  1. Cooldown KEEPS the sole-leg guard: a chain excluded only by cooldown is still restored, so a
     transient upstream blip never strands a request.
  2. Park does NOT: a chain whose remaining exclusions are all PARK returns EMPTY, and the caller
     answers with the D-012 503 — same shape, same `no_provider_reason: "all_legs_parked"`
     discriminator, so the two planes cannot disagree.
  3. Mixed case must be explicit and tested: some legs parked, some cooled, none live. Park is the
     stronger signal — do not restore parked legs to satisfy a cooldown-shaped guard. State the
     chosen rule in the docstring; an undocumented precedence here is how this drifts back.
  4. `count_viable_legs` must stay consistent with the new filter, or callers will disagree with the
     dispatcher about whether a pool is servable.

  ⛔ **TWO EXISTING TESTS CEMENT THE OLD BEHAVIOUR AND MUST BE INVERTED IN THE SAME CHANGE:**
  `tests/test_gw_bridge4_park_cooldown.py::test_sole_leg_guard_keeps_last_leg` (parks the ONLY leg
  and asserts restoration) and `test_sole_leg_guard_multi_model`. Rename them to say what they now
  assert. A good test locking in a bad decision is exactly why D-012 carries this warning.

  ACCEPTANCE: (a) cooled-only sole leg IS restored — red-proofed; (b) parked-only sole leg is NOT
  restored and yields the D-012 503 shape — red-proofed; (c) the mixed park+cooldown rule is
  documented and tested; (d) `count_viable_legs` agrees with the filter; (e) each assertion has an
  OBSERVED red-proof (revert the change, watch it fail), not an asserted one.
