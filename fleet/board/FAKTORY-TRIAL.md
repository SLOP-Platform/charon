repo: charon-private
tier: strong
difficulty: 2
priority: 0
work_class: design-review
branch: eval/faktory-trial
owns: fleet/state/FAKTORY-TRIAL.md
depends_on:
source: fleet/state/ADOPT-EVAL-CONTROL-PLANE.md §2.1 "Faktory (contribsys/faktory) — the
  standout net-new candidate" + EVAL-REGISTRY-style rows §6 + "Bottom line for the operator."
  Read-only research; Windmill = EXECUTED (prior WLS-3 spike); Faktory = architecture+docs
  confidence only, NOT run in that research session.
work_class_note: design-review — one executed trial + a documented adopt/reject verdict, not a
  build ticket. If the verdict is ADOPT, the actual wiring (replacing loop-guard.sh's DLQ) is its
  own follow-on ticket, not this one.
note: |
  Per AP-12 (an executed trial before any adopt-commit) and the
  research-posture-solution-seeking directive: Faktory is the best pure-queue fit in the whole
  control-plane eval for "launch an arbitrary shell/agent job + native DLQ" (single container,
  embedded RocksDB — no separate Postgres/Redis; workers can be ANY language, so a shell worker
  wrapping charon-run.sh is first-class, not a hack; native retry+backoff -> "morgue" dead-set
  DLQ with Web UI, directly replacing loop-guard.sh's hand-rolled threshold=2 quarantine +
  stderr-only escalation). The crux this trial must NOT gloss over: adopting Faktory means the
  control plane's STATE moves from Faktory's own store, not from git — the git-board SSOT
  (deliberate product property, operator-mandated) is NOT replaced by this trial; only the
  loop-guard/retry/DLQ/observability layer is a candidate for replacement. Run on 4-LOM
  (10.0.1.60, `ssh -i ~/.ssh/4lom stack@...`, Docker non-root ok) per the fleet's host inventory.
  [[charon-portable-orchestration-store]] [[use-opencode-go-not-zen]]
accept: |
  - ONE EXECUTED TRIAL on 4-LOM: stand up Faktory (single container), push a real job whose
    payload wraps a trivial `charon-run.sh`-shaped shell invocation, run a shell worker that
    pulls it, executes, and ACKs/FAILs. Force at least one failure -> confirm it lands in the
    morgue (dead set) with the Web UI showing it. Force one retry-then-succeed -> confirm
    backoff+retry behavior matches the loop-guard.sh threshold semantics it would replace.
    Capture the transcript (host, exact commands, observed output/errors, container footprint —
    RAM/disk, matching the prior Windmill spike's measurement discipline).
  - fleet/state/FAKTORY-TRIAL.md: the trial transcript + a per-piece comparison table against
    loop-guard.sh (DLQ/retry/lease/priority/lifecycle/observability, same axis as the source
    doc's §2.1 "vs each piece" breakdown) + an explicit ADOPT/REJECT/ADOPT-PARTIAL verdict with
    the git-board-SSOT crux addressed head-on (does this trial's design keep git as the board of
    record, or does it require moving state into Faktory — name which, honestly).
  - EVAL-REGISTRY row: append (or draft, for the manager to append — do not fight an owns-
    collision with another live ticket over fleet/state/EVAL-REGISTRY.md; land the row via the
    normal append-only convention at merge time) `Faktory | control-plane executor/DLQ
    (loop-guard.sh replacement candidate) | <date> | <verdict> | aligned | <reason citing the
    executed trial, not README> | fleet/state/FAKTORY-TRIAL.md | —`.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  One executed trial + verdict doc. Does NOT wire Faktory into the fleet (a follow-on ticket, if
  ADOPT) and does NOT touch fleet/loop-guard.sh, fleet/claim.sh, or fleet/fleet-droid.sh.
ds: |
  ## Dependencies & sequence
  No depends_on — design/eval only, owns one new verdict doc, no code, no owns-collision with
  any other ticket in this wave or on the board.
