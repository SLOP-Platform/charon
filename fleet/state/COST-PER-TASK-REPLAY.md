# COST-PER-TASK-REPLAY

> P0 harness. Feeds `GRADE-MODEL-PROVIDER-PAIR` and the routing sort key.
> Consumes SPEND-METRIC-TRUSTWORTHY's per-provider attribution — start
> selection/replay half now, join real spend when that lands.

## Metric definition

```
cost_per_accepted_task = total_spend / accepted_tasks
total_spend             = sum of spend across ALL attempts
                         (every retry, every failover leg, every model tried)
accepted_tasks          = tasks passing ADVERSARIAL REVIEW WITH NO CHANGES REQUIRED
```

The quality floor is load-bearing. Without "no changes required", cheap degenerates
into "fails cheaply".

## Architecture

### Selection (representative sample)

Real landed tickets are the universe. A *selection* is a small subset drawn from
the board's `done` units, stratified by `work_class` x `difficulty`. The sample
is refreshed on a cadence; the board composition is the ground-truth distribution.

Drift gate: if the selected sample's work_class x difficulty distribution
deviates significantly from the current board's distribution, the sample is
rejected and re-drawn. This is the mechanical gate that keeps the sample
representative — it cannot drift from real work because it IS real work.

```python
@dataclass
class TicketSample:
    ticket_id: str
    work_class: str
    difficulty: int          # 1-5
    tier: str                # work_class tier
    # board position at time of selection
    board_snapshot: str      # git ref of board state at selection time
```

### Replay execution

For each sampled ticket:
1. Read the ledger (the single source of truth for progress)
2. Replay: drive the same acceptance criteria against the same base ref
   - Record spend per attempt (checkpoint usage)
   - Record whether adversarial review passed with no changes required
3. Annotate each checkpoint with whether the final outcome was ACCEPTED

### Outcome classification

```
ACCEPTED      = passed adversarial review with zero change requests
               (the "no changes required" quality floor)

NOT_ACCEPTED  = required reviewer changes, or failed review, or exhaustion
```

A task that passes review but burns 5x tokens IS NOT accepted — the quality
floor catches the degenerate "passes review but is wasteful" case.

### The join

```
ledger.spend  (per checkpoint, cumulative)
    + ledger.outcome  (ACCEPTED | NOT_ACCEPTED)
    + ticket.metadata (work_class, difficulty, tier)
    → cost_per_accepted_task(work_class, tier, model_id, provider)
```

The join is the deliverable. Inputs already exist in the ledger.

## Data types

```python
@dataclass
class ReplayResult:
    """One replay run for a (model_id, provider) on a sample of tickets."""

    model_id: str
    provider: str
    sample_id: str              # identifies the ticket sample used
    work_class: str
    tier: str

    total_spend_usd: float     # sum across ALL attempts on accepted tasks
    accepted_tasks: int
    total_tasks: int           # tasks in sample
    cost_per_accepted_task: float | None  # None when accepted_tasks == 0

    total_attempts: int        # total dispatch attempts across all tasks
    total_tokens_in: int
    total_tokens_out: int

    # Per-task breakdown for auditing
    task_results: list[TaskResult]

    timestamp: float

    @property
    def acceptance_rate(self) -> float:
        return self.accepted_tasks / self.total_tasks if self.total_tasks else 0.0


@dataclass
class TaskResult:
    """Result for one sampled ticket."""

    ticket_id: str
    accepted: bool
    spend_usd: float
    attempts: int
    tokens_in: int
    tokens_out: int
    reviewer_passed: bool
    reviewer_changes_required: bool
    # which model+provider served each attempt
    attempts_detail: list[AttemptDetail]


@dataclass
class AttemptDetail:
    """One dispatch attempt within a task."""

    attempt_seq: int           # 1-indexed within task
    checkpoint_seq: int        # ledger checkpoint seq
    model_id: str
    provider: str
    spend_usd: float
    tokens_in: int
    tokens_out: int
```

## Fail-on-revert assertion

Asserted on seeded data:

```
For any (work_class, tier):
  Let M_cheap = model with lowest cost_per_accepted_task
  Let M_expensive = model with highest cost_per_accepted_task
  If M_cheap has acceptance_rate << M_expensive, the cheap rank is WRONG
```

Implementation: `assert fail_on_revert_pass(results: list[ReplayResult]) -> bool`

The assertion fails when a model that passes review but burns 5x tokens ranks
WORSE than a dearer model that lands first time.

## Integration points

### Feeds GRADE-MODEL-PROVIDER-PAIR

The replay result is a real outcome that feeds into the grading pipeline.
A `ReplayResult` with `accepted_tasks > 0` is a valid signal for
`grades.reconcile_with_real()`.

Provider is part of the identity because quantization, hardware, and hidden
prompts make provider non-trivial. The grade is `(model_id, provider)` not
just `model_id`.

### Routing sort key

`cost_per_accepted_task` replaces `cheapest-per-token` as the routing sort key
per (work_class, tier). Cheapest-per-token without quality floor → selecting
for failure. Cheapest-per-accepted-task includes the quality floor.

### Board composition reader

Reads `engine/board.py` for:
- All `done` units with `work_class` and `difficulty` attributes
- Current board composition for drift detection

### Ledger join

Reads `ledger.py` for:
- `Ledger.checkpoints()` → per-attempt spend
- `Checkpoint.usage.cost_usd` → spend per checkpoint
- `Checkpoint.reviewer_passed` → adversarial review result
- `Ledger.cumulative_usage()` → total spend for the task

## P0 scope (this ticket)

- Selection harness: stratified sample from done-board
- Ledger join: spend → ticket → outcome
- Metric computation: cost per accepted task
- Fail-on-revert assertion on seeded data
- Routing key emission per (work_class, tier)

## P1 (out of scope here)

- SPEND-METRIC-TRUSTWORTHY integration (per-provider attribution)
- Live cadence refresh
- Drift gate implementation
- Freeze-ring integration

## Design decisions

1. **Ledger is the source of truth for spend.** Not the metering callback.
   Ledger checkpoints record `Checkpoint.usage.cost_usd` which is the authoritative
   per-dispatch cost (ADR-0003 INV-1).

2. **Provider is part of the identity.** Quantization, hardware, and hidden
   prompts make provider part of the model identity for cost purposes. A model
   on two different providers can have different cost-per-accepted-task.

3. **No synthetic benchmark suite.** The "representative task sequence" is a
   selection over real history and cannot drift from the work we actually do.

4. **"No changes required" is the quality floor.** A task that passes review
   but required 10 reviewer round-trips is not accepted. The floor catches the
   degenerate "passes review but burns tokens" case.
