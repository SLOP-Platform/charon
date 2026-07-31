repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 1
branch: fix/worker-lifecycle-detect
owns: fleet/fleet-idle.sh, fleet/stop-worker.sh, fleet/spawn-worker.sh, fleet/tests/worker-lifecycle.test.sh
depends_on:
dep-kind:
serial_justified: |
  ONE process lifecycle contract: spawn -> detect -> stop. The three surfaces are the three
  verification points of the SAME guarantee ("the fleet can see and control its own workers"),
  and every one of them was found broken in the same way — a check structurally incapable of
  observing the thing it claimed to verify. Splitting them ships a fleet that can start a worker
  it cannot see, or see one it cannot stop, and the shared regression suite (worker-lifecycle.test.sh)
  cross-checks all three against one another: the spawn verifier's fixtures are the same stub
  surfaces the idle detector and stop verifier use. Landing them separately would mean three
  partial suites and no single run that proves the lifecycle end to end.
work_class_note: every fleet session depends on these three scripts being honest — fleet-idle says "safe to interrupt" while a worker is mid-turn, stop-worker reports a successful stop as FAILED, and spawn-worker silently drops its injected prompt on every 3-tab fan-out. Each defect is a verification path that is structurally incapable of observing the thing it claims to verify — the same class.
note: |
  LIVE-EVIDENCE (already proven by the manager, see fleet/state/agent-briefs/WORKER-LIFECYCLE-FIX.md):
    BUG 1: `fleet/fleet-idle.sh:9` — the grep `'[o]pencode --model'` REQUIRES
    `--model` to be ADJACENT to `opencode` in ps output. fleet/spawn-worker.sh
    execs `opencode --port N --model charon/X` so the two tokens are NOT
    adjacent. A worker ran on :47099 for 1h38m while fleet-idle printed
    `=== live opencode sessions === (none)` and exited 0 = "IDLE — safe to
    run interrupt-capable work." The one script whose entire job is "is it
    safe to interrupt?" answers YES while the fleet is working.

    BUG 2: `fleet/stop-worker.sh:24` — the verify branch is
    `code=$(curl -s -m 3 -o /dev/null -w "%{http_code}" "http://.../api/health" 2>/dev/null || echo 000)`
    On a refused connection, `curl -w '%{http_code}'` already prints `000` AND
    exits non-zero, so the `|| echo 000` appends a SECOND `000`, the captured
    string becomes `000000`, the `[ "$code" = "000" ]` test fails, and the
    script reports `FAILED to verify stop` and exits 1 — on a stop that fully
    succeeded. Observed live today stopping :47099.

    BUG 3a: `fleet/spawn-worker.sh` — the readiness gate fires on the FIRST
    poll where `health=ok AND established > 0`, observed at established=18 in
    a 3-tab fan-out (:47301/2/3). 18 is the TUI still mid-attach; a prompt
    injected in that window is silently dropped (the `/tui/*` endpoint returns
    `true` unconditionally). At established=36 the same inject landed a
    session. 36 was one observation on one machine — the fix is not a magic
    number, it is STABILITY of the connection count across consecutive 1s
    samples.

    BUG 3b: `fleet/spawn-worker.sh` — the start-verification compares a
    `grep -c '"id"'` COUNT before vs after submit. Two independent reasons
    this can never work: /api/session is PAGINATED (returned exactly 50 rows
    for the operator who hit this — a capped list cannot show growth), AND
    the opencode session store is GLOBAL and shared across every port (the
    same fan-out's three ports returned the identical session list, including
    sessions belonging to other workers and to a stray from two hours
    earlier). Replacement: snapshot ALL session IDs BEFORE submit, then
    poll AFTER for IDs not in the before-set AND with time.created >=
    submit_time. ID-set diff is not fooled by pagination; the timestamp
    filter is the only thing that tells MY submit apart from a coincident
    neighbour's.

  CONSEQUENCE: every fleet session today relies on three verification paths
  that are structurally incapable of observing what they claim to verify.
  The fix lands all three together because they share the same failure class
  and the test exercises all three in one hermetic suite.

accept: |
  (1) `fleet/fleet-idle.sh` matches BOTH spawn forms — `opencode --model X`
      AND `opencode --port N --model X` — and does NOT match `grep opencode`
      or `vim fleet/spawn-worker.sh`. Verified by FLEET_IDLE_PS-stubbed ps.
  (2) `fleet/stop-worker.sh` captures the http_code as EXACTLY the curl-printed
      string (no `|| echo 000` doubling). Refused port resolves to exactly
      `000`; the verify branch reports STOPPED with exit 0 only when pid is
      gone AND port refuses. A port answering 200 with pid alive reports
      FAILED and exits 1 (unverified stop must never pass).
  (3a) `fleet/spawn-worker.sh` readiness gate waits for STABILITY of the
       connection count across 3 consecutive 1s samples (the real
       discriminator — a TUI done attaching stops growing the count) above
       a sane minimum (10 — well above the headless-serve baseline of 3-5,
       well below any observed still-attaching plateau).
  (3b) `fleet/spawn-worker.sh` start-verification walks /api/session BEFORE
       submit, snapshots every session id, polls AFTER for ids not in that
       set AND with time.created >= submit_time. Detects a real start (g),
       detects a real non-start (h), is not fooled by a session created by a
       different worker/port whose time.created is < submit_time (i), and
       is not fooled by pagination — the ID-set diff sees the new id even
       when the visible list is capped at 50 (j). The OLD count-delta check
       is wrong on (i) AND (j); a revert to it makes (i)/(j) RED.
  (4) `fleet/tests/worker-lifecycle.test.sh` — hermetic (<5s), mktemp -d only,
      Python-stdlib HTTP stub for /api/session, stubbed ps/ss/kill (kill
      builtin disabled via BASH_ENV so the stub isn't shadowed). Assertions
      (a)–(j) each go RED when their named revert is applied, GREEN on restore.
      The exact CI_SUITES entry is in fleet/state/handoff/WORKER-LIFECYCLE-CI-SUITE-LINE.txt
      so the rig's CI gate can pick it up once the OTHER owner of rig-ci-scope.sh
      (per the brief) adds it.
  (5) `fleet/checks/rig-ci-scope.sh` is NOT touched (owned by another ticket
      per the brief). The CI_SUITES line is delivered via the handoff file.

scope: |
  Three lifecycle verifications in the rig's fleet-spawn/stop/idle scripts.
  Blast radius: every fleet session. P0 because each defect is a verification
  that passes while the thing it claims to verify has failed — the same class
  that just silently dropped three prompts in production. Build-rig only (no
  product change). Adversarial review REQUIRED before land (data-safety on
  the start-verification side: a verifier that incorrectly counts another
  worker's session as this worker's start could enable stale-claim starvation
  patterns).
ds: Now — no owns collision (fleet-idle.sh, stop-worker.sh, and spawn-worker.sh
  are unowned by any other live ticket; fleet/checks/rig-ci-scope.sh is owned
  by two other tickets per the brief and is therefore NOT touched here — the
  CI_SUITES line is delivered via handoff). Blocks safe max-parallel fan-out
  (the manager cannot trust fleet-idle.sh until this lands) and any future
  automation gating on stop-worker.sh. Land before further fan-out.