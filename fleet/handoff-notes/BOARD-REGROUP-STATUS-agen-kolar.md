# BOARD REGROUP STATUS — halted mid-pass (agen-kolar, 2026-07-24)

Handoff note. Nothing here is committed — the manager batches board commits.
`bash fleet/validate_board.sh` = **rc 1, ONE red, NOT from this pass** (see §5).

## 1. Two new tickets (task A — COMPLETE)

| ticket | priority | why that band |
| --- | --- | --- |
| `HANDOFF-GOTCHA-VERIFIABLE` | 1 | attached to the live handoff-accuracy CG, code already BUILT+STAGED in `/home/stack/charon-private-wt/HANDOFF-GOTCHA`; one commit lands it. Not P:0 — it does not gate the landing queue. |
| `RIG-REDS-DISPOSITION` | 0 | the KEYSTONE: `land.sh` runs the full gate and refuses on red, so 10 standing reds block EVERY rig land and ~21 built-but-unmerged branches. Serial predecessor of every rig merge. |

Both: `repo: charon-private`, tier/difficulty/work_class set, D&S section, fail-on-revert +
non-vacuous acceptance, ROADMAP rows (Fleet / `Wave J — handoff & doctrine` and Fleet / `Rig fixes`).

Sequencing added: `SESSION-END-PUSH-GATE` now `depends_on: HANDOFF-GOTCHA-VERIFIABLE` +`real-dep:` —
the staged branch adds 3 lines to `fleet/end-session.sh`'s generated handoff FIXTURE (so it satisfies
the now non-vacuous `[claims]` gate) while SESSION-END-PUSH-GATE rewrites that file's close-refusal
logic. Different functions, so they compose in this order and clobber in the other. The dep went on
the NOT-STARTED ticket, never on the built one.

Known-open sub-finding recorded on the ticket (reported, not fixed): `handoff-mechanize` b2/c1 fail
on `origin/master` too — the `[sections]` gotchas needle `GOTCHA|avoid|DENIED` also matches text
OUTSIDE the gotchas section, so a stripped section goes undetected. Needs its own ticket.

## 2. Un-merge / regroup (task B — PARTIAL, halted on budget)

The correction being applied: **bundle = group by lens/wave at one priority so several agents work
it in parallel. It never meant fuse tickets into one serial branch.**

### RESTORED as separate tickets (6 of 8)
Recovered verbatim from `git show HEAD:` then improvements re-applied:
`DISCOVERY-NORMALIZE`, `DISCOVERY-DIFF`, `DISCOVERY-QUEUE`, `DISCOVERY-APPROVAL-WIRE`,
`DISCOVERY-CADENCE`, `DONE-SH-INTEGRITY-FIX`.
`fleet/board/DISCOVERY-PIPELINE.md` DELETED (it was untracked — a pure bundle artifact).

### RECONSTRUCTED (not recoverable from git — created today, never committed, then deleted)
`PREFLIGHT-GATE-RUN-HELPER` — rebuilt from the absorbed content inside `WCI-CONTENTION-TEETH`
(its phase-3 note + acceptance items L/M/N/O were written from it) plus its cited source
`fleet/state/reviews/CLASS-SCAN-UNAUDITED-GATES-agen-kolar.md`. Owns `fleet/preflight.sh` +
`fleet/tests/preflight-gate-run.test.sh` (the latter REMOVED from WCI-CONTENTION-TEETH's owns, so
there is no double-claim).

### STILL MERGED — the remaining work
`META-GATE-PREFLIGHT-WIRE-CLOSED` is **still absorbed** inside `WCI-CONTENTION-TEETH` as its
"PHASE 4". To finish:
- create it owning `fleet/preflight.sh`, `fleet/tests/meta-gate-wired.test.sh`,
  `fleet/state/GATE-GAP-LEDGER.tsv`; content = WCI-CONTENTION-TEETH phase 4 / acceptance P–T.
- `depends_on: PREFLIGHT-GATE-RUN-HELPER` (shared preflight.sh + it wires a leg through the
  fail-closed machinery that ticket establishes) **plus** `META-GATE-CALLSITE-ENUM`,
  `META-GATE-REDPROOF-REACHABLE`, `META-GATE-FINDINGS-ZERO` — those three are PHASE-4-only prereqs
  and their `real-dep:` text is already written in WCI-CONTENTION-TEETH; move it across. Dropping
  them from WCI unblocks its phases 1–2, which are NOT gated on the meta-gate trio.
- then DELETE the duplicated phase-3 and phase-4 acceptance text from `WCI-CONTENTION-TEETH`
  (currently duplicated in both places — flagged in its `unbundle-in-progress:` block), drop
  `fleet/tests/meta-gate-wired.test.sh` + `fleet/state/GATE-GAP-LEDGER.tsv` from its owns, and
  lower its `difficulty:` from 4 (it is 2 phases, not 4).
- `MARKER-PROOF-MECHANIZE` was un-merged and its `DONE-SH-INTEGRITY-FIX` edge restored, but its
  remaining prose should be re-read once more for stray "LAYER 0" references.

## 3. Waves assigned (grouping = same project + same wave + same priority)

| wave (ROADMAP.tsv) | tickets | priority |
| --- | --- | --- |
| `discovery-leg` | DISCOVERY-NORMALIZE / -DIFF / -QUEUE / -APPROVAL-WIRE / -CADENCE | all 1 |
| `gate-audit-generalization` (existing) | WCI-CONTENTION-TEETH, PREFLIGHT-GATE-RUN-HELPER, + the 3 META-GATE-* | all 1 |
| `done-marker-integrity` | DONE-SH-INTEGRITY-FIX, MARKER-PROOF-MECHANIZE | both 2 |

## 4. Edges kept vs removed

REMOVED (each was a DATA-FORMAT contract fixed by the design doc `FREE-PROVIDER-DISCOVERY-DESIGN`
and satisfied by a committed fixture — the downstream red-proofs never execute the upstream module,
and every pair has DISJOINT owns):
- `DISCOVERY-DIFF -> DISCOVERY-NORMALIZE` — D3 diffs a §3c-column TSV; its proof injects a price hike
  into a fixture snapshot.
- `DISCOVERY-QUEUE -> DISCOVERY-DIFF` — D4 consumes delta records specified in §3b/§3d; its proof
  feeds hand-written candidate/REMOVED fixtures.
- `DISCOVERY-APPROVAL-WIRE -> DISCOVERY-QUEUE` — D5 reads APPROVED rows out of a §3e-specified TSV;
  its proof supplies approved / un-approved / eval-FAIL fixture rows.
- `DISCOVERY-CADENCE -> DISCOVERY-APPROVAL-WIRE` — D6 invokes legs by ENTRYPOINT PATH on a timer. The
  edge encoded RELEASE ORDER ("nothing to schedule yet"), not a build prereq; it put a
  difficulty-1 timer behind four tickets.
- `MARKER-PROOF-MECHANIZE -> BENCH-OOB-GRADING` — stays dropped as FALSE (kept from the bundling
  pass): BENCH-OOB's `preflight.sh` is `fleet/benchmark/preflight.sh`, a DIFFERENT file.

KEPT (real):
- `DISCOVERY-NORMALIZE -> DISCOVERY-SOURCE-ADAPTERS` — there is no RawOffer shape to normalize until
  D1 defines it. BUILT, PR #219, UNLANDED: clears by LANDING.
- `DISCOVERY-APPROVAL-WIRE -> ADD-PROVIDER-MECHANIZE-COMPLETE` — D5's contract is "actuate through
  the existing mechanized add, build no second actuator". BUILT, PR #186, UNLANDED.
- `MARKER-PROOF-MECHANIZE -> DONE-SH-INTEGRITY-FIX` — RESTORED. Real on two counts: they co-own
  `fleet/done.sh`, and requiring proof before the matcher is trustworthy only hardens a matcher that
  still names the WRONG PR.
- `PREFLIGHT-GATE-RUN-HELPER -> WCI-CONTENTION-TEETH` — shared `fleet/preflight.sh`. **The approved
  preflight DECOMPOSITION (WCI phase 2: 8 inline `*_gate()` -> one file each under `fleet/checks/`)
  is what REMOVES this constraint** and lets the preflight tickets run in parallel. That is the real
  fix for the contention; fusion was not. Recorded on both tickets.
- WCI-CONTENTION-TEETH's 5 preflight.sh co-owner edges (SYNC-SCHEDULE, MARKER-PROOF-MECHANIZE,
  PLANE-CANARY-WIRE, RECONCILE-WIRING, REPO-MAP-CONVERGE) — untouched.

## 5. Validator state

`bash fleet/validate_board.sh` = **rc 1**, exactly one red, and it is NOT from this pass:

    RED orphan-marker: state/claims/TICKET-MAP-GATE matches no board ticket

Written 2026-07-24 17:32 by session `agen-kolar` in worktree
`/home/stack/charon-private-wt/TICKET-MAP-GATE` — a CONCURRENT sub-session claimed a ticket id that
has no board file. Same class as the two tickets in §1. Whoever owns that worktree must create
`fleet/board/TICKET-MAP-GATE.md` or release the claim (`fleet/release.sh TICKET-MAP-GATE`).
Immediately before that marker appeared, the board validated **rc 0, zero reds** with every change in
§1–§4 in place (`INFO` owns hand-offs on `fleet/done.sh` and `fleet/preflight.sh` are dep-sequenced;
`WARN owns-path-missing` on the not-yet-created `fleet/discovery/*` files is expected and non-blocking).

NOT DONE (budget): the `CLAIM_ONLY=<id> fleet/claim.sh --dry-run` parallel-claimable proof. By
inspection the discovery wave went from a 5-deep serial chain to **3 immediately claimable in
parallel** (DIFF, QUEUE, CADENCE — no deps at all) plus 2 gated only on landing PRs #219/#186.
