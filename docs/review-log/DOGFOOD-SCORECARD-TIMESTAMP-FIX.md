# DOGFOOD-SCORECARD-TIMESTAMP-FIX — review note

**Decision:** Append `$$` (PID) to the generated output filename to make it
collision-proof within the same second. Two runs within the same second now
produce distinct filenames because each invocation runs in its own process with
a unique PID.

**Alternatives considered:**
- Monotonic counter suffix: more complex, requires state, same outcome.
- Refuse-and-error on existing file: would prevent data loss but would also
  reject the second run entirely, breaking batch workflows.
- Content hash: overkill for a script-generator whose content is deterministic
  given inputs; PID is sufficient and trivially correct.

**Defense in depth:** A `[ ! -f "$OUT" ]` guard is still present — if somehow
the same PID + same second re-occurs (impossible in normal operation), the tool
errors rather than overwriting.
