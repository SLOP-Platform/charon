repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 1
branch: eval/faktory-reinvestigate
depends_on:
owns: fleet/state/FAKTORY-TRIAL.md
serial_justified: |
  One tool, one capability sweep, one verdict. The capability matrix only means anything measured
  in a single pass against a single running instance.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. EVAL lane — measure and report. Wire NOTHING.
  The Faktory container on 4-LOM is currently STOPPED (volume `faktory-data` preserved). Restart it
  for the trial: `ssh -i ~/.ssh/4lom stack@10.0.1.60 'docker start faktory'`. Password lives ONLY at
  `~/.faktory/password` on 4-LOM (chmod 600) — never commit it, never paste it into a report.
source: |
  Operator, 2026-08-01: re-investigate Faktory under the corrected lens with FULL capabilities, to
  properly decide whether it should be wired.
note: |
  ## WHY THIS IS A RE-INVESTIGATION, NOT A REPEAT — the first decision was never actually made
  Traced to primary sources 2026-08-01. **Every evidence document the adoption rests on is missing:**
    - `fleet/state/ADOPT-EVAL-CONTROL-PLANE.md` (the origin, called Faktory "the standout net-new
      candidate") — **does not exist at any commit**; a prior droid searched and confirmed.
    - `fleet/state/FAKTORY-TRIAL.md` (transcript + verdict + the git-SSOT crux) — **never created**.
      `git log --all -- <path>` is empty.
    - EVAL-REGISTRY Faktory row — **absent**.
    - `TRIAL-FAKTORY`, cited by the adopt record as the ADOPT-PARTIAL verdict source — **no document
      of that name exists**.
    - `fleet/state/FAKTORY-ADOPT.md` — dropped from the tree; readable only at `a750b89`.
  FAKTORY-TRIAL was closed with `override:eval superseded by FAKTORY-ADOPT merged #243`. So the
  rig's own AP-12 gate ("an executed trial before any adopt-commit") was bypassed by override.
  **There is no verdict to overturn — there is a decision that was never recorded.**

  Real work WAS done and must not be re-derived: footprint measured (~34.6MB image, ~12.7-15MB RAM,
  single container, Faktory 1.9.4), and a genuine correction — the `/data` mount is DEAD, the real
  RDB path is `/root/.faktory`. Carry those forward.

  ## THE STATE TODAY (measured 2026-08-01)
  - Server ran on 4-LOM for **7 days with ZERO workers**.
  - `fleet/claim.sh` has **zero** references to `lease-enqueue` or `faktory`
    (`grep -cE 'lease.enqueue|faktory|enqueue' fleet/claim.sh` = 0).
  - `fleet/lease-enqueue.sh` self-describes as "THE single enqueue chokepoint ... the ONLY
    sanctioned path that starts work" — and nothing calls it.
  - `loop-guard.sh`, the thing Faktory was adopted to REPLACE, is still live and still hand-rolled.
  So the adopt record's claim ("the fleet's SOLE durable job/lease/retry/DLQ substrate", "the
  claim-lease store CLAIM-LEASE-EXACTLY-ONCE codes against") is **false in practice**.

  ## THE NEED IS REAL — do not evaluate this in the abstract
  On 2026-08-01 `loop-guard.sh` quarantined THREE P0 tickets after an OpenRouter key cap, because
  its infra-fault exemption is inert (no caller passes `--reason` — see LOOP-GUARD-REASON-WIRE).
  A durable lease/retry/DLQ substrate with correct failure classification is an unmet need, not a
  solved one. Judge Faktory against THAT.

  ## SCOPE — FULL CAPABILITY SWEEP (this is the part never done)
  The original trial scoped ONE question: "can it replace loop-guard's DLQ?" Our integration
  implements only five verbs — `push`, `reserve`, `ack`, `fail`, `info` — plus morgue and
  retry/backoff. **Enumerate and test Faktory's ACTUAL full surface from its own docs/source**
  (do not trust this ticket's list, and do not trust the model's memory — verify against the
  running 1.9.4 instance and the upstream repo):
  batches · scheduled/cron jobs · queue priorities & weighting · unique jobs · throttling ·
  callbacks · middleware · the mutate API · queue pause/resume · job expiry · OSS-vs-Enterprise
  split (which of the above are PAID-ONLY? that materially changes the verdict).
  For EACH capability: does it exist in OSS 1.9.4? does the fleet have a use for it TODAY, and
  which named ticket/problem would it serve?

  ## THE CORRECTED LENS (mandatory — the old verdict framing is void)
  - **"What does this replace?" is BLIND TO GAPS.** Ask what it FILLS that we lack. A capability
    filling an unmet need scores high even if it deletes nothing.
  - **Size / dep-count / "one more container" are NOT rejection criteria.** Ops burden and control
    direction ARE.
  - Every leverage claim must name a MEASURED incident it would have prevented. Candidates:
    the 3 false quarantines (2026-08-01), the ALL-EXHAUSTED stalls, stranded submitted-but-never-
    done tickets, PRs rotting 370h+.
  - **The git-board-SSOT crux, head-on:** does wiring Faktory move control-plane state OUT of git?
    The git board is an operator-mandated product property. Say plainly which state would live in
    Faktory vs git, or say it cannot be reconciled.

  ## DELIVERABLE — `fleet/state/FAKTORY-TRIAL.md` (the doc that was never written)
  1. Executed trial transcript: host, exact commands, observed output. Restart the container, push
     a real job wrapping a `charon-run.sh`-shaped invocation, run a shell worker, ACK it. Force a
     failure -> confirm it reaches the morgue. Force retry-then-succeed -> confirm backoff.
  2. FULL capability matrix (above), OSS-vs-Enterprise marked.
  3. Per-piece comparison against `loop-guard.sh` TODAY: DLQ · retry/backoff · lease ·
     exactly-once · priority · lifecycle · observability · **failure CLASSIFICATION**
     (infra-vs-model — the thing that broke tonight).
  4. Verdict: ADOPT / ADOPT-PARTIAL / REJECT — with, if ADOPT, the concrete wiring plan naming the
     files, and if REJECT, what we build or keep instead.
  5. **EVAL-REGISTRY row** — append it. A verdict not in the registry gets paid for twice; that is
     precisely how this tool got adopted on a citation to documents that do not exist.

  ## HONEST OUTCOMES ARE BOTH FINE
  "REJECT — the need is real but Faktory is the wrong shape, here is why" is as valuable as ADOPT.
  What is NOT acceptable is another undocumented verdict. Do not restart the container permanently:
  stop it again when the trial ends unless the verdict is ADOPT.

D&S — Deps & Sequence:
  - Depends on: nothing. Pure eval, owns one doc, collision-free.
  - Related: LOOP-GUARD-REASON-WIRE fixes the immediate inert-exemption bug regardless of this
    verdict. The two are independent — do not block either on the other.
