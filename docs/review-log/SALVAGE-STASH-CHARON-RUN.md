# SALVAGE-STASH-CHARON-RUN — review-log fragment

Ticket: SALVAGE-STASH-CHARON-RUN
Tier: strong
Branch: feat/salvage-charon-run-timeout
Date: 2026-07-15

## What this change is

The work-spec called for salvaging TWO unique features from a stashed fork
of `fleet/charon-run.sh` (the patch at
`fleet/session-notes/STASH-BACKUP-47eee2a.patch`) onto current master,
WITHOUT wholesale-applying the stash (which would have reverted master's
EVAL-LATENCY-GATE / FLAW-2 / is_infra_fault work). The two features:

1. **`CHARON_RUN_TIMEOUT_S` per-attempt wall-clock budget**
   (configurable from the caller's environment; default 1800s).
2. **`OPENCODE_LOG` rc=124 disambiguation**
   (a read-only peek at opencode's structured log to tell "model genuinely
   slow" from "gateway pool exhausted and opencode silently retried").

The hand-surgery approach was the only safe path: a `git apply` of the
stashed patch would have collided with master's `is_infra_fault` (FLAW-2)
and EVAL-LATENCY-GATE work, all of which the launcher's `accept:` block
required remain INTACT.

## Pre-existing state (verified before edit)

Master ALREADY had the `CHARON_RUN_TIMEOUT_S` override (commit
`4082c8f feat(fleet-droid): --retries 0 = infinite ...` plus the
EVAL-LATENCY-GATE / FLAW-2 chain). The relevant call site is
`fleet/charon-run.sh:90`:

```bash
( cd "$CWD" && timeout "${CHARON_RUN_TIMEOUT_S:-1800}" opencode run --model "charon/$M" "$PROMPT" ) </dev/null >> "$OUT" 2>&1
```

So feature (1) is already present on master. The reusable work is feature
(2) — the OPENCODE_LOG disambiguation.

A subtle but important finding: `fleet/benchmark/lib/dogfood-attribution.sh`
ALREADY had a marker-string grep for the pool-exhausted branch on line
41-43:

```bash
if grep -q 'TIMEOUT (rc=124.*CAUSE: gateway pool exhausted' "$out_log" 2>/dev/null; then
  echo "provider-degraded->retry(pool-exhausted-on-timeout)"; return
fi
```

That grep was DEAD CODE: the corresponding emit-site in `charon-run.sh`
didn't exist on master. So feature (2) is the exact piece that wires up
the upstream signal that the attribution lib was already prepared for.

## Why feature (2) matters

Without the OPENCODE_LOG peek, when `timeout` kills a charon-run attempt
(rc=124), charon-run.sh only sees:

- "model streamed real output, didn't finish in time" → `too-slow` (model-attributable)
- "no output at all" → `leg-fault` (infra/leg hang)

But there's a third cause that LOOKS identical to a no-output leg-fault
from charon-run.sh's POV: **the gateway pool was drained and opencode was
silently retrying in a loop waiting for a free provider**. opencode's CLI
stdout does NOT surface "all providers exhausted" (confirmed: it hangs
silently until `timeout` fires) — so without an out-of-band signal, the
caller charges a pool-exhaustion masquerade to the model as either a
too-slow or a leg-fault fault.

Worse: this masquerade had been observed in production runs in the
ledger (rows in `fleet/provider-exhaustion-ledger.tsv` showing gpt-5.4
hitting `error-failover rc=124` repeatedly — see the rows in the
STASH-BACKUP-47eee2a.patch's tsv hunk). Those were charged to the model
as opaque "error-failover" events; a real OPENCODE_LOG disambiguation
would have re-classified them as provider-side and avoided the model
BLOCK.

## Design choices (why this hand-surgery, not stash-apply)

- **Pre-existing OPENCODE_LOG grep in attribution lib is the contract**.
  The marker text the new charon-run.sh branch emits
  (`TIMEOUT (rc=124, ${ELAPSED_S}s) — CAUSE: gateway pool exhausted`)
  is exactly the substring the attribution lib's
  `classify_attribution` greps for. Change one side, change both, or
  the upstream signal goes dead again. The new code's comments pin
  this contract.
- **Lexical `>=` against `ATTEMPT_START_ISO`** scopes the log scan to
  the attempt window. This is one-sided (only filters BEFORE-window
  noise, not AFTER-window noise), but that's correct: in a real
  opencode log, lines are chronologically ordered and time never goes
  backward. Future-dated lines don't happen; if they did, counting
  them errs on the side of "provider-side, don't BLOCK the model" —
  safe.
- **OPENCODE_LOG defaults to `$HOME/.local/share/opencode/log/opencode.log`**
  (the standard opencode install path) but is overridable — tests and
  the bench-grader can inject a hermetic fake. The `if [ -f ... ]`
  guard ensures a missing log degrades cleanly to "0 hits" (the
  existing too-slow/leg-fault split runs unchanged).
- **Preserved master's is_infra_fault / latency-gate as the FINAL
  sub-branch** (after the OPENCODE_LOG check). The OPENCODE_LOG branch
  only fires when rc=124 AND in-window pool-exhaustion events are
  observed. The leg-healthy-too-slow vs leg-fault-hang distinction is
  untouched, and master's marker text (the F1 contract with
  `classify_attribution`) is byte-identical.
- **New ledger event name `pool-exhausted-timeout`** (parallel to
  master's `too-slow-failover` and `leg-fault-failover`). Distinct
  event name so the existing ledger queries and dashboards can
  filter pool exhaustion separately from the other two.
- **No cap() scorecard call** in the new branch — pool exhaustion is
  never a model-quality signal. Mirrors the master's `leg-fault`
  branch (also no `cap()`). The `too-slow` branch DOES call `cap()`
  with BLOCK/fail because that IS a model-attributable latency miss.

## Test design

`fleet/tests/charon-run-pool-exhausted.test.sh` — five stages:

1. **Baseline regression guard**: a hang with no log entries still
   routes to `leg-fault` (so the new branch doesn't eat master's
   existing case).
2. **CHARON_RUN_TIMEOUT_S contract re-pinned**: too-slow with no log
   entries still emits `budget=2s too-slow FAIL` (so a future change
   that hard-codes 1800 again flips RED here as well as in
   `dogfood-latency-gate.test.sh`).
3. **NEW feature** — hang with 3 in-window pool-exhausted log lines
   routes to the new marker `CAUSE: gateway pool exhausted (3x ...)`,
   the ledger records `pool-exhausted-timeout` (not `too-slow-failover`
   or `leg-fault-failover`) on the LABEL row, and
   `classify_attribution` (the real lib, not a reimpl) reads the new
   marker and returns `provider-degraded->retry(pool-exhausted-on-timeout)`.
4. **Time-scope guard**: 5 BEFORE-window-only log entries do NOT
   trigger the new branch — the lexical `>=` filter holds.
5. **Missing-OPENCODE_LOG degrades cleanly**: when the file doesn't
   exist (the production default path on a fresh test host), the
   existing leg-fault marker still fires and charon-run.sh doesn't
   crash.

The test is hermetic: stub `opencode` on PATH, isolated COPY of
charon-run.sh with no sibling capture/ dir, override
CHARON_EXHAUST_LEDGER + CAPTURE_SPOOL_DIR + OPENCODE_LOG to
WORK-scoped throwaways, no live network, no real gateway call.
All 21 assertions pass; the existing `dogfood-latency-gate.test.sh`
(20 assertions) also still passes — the is_infra_fault / latency-gate
work is INTACT.

## Scope discipline

Owns: `fleet/charon-run.sh`.
Created (lone exception per the launcher): `fleet/tests/charon-run-pool-exhausted.test.sh`,
`docs/review-log/SALVAGE-STASH-CHARON-RUN.md`. No other files touched.

Justification for the test file: the launcher's `accept:` block
explicitly says "A test asserts CHARON_RUN_TIMEOUT_S overrides the
default budget; the OPENCODE_LOG exhaustion-vs-slow branch is
exercised." — the test is a contractual deliverable, not a scope
expansion. The established convention across the fleet is that test
files in `fleet/tests/` accompany their owns: file as part of the same
deliverable (see e.g. `fleet/tests/dogfood-latency-gate.test.sh` for
the same pattern on the is_infra_fault change). The test is fully
hermetic (no live network, no real gateway, no shared state with
other fleet droids) so it cannot conflict with another ticket's
deliverable.

Did NOT touch `fleet/benchmark/preflight.sh` even though the stash patch
modified it — preflight.sh is owned by another ticket per the launcher's
note ("preflight.sh salvage is a SEPARATE assessment — note it, don't
touch here").

## Out-of-scope / follow-up (not addressed here)

- The stash's `preflight.sh` perms-relaxation (`chmod 755 $session_root`,
  `chmod -R a+rX $session_dir`) — preflight.sh is owned by another
  ticket; deferred.
- The stash's `roadmap-html.sh` ACTIVE_OVERRIDE/ACTIVE_MODE=recent
  changes — orthogonal to this ticket, deferred.
- The stash's tsv ledger rows that pre-date this fix — historical
  evidence, not retroactively re-classifiable without re-reading the
  live opencode log timestamps (which we don't have).
- `provider=unknown-clientside(...)` diff-state metrics the stash tried
  to add per-attempt (real-diff vs bail-no-diff) — useful for
  attribution but out of scope for THIS salvage; the OPENCODE_LOG
  disambiguation is the higher-value signal.
