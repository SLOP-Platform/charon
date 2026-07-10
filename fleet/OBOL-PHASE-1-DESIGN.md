# Obol Phase 1 Design Spec

Date: 2026-07-04
Status: design/spec; no product code implemented
Inputs: ADR-0008, ADR-0010, SESSION-BRIDGE-PRODUCT-EVAL.md, PLAN-PORTABLE-ORCHESTRATION-STORE.md

## Summary

Obol Phase 1 is the product-grade coordination store for Charon's human-gated work engine. It carries over the product-worthy lessons proven by the session bridge without shipping the bridge itself.

The bridge remains build-rig-internal. It hardcodes home/project assumptions, coordinates manually launched opencode sessions, and has no shippable security posture. Obol takes only the primitive: poll-don't-push typed inbox, atomic epoch-fenced claim, derived readiness, and quorum adversarial review.

Phase 1 is intentionally not autonomous execution. Per ADR-0008, it produces and manages a human-reviewed ticket plan. Per ADR-0010, the product engine workers are Charon ACP workers and the gateway path stays untouched. Obol is a stdlib-only local coordination layer that can be installed or vendored into any project without carrying fleet, SLOP, runner, or `/home/stack` assumptions.

## Product Boundary

In scope:
- A standalone stdlib Python package or vendorable module named `obol` unless the operator renames it.
- One local daemon per project, with one SQLite WAL store and one thin CLI/proxy.
- Project-local issue graph, inbox, claims, sessions, and review votes.
- Human-gated Phase 1 workflow: import/propose ticket plan, derive readiness, claim work, exchange typed review messages, record quorum outcomes.
- Hermetic tests proving the concurrency, inbox, fencing, readiness, and migration invariants.

Out of scope:
- Shipping the existing session bridge code.
- Any `charon-private/fleet`, SLOP, droid, opencode, runner, `/home/stack`, or repo-enum assumption in product code.
- Gateway/proxy request-path imports or behavior.
- Autonomous decompose/run, auto-land, scanner-required mode, AIMD adaptive capacity, remote mesh, web dashboard, or workflow/cron engine.

## Architecture Sketch

Obol has three pieces:
- `obold`: one asyncio daemon per project; sole SQLite writer; local-only transport; starts on first use.
- `obol` CLI/proxy: thin JSON-RPC client with reconnect/backoff and session re-announcement.
- SQLite store: WAL mode, single project, no `repo` or `project` column in runtime tables.

Path policy:
- Runtime path: `$XDG_RUNTIME_DIR/obol/<project>/` when available.
- Fallback path: `~/.obol/<project>/`.
- Repo config: `.obol/config.json`.
- Greppable mirror: `.obol/issues.jsonl`, exported from the store and never source of truth.
- Never use `/run`, `/tmp/charon-*`, `~/.charon`, `/home/stack`, or fleet paths in product defaults.

Transport policy:
- Linux/macOS: AF_UNIX socket with owner-only permissions.
- Windows: AF_INET loopback on `127.0.0.1`, pending the open decision on a per-daemon token.
- No network mesh in Phase 1.

Dependency policy:
- Python stdlib only in the shippable core: `sqlite3`, `json`, `socket`, `asyncio`, `hashlib`, `pathlib`, `subprocess`, `time`, `threading` for tests.
- JSON config and hand-rolled validation. No Pydantic, TOML, Redis, Postgres, web framework, or non-stdlib runtime dependency.

## API Sketch

CLI commands:
- `obol init --project <name>`: writes `.obol/config.json` and initializes paths.
- `obol import <files...>`: imports tickets/waves into the issue graph in one transaction.
- `obol prime --session <id>`: prints standing orders, current claim, derived ready set, and inbox summary.
- `obol claim --session <id> [--tier <tier>] [--patience <n>]`: atomically claims the next ready issue and returns `{id, claim_epoch}`.
- `obol poll --session <id>`: refreshes liveness and returns unacked inbox messages.
- `obol ack --session <id> <message-id...>`: acknowledges messages after acting on them.
- `obol nudge --from <id> --to <id> --type <mtype> --payload <json>`: sends a typed message.
- `obol vote --session <id> --correlation <id> --verdict <verdict> [--finding <text>]`: records a review vote.
- `obol transition --session <id> --issue <id> --epoch <n> --status <status>`: guarded state transition for `in_review`, `done`, `blocked`, or release.
- `obol release <checkpoint-id>`: manually releases a checkpoint when configured.
- `obol status`: reports sessions, claims, ready set, stalled sessions, and unresolved reviews.
- `obol dump`: emits store state for debugging/export.
- `obol test`: runs the hermetic invariant suite.
- `obol uninstall`: stops the daemon and removes runtime state for that project.

JSON-RPC methods mirror the CLI:
- `init`, `import_issues`, `prime`, `claim_next`, `poll`, `ack`, `send_message`, `record_vote`, `guarded_transition`, `release_checkpoint`, `status`, `dump`, `shutdown`.

Message types:
- `review-request`
- `review-verdict`
- `scope-proposal`
- `scope-response`
- `handoff`
- `collision-warning`
- `block-notification`
- `ping`
- `pong`

Payload rules:
- Payloads are JSON objects with type-specific fields.
- Payloads must be small and machine-readable; prompts, secrets, full diffs, tokens, and environment dumps are forbidden.
- Messages are at-least-once. Consumers must dedupe by `correlation_id` where acting twice would be unsafe.

## Data Model Sketch

Runtime schema has no repo column and no project column. One daemon serves one project.

```sql
CREATE TABLE issues (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'task',
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    owns TEXT NOT NULL DEFAULT '[]',
    owns_verified_by_hand INTEGER NOT NULL DEFAULT 0,
    tier TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    assignee TEXT,
    claim_epoch INTEGER NOT NULL DEFAULT 0,
    release_mode TEXT NOT NULL DEFAULT 'auto',
    created_at TEXT NOT NULL,
    claimed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE edges (
    issue_id TEXT NOT NULL,
    blocked_by TEXT NOT NULL,
    real_dep TEXT DEFAULT '',
    PRIMARY KEY (issue_id, blocked_by)
);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    busy TEXT DEFAULT '',
    busy_since TEXT,
    last_seen TEXT NOT NULL,
    head_sha TEXT DEFAULT '',
    diff_hash TEXT DEFAULT '',
    connected INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    to_session TEXT NOT NULL,
    from_session TEXT NOT NULL,
    mtype TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT,
    acked_at TEXT
);

CREATE TABLE votes (
    correlation_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    lens TEXT DEFAULT '',
    verdict TEXT,
    finding TEXT DEFAULT '',
    voted_at TEXT,
    PRIMARY KEY (correlation_id, reviewer)
);
```

Config sketch:

```json
{
  "project": "charon",
  "worktree_root": "~/.obol/worktrees/charon",
  "autonomy": "gated",
  "review_quorum": 2,
  "visibility_timeout_s": 120,
  "max_busy_s": 1800,
  "tiers": { "frontier": 3, "strong": 2, "economy": 1 },
  "tier_aliases": { "opus": "frontier", "sonnet": "strong", "haiku": "economy" },
  "owns": { "case_insensitive": false }
}
```

Readiness derivation:
- `ready` is derived, not narrated.
- A task is claimable when `status='ready'`, all blockers are `done`, the claimant tier can take it, and `owns[]` is provably disjoint from every `in_progress` claim.
- Checkpoints are never claimed as work.
- `owns[]` entries are only concrete paths, directory prefixes, or segment-aware single-segment globs. If disjointness cannot be proven, treat it as a conflict unless `owns_verified_by_hand=1`.

Atomic claim:
- Daemon uses `sqlite3` autocommit plus explicit `BEGIN IMMEDIATE`.
- Candidate readiness is computed inside the transaction.
- The winning update is guarded by `WHERE id=? AND status='ready'`.
- Success is `cursor.rowcount == 1`, never `conn.total_changes`.
- Every successful claim increments and returns `claim_epoch`.
- Later transitions guard `assignee=self AND claim_epoch=my_epoch`; stale revived sessions are fenced and must abandon.

Inbox:
- `poll()` refreshes liveness and stamps `delivered_at`; it does not clear messages.
- `ack()` stamps `acked_at` after the caller acts.
- Unacked messages redeliver after `visibility_timeout_s`.

Quorum review:
- Review is a typed message plus `votes` rows keyed by `correlation_id`.
- `REJECT` requires a non-empty finding.
- Default proceed condition is two approvals, configurable by `review_quorum`.
- Panels should record distinct review lenses, not cloned reviewers.
- Operator override is always binding and logged.

## Migration Plan

Phase 0: advisory stand-up.
- Add obol package skeleton, schema, config, daemon/proxy seam, and import validator.
- Import current ticket/wave files into the store.
- Keep existing fleet/file-marker flow authoritative.
- Validate `obol status`, `prime`, derived readiness, and `issues.jsonl` mirror against current board state.
- Rollback: stop daemon and remove runtime state.

Phase 1: claim and inbox cutover.
- Sessions claim through `obol claim` and receive messages through `obol poll`/`ack`.
- Store becomes authoritative for claims and messages.
- File markers may remain as a one-way mirror only during migration.
- Retire old session-messaging daemon instances for this role.
- Rollback: repoint sessions to the previous claim plane if the mirror has stayed consistent.

Phase 2: runtime wave/collision retirement.
- Treat waves/ticket JSON as import format, not runtime scheduler state.
- Move collision enforcement into import validation plus in-transaction readiness/claim.
- Retire the separate board/collision pass for product obol; fleet-specific scripts may remain build-rig tooling.
- Rollback: re-enable separate pass and file markers.

Phase 3: bootstrap collapse.
- Replace multi-document startup for product-managed projects with `obol prime`.
- Keep full docs as reference, not mandatory session input.
- Rollback: restore prior startup docs.

Every phase must be forward/backward tested with no loss of issues, messages, votes, claims, or review state.

## Testing Plan

The merge-blocking gate is a hermetic test suite, not dogfood. Dogfood can demonstrate value but must not be the only proof.

Concurrency and claim tests:
- Barrier-align N clients against M ready tickets; assert no double claims and no lost claims.
- Inject a pause between ready-set read and update to force the TOCTOU window.
- Mutation checks must prove the test fails if the `status='ready'` guard is removed or `rowcount` is replaced with `total_changes`.
- Overlapping owns cannot be claimed in parallel.

Readiness tests:
- Chain, diamond, and fan-out blocker graphs derive the expected ready set.
- Completing a blocker makes dependents ready.
- In-progress ownership hides overlapping ready tickets.
- Checkpoints never appear in claimable results.

Inbox tests:
- Poll delivers and does not clear.
- Ack retires messages.
- Crash-before-ack redelivers after visibility timeout.
- Messages survive daemon restart and preserve order.

Fencing and liveness tests:
- Stale sessions are reaped and claims return to ready.
- Busy extends TTL but max-busy ceiling still reaps.
- Reaped-then-revived sessions fail guarded transitions with stale epochs.
- Daemon kill mid-transaction is all-or-nothing under WAL.
- Socket disconnect mid-claim reconciles without a double owner.
- Clock rollback does not false-reap.

Review tests:
- Two approvals mark done.
- Reject with finding blocks.
- Reject without finding raises.
- Busy reviewers are skipped according to policy.
- Operator override supersedes machine quorum.
- Distinct lenses are recorded.

Import and migration tests:
- Bad owns shape, duplicate owns, overlapping owns, false blocking deps without `real-dep:`, and missing dependency sections abort import.
- Partial import rolls back all rows.
- Cross-plane coexistence cannot double-claim during migration.
- Each migration phase can roll forward and back without data loss.

Boundary tests:
- Gateway/proxy/service request path imports no obol engine modules.
- Obol core imports only stdlib modules.
- Product code contains no `charon-private`, `fleet`, `SLOP`, `mediastack`, `/home/stack`, droid, or opencode build-rig assumptions.
- Runtime schema has no `repo` column and no multi-project tenant column.
- Path defaults honor XDG/fallback policy.

## Files Likely Touched

Product files likely touched when implementation starts:
- `src/charon/obol/__init__.py`
- `src/charon/obol/cli.py`
- `src/charon/obol/daemon.py`
- `src/charon/obol/proxy.py`
- `src/charon/obol/schema.py`
- `src/charon/obol/store.py`
- `src/charon/obol/transport.py`
- `src/charon/obol/validation.py`
- `src/charon/obol/owns.py`
- `src/charon/obol/review.py`
- `tests/test_obol_claim.py`
- `tests/test_obol_inbox.py`
- `tests/test_obol_readiness.py`
- `tests/test_obol_review.py`
- `tests/test_obol_liveness.py`
- `tests/test_obol_import.py`
- `tests/test_obol_migration.py`
- `tests/test_obol_boundary.py`
- `tools/check_boundary.py` if needed to extend stdlib/boundary enforcement.
- `pyproject.toml` only to expose the CLI entry point and package files.
- `docs/adr/0008-work-intake-ticket-plan-pipeline.md` or a follow-on ADR note if the accepted ADR needs an implementation appendix.
- `docs/DECISIONS.md` if operator-owned open decisions are settled.

Fleet/build-rig files likely touched for rollout records only:
- `/home/stack/charon-private/fleet/PLAN-PORTABLE-ORCHESTRATION-STORE.md`
- `/home/stack/charon-private/fleet/SESSION-BRIDGE-PRODUCT-EVAL.md`
- Future ticket specs/prompts for implementation slices.

## Suggested Implementation Slices

1. Boundary and skeleton: package, CLI stub, stdlib-only/boundary tests, config path resolver.
2. Schema/store: SQLite WAL initialization, migrations, one-project invariant, dump/status.
3. Import/validation: ticket import, owns vocabulary, dependency validation, rollback.
4. Readiness/claim: derived ready set, `BEGIN IMMEDIATE`, `rowcount`, `claim_epoch`, guarded transitions.
5. Inbox: typed messages, poll/ack, visibility timeout, liveness refresh.
6. Review: votes, quorum resolver, operator override record.
7. Daemon/proxy/transport: AF_UNIX/Windows loopback seam, reconnect/backoff, first-use spawn.
8. Migration mirror and `prime`: issues.jsonl export, concise bootstrap output.

## Open Questions

1. Tool name: keep `obol`, or rename to `ferry`/`skiff` before product code and paths land?
2. Packaging location: ship under `src/charon/obol` as part of Charon first, or as a standalone top-level package with Charon vendoring later?
3. Windows loopback: require a per-daemon token for AF_INET loopback, or accept single-user loopback in Phase 1?
4. Autonomy default: keep `gated` by default, with judge-panel fallback only in `autonomous` mode?
5. Timeout defaults: are `visibility_timeout_s=120` and `max_busy_s=1800` acceptable initial defaults?
6. Checkpoint auto-release: what exactly counts as gate-green: local gate, CI status, review quorum, or both local+CI?
7. ID scheme: use `ix-<sha1(title+nonce)[:10]>`, content-addressed body hash, or longer collision-resistant IDs?
8. Mirror cadence: export `.obol/issues.jsonl` on every state transition, periodically, or both?
9. Recursive ownership: keep `**` forbidden and split tickets when recursive ownership is needed, or add a decidable recursive-prefix form?
10. ADR naming: should this remain an implementation appendix to ADR-0008 Phase 1, or become a new ADR for the portable orchestration store?
