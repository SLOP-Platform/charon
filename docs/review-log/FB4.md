## 2026-06-27 — FB4 (fragility audit THEME 7) — engine concurrency/fencing fixes

**Change under review:** surgical correctness fixes to MERGED `engine/claim.py` (E1) and
`engine/scheduler.py` (E2). These undermined the "never two live holders" guarantee the
fence exists for (ADR-0010 D2; DECISIONS D008/D009; DTC Lens-4). No redesign, no second lock
subsystem, no heartbeat/remote-lease (D009 honored). Each fix has a PROVEN-RED test.

- **[#1 Reclaim two-holder race — CAS by atomic rename]** The old reclaim did `os.unlink`
  then `_create_exclusive` with no lock and no re-validation between the staleness read and
  the unlink: two reclaimers reading the same stale record both became holders (R2's unlink
  clobbered R1's freshly-created claim). Fixed with a lock-free CAS: **capture** the stale
  file by atomically renaming it to a private temp (`os.replace(path → captured)`) — the
  rename is the test-and-set, so exactly one racer can move `path` away; the rest get
  `FileNotFoundError` → `ClaimContended`. After capture, **re-validate** the captured record
  is the *same* stale one we read and still stale (`recheck != existing or _is_live`); if a
  fresh holder slipped in, give it back without clobbering a newer holder (`os.link` is
  atomic and fails if `path` was retaken) and lose. Chose CAS over a per-unit lockfile
  because a crash-leaked lockfile would need its own TTL/PID liveness — i.e. a second lock
  subsystem, which D009 forbids. CAS is self-healing and reuses the existing O_EXCL ethos.
  Proven-red test deterministically interleaves two reclaimers via a `_read_claim` seam
  (R2 reads stale, blocks; R1 reclaims to epoch 2; R2 resumes) — old code yields TWO holders
  (epoch 2 + epoch 3); fixed code: R2 loses.

- **[#2 Disposition.RETRY was dead — ledger create-or-load + per-drain attempt scope]** The
  runner called `Ledger.create`, which raises `LedgerCorruption` when `ledger.json` already
  exists, so every RETRY re-failed at ledger creation and looped to the attempt cap; and
  `self._attempts` never reset across `drain()` so a once-failed unit could never be retried
  in a later drain. Fixed: `CoordinatorRunner` now create-OR-loads (resume the durable
  ledger on a retry — D2 durable resume), and `drain()` resets `self._attempts` at entry (the
  cap bounds re-launch *within* one drain only). Proven-red: a unit that EXHAUSTs once then
  SATISFIES lands DONE (`["exhausted","complete"]`).

- **[#3 Capacity slot leak + non-fresh worktree]** The claim path caught only
  `ClaimContended`; any other exception (worktree factory mkdir/init, a stale reclaim, a
  board error) propagated WITHOUT releasing the capacity slot acquired just before, tearing
  down the whole drain. Fixed `_launch_round` with an explicit `launched_unit` flag +
  `finally` that releases the slot on every non-launch path; a non-`ClaimContended` failure
  is also *counted as an attempt* so a persistent error cannot spin the drain (contention is
  still NOT counted — it should retry freely). The default worktree factory is now unique
  **per attempt** (`…/sandbox/<id>/a<attempt>/repo`) so a retry/stale-reclaim lands on a
  FRESH worktree (claim refuses reclaim onto the in-flight one). Proven-red: a worktree
  factory that raises once releases the single opus slot so the sibling still runs and the
  unit recovers on its second attempt (old code raised out of the entire drain).

- **[#4 Stale-epoch release tore down the drain — log-and-skip]** In `_settle`, a
  `StaleReclaim` from `release_claim` propagated out of the `for fut in done` loop, aborting
  settlement of in-flight siblings (left CLAIMED) — the exact double-exec the fence detects
  crashed instead of being recorded. Fixed: catch `StaleReclaim`, mark the unit
  `Disposition.SUPERSEDED` (new enum member, produced only here — not by `default_classify`),
  do NOT advance the board (the fresh holder owns it now; it stays CLAIMED), release the slot,
  and continue settling siblings. Proven-red: one unit's mid-flight reclaim does not abort the
  sibling's settlement; sibling → DONE, superseded unit left CLAIMED.

**Known residual (noted, out of scope):** on a #2 retry the loaded ledger pins
`target_repo` to the *first* attempt's worktree, so `coordinator.run` resumes that worktree
while #3's factory hands a fresh one for the *claim*. This is correct durable-resume
semantics (resume from lkg) and the claim/ledger worktree divergence is benign (the claim's
fresh-worktree rule is a fencing constraint, not the execution path), but a future ticket may
want to reconcile claim.worktree with ledger.target_repo. See [[charon-own-work-engine]].
