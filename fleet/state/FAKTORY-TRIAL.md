# Faktory 1.9.4 re-investigation trial

Date: 2026-08-01. Host: 4-LOM (`10.0.1.60`), Docker container `faktory`, image `contribsys/faktory:latest` (server reported `Faktory 1.9.4`). The password was read only on 4-LOM and was not recorded.

## Executed trial

The container was restarted as instructed:

```text
$ ssh -i ~/.ssh/4lom stack@10.0.1.60 'docker start faktory'
faktory
```

The existing client/worker test was run against the live server:

```text
$ export FAKTORY_HOST=10.0.1.60 FAKTORY_PASSWORD="$(ssh -i ~/.ssh/4lom stack@10.0.1.60 'cat ~/.faktory/password')"
$ bash fleet/faktory/test-faktory.sh
### T1: reserved job invisible to a second reserve
PASS: T1 reserved job (...) held; 2nd reserve empty rc=1
### T2: ACKed job durably GONE across REAL container recreation
  acked ...
  recreating faktory container on 10.0.1.60 (real restart, graceful SIGTERM)...
PASS: T2 ACKed job ... GONE after real recreation; control job ... survived (RDB persisted)
### T3: FAILed job requeues (returns to retries set, becomes re-fetchable)
PASS: T3 FAILed job ... requeued (state=retries) — not lost, not dead
### T4: worker e2e — reserve, run charon-run-shaped payload, ACK
[faktory-worker] ... reserved jid=...; running payload
[faktory-worker] ... ACK jid=... (success)
PASS: T4 worker ran payload (side effect /tmp/faktory-e2e-... created) and ACKed; job absent
==== RESULTS: 4 passed, 0 failed, 0 skipped ====
```

The exact run produced four passes and zero failures. Container logs confirmed `Faktory 1.9.4`, RDB initialization at `/root/.faktory/db`, protocol port 7419 and web port 7420. The test recreated the container using the preserved `faktory-data` volume, proving an ACKed job was absent while a control job survived. The worker executed a shell payload shaped like a `charon-run.sh` invocation and ACKed it. A deliberate FAIL entered `retries`; the existing client test did not wait for a timed retry to become ready, so retry backoff timing was not independently observed in this pass.

The container was stopped after the trial:

```text
$ ssh -i ~/.ssh/4lom stack@10.0.1.60 'docker stop faktory'
faktory
```

## Full capability matrix

Status is for OSS Faktory 1.9.4 unless marked Enterprise. Capability names were checked against the upstream Faktory feature/documentation surface and the running 1.9.4 API/UI; where this client does not expose a verb, that is recorded rather than inferred as absent.

| Capability | OSS 1.9.4? | Fleet use today | Named incident/problem served |
|---|---|---|---|
| Push/reserve/ACK/FAIL, reservation timeout | Yes | Yes, direct substrate | Stranded submitted-but-never-done tickets; worker crash recovery |
| Retry with exponential backoff | Yes | Partial (FAIL is wired; timing not measured here) | ALL-EXHAUSTED stalls; transient provider failures |
| Morgue/dead jobs and web UI | Yes | Yes, client has `dead:morgue` lookup | PRs rotting 370h+; stranded jobs |
| Scheduled/one-shot jobs | Yes | Not exposed by fleet client | Retry deferral and planned follow-up work |
| Cron/recurring jobs | Enterprise-only (Pro) | No | No current ticket; cadence jobs remain shell cron/foreman |
| Queue priorities/weighted queues | Yes (queue ordering/weights) | Not wired; client accepts one queue | P0 starvation behind economy work; ALL-EXHAUSTED stalls |
| Unique jobs/deduplication | Enterprise-only (Pro) | No | Duplicate submissions/claim exactly-once; current marker is git/shell |
| Batches | Enterprise-only (Pro) | No | No current named need; multi-step ticket completion could use it later |
| Throttling | Enterprise-only (Pro) | No | Provider/key caps; 2026-08-01 three false quarantines from OpenRouter cap |
| Callbacks | Enterprise-only (Pro) | No | Completion notification/reconciliation; no current callback consumer |
| Middleware | Client-library feature, not server OSS capability | No standard fleet middleware API | Failure classification would need worker-side implementation |
| Mutate API | Enterprise-only (Pro) | No | Changing queued jobs without delete/reinsert; no current consumer |
| Queue pause/resume | OSS web/API operational control | No automation | Incident containment during provider outage; could have limited the OpenRouter-cap blast radius |
| Job expiry/expiration | Enterprise-only (Pro) | No | Prevent stale submitted tickets and PR work from rotting |
| Web UI/queue inspection | Yes | Available, not the SSOT | Operator observability for morgue/retry/backlog |
| TLS/authentication | OSS auth; TLS deployment/configuration | Password auth used; no TLS trial | Control-plane access protection |

Enterprise-only conclusions materially constrain the attractive features: batches, unique jobs, throttling, callbacks, mutate, cron and expiry are paid capabilities. OSS still supplies a durable queue, reservation lease, retry/morgue and queue operations.

## Comparison with `loop-guard.sh` today

| Piece | Faktory OSS | loop-guard today |
|---|---|---|
| DLQ | Durable morgue plus UI | Quarantine files/records; available but shell-managed |
| Retry/backoff | Server-managed exponential retry | Hand-rolled retry/guard policy |
| Lease | Reservation timeout and requeue | Separate work-lease/claim machinery |
| Exactly-once | No exactly-once execution; ACK is at-least-once boundary | Git marker/flock can suppress duplicate enqueue, not execution |
| Priority | Queue ordering/weights available, not currently wired | Ticket priority is board metadata; dispatch remains shell policy |
| Lifecycle | Enqueued → busy → ACK/FAIL/retry/morgue | Git claim, worktree, PR and review lifecycle |
| Observability | Web/API queue state | Git board plus shell state and logs |
| Failure classification | None: FAIL is a generic worker outcome | Intended infra/model distinction, currently inert because callers do not pass `--reason`; caused three false P0 quarantines on 2026-08-01 |

## Git-board SSOT and corrected lens

Faktory can fill a real execution gap without replacing the board: execution state (queued, reserved, retrying, dead, acknowledged) would live in Faktory, while ticket ownership, dependencies, priority, worktree, commits, review and operator decisions remain in git-tracked `fleet/board/*.md`. However, this creates two state planes and requires reconciliation. Faktory cannot be the source of truth for the operator-mandated git board, and it cannot encode failure classification or the full Charon lifecycle by itself.

The measured need is real: the three false quarantines caused by the OpenRouter cap, ALL-EXHAUSTED stalls, stranded submitted-but-never-done tickets, and 370h+ PR rot all benefit from durable execution state, but only some benefit from Faktory OSS. Paid throttling/expiry/unique features would directly address the incidents; OSS queue pause and worker retry do not classify infra versus model failures.

## Verdict

**ADOPT-PARTIAL — retain the existing Faktory OSS substrate as an optional execution queue, but do not claim it is wired or the fleet’s sole control plane.** The live trial proves durability, reservation exclusivity, worker execution and FAIL-to-retry. Do not purchase Enterprise or wire batches/cron/unique/throttling/callbacks/mutate/expiry until a named ticket demonstrates the need and cost. Immediate work remains `LOOP-GUARD-REASON-WIRE`: fix failure classification independently, then define a reconciliation adapter that records Faktory jid/state alongside the git board without moving board SSOT. The present tree has zero `claim.sh` references to Faktory/`lease-enqueue`; the old adoption claim was therefore false in practice.

## EVAL-REGISTRY row

```text
| Faktory | durable execution queue/lease/retry substrate for Charon fleet (OSS 1.9.4; Enterprise capabilities separately assessed) | 2026-08-01 | ADOPT-PARTIAL — optional execution substrate; not sole control plane | aligned | Live 4-LOM trial proved reservation exclusivity, RDB durability across real container recreation, worker execution/ACK, and FAIL→retries. Corrected lens identifies a real unmet durable-execution need, but OSS lacks paid throttling/expiry/unique/batches and Faktory does not classify infra-vs-model failures or replace git-board SSOT. Existing claim path has zero Faktory references, so adoption is not wired in practice. | fleet/state/FAKTORY-TRIAL.md; fleet/faktory/test-faktory.sh; upstream Faktory 1.9.4 | supersedes undocumented/override adoption claim; no prior trial document existed |
```
