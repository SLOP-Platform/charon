# Portable Orchestration Store — Implementation + Testing Plan

**Date:** 2026-07-02
**Version:** **v2** — a 4-lens debate-to-consensus panel (architecture/simplicity · portability/stdlib-leak · store-concurrency/correctness · testing/migration) unanimously **REJECTed v1** ("fixable, not fundamentally wrong"); this pass resolves every finding. The thesis, prior-art credits, derived readiness, and the idle-is-free / ephemeral-per-ticket cost wins survive unchanged.
**Scope:** ADR-0008 Phase 1 — graduate the home "fleet rig" into an in-tree, shippable work-engine
**Working tool name:** `obol` (the coin paid to Charon — a small, portable unit) — **OPEN DECISION, operator-owned** (alternatives below)
**Status:** DRAFT v2 — DTC findings folded in; ready for re-review
**Companion:** BRIDGE-DAEMON-PROPOSAL.md (the session-messaging daemon this store subsumes/extends)
**Min-Python:** **3.9** (covers Ubuntu 22.04 / Debian 11 default interpreters)

---

## DTC Resolution (v2)

The v1 panel returned unanimous REJECT-with-finding. Each blocker and each operator ruling is
folded in below; this section is the audit trail — the fix lives where the section number points.

**7 consensus blocker-fixes**

| # | Blocker (v1) | Fix applied (where) |
|---|---|---|
| 1 | `claim_next` used cumulative `conn.total_changes` as a per-claim won-signal → always truthy after the first claim → **double-claims** | Capture the UPDATE's `cursor.rowcount`; `won = (cur.rowcount == 1)` (§4) |
| 2 | Collision gate rested on `fnmatch` pattern-vs-pattern, which **cannot decide whether two globs intersect** → false "disjoint" | Redefine `owns[]` to **decidably-checkable** prefixes / concrete paths / **segment-aware single-segment globs** (glob never crosses `/`); **conservative: unproven-disjoint ⇒ CONFLICT**; `owns_verified_by_hand` human escape hatch; case-explicit `fnmatchcase` (§7, §3) |
| 3 | Inbox was **at-most-once** — `poll()` cleared+committed before bytes reached the session → a dropped review-request wedges a ticket in `in_review` | **Explicit ack**: `poll()` stamps `delivered_at` + visibility timeout, does not clear; `ack(ids)` stamps `acked_at`; unacked past timeout redeliver (§5) |
| 4 | Concurrency model was self-contradictory (single-writer daemon **and** N-process claimers) and the daemon was an unrecovered SPOF | **One asyncio daemon = sole writer**; in-memory ready-set on a read snapshot then ONE guarded UPDATE; `isolation_level=None` + explicit `BEGIN IMMEDIATE`/`COMMIT` + `busy_timeout`; **proxy carries a reconnect-with-backoff loop**; on reconnect the daemon reconciles via `claim_epoch`+`head_sha`/`diff_hash` (§1, §4) |
| 5 | Reaper reintroduced the collision `owns[]` prevents — a reaped-but-live session and its replacement both hold the same files (**no fencing**) | Monotonic **`claim_epoch`** per ticket; every transition guards `assignee=self AND claim_epoch=my_epoch`; a revived session fails the guard and abandons; **max-busy ceiling** so `busy` can't exempt a crash forever (§4, §7, liveness) |
| 6 | Stdlib-only was violated by the proposed defaults (TOML/`tomllib` 3.11, Pydantic, `/run`, AF_UNIX-on-Windows) | Defaults flipped zero-dep: **JSON config**, **hand-rolled stdlib validator**, **min-Python 3.9**, transport abstraction (**AF_UNIX Linux/mac, AF_INET 127.0.0.1 Windows**), socket/db under `$XDG_RUNTIME_DIR` or `~/.obol/` (**never `/run`**), daemon spawns as a subprocess (**no systemd requirement**) + uninstall path (§0, §1, Portability) |
| 7 | Tests could not catch bugs 1–5 (`:memory:`, no forced races, no mutation check) | `threading.Barrier`-aligned socket clients + **injectable pause-hook** across the read→UPDATE TOCTOU; **mutation check** (deleting the guard must FAIL the test); **real temp-file WAL DB via concurrent clients**; negative controls, daemon-kill-mid-txn, socket-disconnect-mid-claim, cross-plane double-claim, clock-backward, wedged-busy ceiling, partial-import rollback; injected `now()` + seeded id/random; **hermetic `obol test` is the CI gate, dogfood is a demo** (Testing) |

**3 operator rulings**

| Ruling | How it's encoded |
|---|---|
| **One daemon PER PROJECT** (deploy-time stands one up for that project) | The `project` column/PK/index/WHERE is **removed** from every table; the daemon's config names its single project. Kills the honor-system cross-tenant hole; the multi-tenant isolation test is deleted (§1, §2, Portability) |
| **Optional checkpoint/barrier primitive** | A `checkpoint` issue node downstream tickets may `blocked_by` **without** a `real-dep:` marker (the disjoint-owns validator allows a dep ON a checkpoint). **Default auto-release** when the upstream wave is all-done + gate-green; **manual release** opt-in. No forced operator eyeball by default (§2, §7) |
| **Right-size consensus, drop the crypto** | Adversarial-review-to-consensus stays (hard requirement) but the panel is **diverse-lens (distinct lenses / real peer sessions), NOT N identical clones**; cheap quorum vote-tracking stays; **`reconnect_hash` sha256 identity-proof dropped** — identity is a plain session-id, fencing is `claim_epoch` (§6, §2) |

---

## Thesis

The home "Droid Method" has already independently reinvented ~90% of the multi-agent
orchestration field, and is **ahead of the public state of the art on three points**:

1. **Idle-is-free cold pooling** — an idle session is a sleeping bash shell burning *zero
   model tokens*. The model is spawned only at the moment work is claimed. Most public
   frameworks keep a warm, context-loaded agent burning tokens while it waits.
2. **Ephemeral-per-ticket as an anti-drift *feature*** — one session = one ticket, then exit.
   Bounded context, no accumulated drift, no stale plan. This is a deliberate design property,
   not a limitation.
3. **Physics-grounded lie-detection** — liveness and honesty are derived from *observable
   ground truth* (git HEAD, uncommitted-diff hash, mailbox POSTED count) versus what a session
   *says* it's doing. Self-report is never trusted.

**The problem is NOT missing mechanisms. The problem is FRAGMENTATION.** The method is smeared
across four generations of tooling and **two coexisting coordination planes**:

- **The file/flock plane** — `state/{claims,submitted,done}/` markers, `waves/smart-routing.json`
  as a hand-authored schedule, and `validate_board.sh` as a separate collision pass.
- **The SQLite bridge-daemon plane** — newer, only partly cut over (4 stale `server.py`
  instances, per BRIDGE-DAEMON-PROPOSAL.md).

On top of both sits a **heavy 5-document bootstrap read-tax** every session pays before it can
do anything.

**The better way is SUBTRACTION.** Collapse both planes to **ONE store** with **DERIVED (not
hand-authored) scheduling**. The wave manifest, the flock gate, and the separate collision pass
all disappear — replaced by a single SQL query over one table. This document specifies that
store, its portability model, its migration path, and its test suite.

---

## Goals / Non-goals

**Goals**
- One source of truth: a single SQLite store behind one daemon, one thin proxy per session.
- Scheduling is *derived* from ticket state + a blocker graph, never hand-authored.
- **Portable** — one reusable component deployable to *any* project (Charon first, SLOP/mediastack
  second, future products later). NOT a Charon-only rig.
- **Stdlib-only** so the exact same code can graduate into a shipping product (pipx/uvx-installable,
  no rig leak).
- Preserve every already-best-in-class mechanism: typed-nudge inbox, quorum review, idle-is-free
  pooling, ephemeral-per-ticket, disjoint-owns collision contract.
- Collapse the 5-doc bootstrap to a single `prime` command.

**Non-goals (this phase)**
- No cross-machine mesh / relay (local Unix socket only — see BRIDGE-DAEMON-PROPOSAL AVOID §4).
- No web dashboard (MCP/CLI is the interface — AVOID §5).
- No embedded workflow/cron engine (AVOID §6).
- No non-stdlib dependency of ANY kind in the shippable core (see Architecture §0).
- Not a rewrite of the model-router / gateway — this is the *orchestration* layer only.

---

## Prior art (what we keep, what we borrow, credited)

We keep the **Droid Method's** own inventions wholesale: idle-is-free cold pooling,
ephemeral-per-ticket, physics-grounded lie-detection (git-HEAD/diff-hash vs self-report), the
typed-nudge inbox, and the disjoint-`owns[]` collision contract. From **beads** we adopt the
*model only* — issues as first-class records with a live `blocked_by` dependency graph, hash-based
IDs, and a `prime`-style low-token bootstrap — but NOT beads-the-tool (it is not stdlib; see §0).
From **swarm-tools / agent-teams** we take the atomic work-stealing claim and down-tier draining.
From the **inbox model** (and repowire, reviewed in BRIDGE-DAEMON-PROPOSAL.md) we take poll-don't-push
delivery, correlation-tracked asks, and clear-on-read TTL liveness. From **GSD**-style planning we
take the "readiness is derived, never narrated" discipline. Everything below is a *synthesis* of
these into one stdlib store — the novelty is the subtraction, not any single mechanism.

---

## Architecture

### §0 — HARD product-safety constraint: stdlib only

The shippable core uses **Python stdlib only** — `sqlite3`, `json`, `socket`, `asyncio`. NOT beads,
NOT Dolt, NOT Redis, NOT Postgres, **NOT Pydantic, NOT `tomllib`**, NOT any pip dependency in the
coordination core. Reason: the product must stay **pipx/uvx-installable with zero external services**
— a fresh-install user runs `pipx install obol` and it works, no database server to provision, no
daemon fleet beyond the one local process. `sqlite3` ships with CPython; a single file DB in WAL mode
gives us ACID transactions, concurrent readers, and a single writer — exactly the shape we need. Any
richer store would be a **rig leak**: it works at home and breaks on a customer's laptop.

The v1 draft violated this in its own defaults. **v2 flips every default to zero-dep** (this closes
Open Decisions #3 and #5):

- **Config = JSON** (`.obol/config.json`), read *and written* with stdlib `json`. No `tomllib` (which
  imposes a 3.11 floor and has no stdlib *writer*, so `obol init` couldn't emit it). Matches the
  `waves/*.json` import format.
- **Validation = a hand-rolled stdlib validator** (specified in Portability → import): required
  fields, types, `owns[]`-shape, dep-justification. **No Pydantic.**
- **Min-Python = 3.9** — covers the Ubuntu 22.04 / Debian 11 system interpreters a pipx user is
  likely on. All code below stays within 3.9 stdlib.
- **Transport is portable** — AF_UNIX on Linux/mac, **AF_INET loopback (127.0.0.1) on Windows** (where
  AF_UNIX is unreliable), behind one transport abstraction (§1). Socket + DB live under
  `$XDG_RUNTIME_DIR` or `~/.obol/`, **never `/run`** (a pipx user cannot `mkdir` there).

This zero-dep posture is what keeps the Windows-client surface Charon targets viable.

### §1 — One store, one daemon, one proxy

```
┌──────────────────────────────────────────────────────────────┐
│         obold  (ONE daemon PER PROJECT — config names it)    │
│                                                              │
│   transport abstraction  SQLite (WAL, temp-file)  liveness    │
│   AF_UNIX  (Linux/mac)   ~/.obol/<project>/db     sweeper     │
│   AF_INET  127.0.0.1     single writer (the loop) reaper +    │
│   (Windows)              autocommit+BEGIN IMMEDIATE epoch fence│
│   JSON-RPC frames        exports issues.jsonl mirror          │
└───────┬──────────────────────────────────────────────────────┘
        │  JSON-RPC over the transport
  ┌─────┴───────┬─────────────┐
  ▼             ▼             ▼
 proxy.py     proxy.py      proxy.py    (~60 lines: forward + reconnect-with-backoff)
 session A    session B     session C
 (all belong to this project's daemon)
```

- **`obold`** — a single asyncio daemon, **sole SQLite writer** (all writes serialized on the event
  loop), no HTTP framework, no WebSocket (per BRIDGE-DAEMON-PROPOSAL HARD RULES 13–18). **One per
  project** (operator ruling): deploy-time stands up a daemon for that project; its config names its
  single project, so no `project` key threads through the schema and there is no cross-tenant hole.
- **`proxy.py`** — a thin forwarder that opens the transport, forwards one JSON-RPC request, returns
  the response — **plus a reconnect-with-backoff loop** (fix #4): the daemon is not an
  unrecovered SPOF but the proxy is not zero-logic either. On daemon crash a session gets
  ECONNREFUSED; the proxy retries with exponential backoff, and **on reconnect re-announces its
  session-id + current claim (ticket id + `claim_epoch`)** so the daemon can reconcile work done
  during the outage (via `claim_epoch` + `head_sha`/`diff_hash`). Identity is a plain session-id — no
  crypto handshake (the `reconnect_hash` is dropped; fencing is the epoch, §4/§7).
- **Transport abstraction** — one small seam picks AF_UNIX (Linux/mac) or AF_INET on 127.0.0.1
  (Windows). The rest of the code never sees the difference. Socket + DB live under
  `$XDG_RUNTIME_DIR/obol/<project>/` or `~/.obol/<project>/`, never `/run`.
- **Lifecycle** — `obold` **spawns on first use as a subprocess** (no systemd requirement). Optional
  auto-start units (systemd user unit / launchd / Windows `nssm`) are documented, not required. An
  `obol uninstall` cleanup path stops the daemon and removes the db + socket (Portability).
- **Greppability preserved** — the daemon periodically exports a read-only **`.obol/issues.jsonl`
  mirror** (export, NOT source of truth — the beads pattern) so `ls`/`grep`/incident-response still
  work now that the file-marker plane is gone; `obol status` and `obol dump` read the live store.
- **The file-marker plane is RETIRED.** `state/{claims,submitted,done}/` markers,
  `smart-routing.json`-as-runtime, and `validate_board.sh`-as-separate-pass all go away. Their
  jobs move *inside* the store (see §3, §4, §7); grep survives via the jsonl mirror above.
- **`waves/*.json` is DEMOTED** to a human-editable **import format**, not runtime state (see
  Portability → import path).

### §2 — Tickets = issues with a live blocker graph

Adopt beads' *model*: issues are first-class records; dependencies are edges; IDs are hash-based
(merge-collision-free across branches — two people creating a ticket on two branches never collide).
**Per operator ruling, the `project` column is gone from every table** — this daemon serves exactly
one project (its config names it), so there is no tenant key to thread through PKs, indexes, or WHERE
clauses, and no cross-tenant honor-system hole.

```sql
-- Schema v2.  All timestamps ISO-8601 UTC text.  All list columns are JSON text.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS issues (
    id           TEXT PRIMARY KEY,             -- hash-based, e.g. "ix-<sha1(title+nonce)[:10]>"
    kind         TEXT NOT NULL DEFAULT 'task', -- 'task' | 'checkpoint'  (checkpoint = barrier node, see §7)
    title        TEXT NOT NULL,
    body         TEXT DEFAULT '',              -- the work-spec / description
    owns         TEXT NOT NULL DEFAULT '[]',   -- JSON array of decidable owns entries (prefixes/paths/segment-globs, §7)
    owns_verified_by_hand INTEGER NOT NULL DEFAULT 0,  -- human escape hatch for a genuinely ambiguous owns set
    tier         TEXT NOT NULL,                -- "frontier" | "strong" | "economy" (project-configurable)
    status       TEXT NOT NULL DEFAULT 'ready',-- ready | in_progress | blocked | in_review | done | abandoned
    assignee     TEXT,                         -- session_id holding the claim, NULL if unclaimed
    claim_epoch  INTEGER NOT NULL DEFAULT 0,   -- FENCE: incremented on every claim; guards all later transitions (§5 fix)
    release_mode TEXT NOT NULL DEFAULT 'auto', -- checkpoint only: 'auto' (release when wave done+green) | 'manual'
    created_at   TEXT NOT NULL,
    claimed_at   TEXT,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_issues_ready ON issues (status, tier);

CREATE TABLE IF NOT EXISTS edges (
    issue_id     TEXT NOT NULL,                -- the dependent (blocked) ticket
    blocked_by   TEXT NOT NULL,                -- the blocker; issue_id is not ready until blocked_by is done
    real_dep     TEXT DEFAULT '',              -- "real-dep: <why>" — required for a disjoint-owns edge UNLESS blocked_by is a checkpoint
    PRIMARY KEY (issue_id, blocked_by),
    FOREIGN KEY (issue_id)   REFERENCES issues (id) ON DELETE CASCADE,
    FOREIGN KEY (blocked_by) REFERENCES issues (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,             -- plain identity (display name); no crypto (reconnect_hash dropped)
    tier         TEXT NOT NULL,                -- the session's ceiling; it may claim at-or-below this tier
    status       TEXT NOT NULL DEFAULT 'idle', -- idle | working | in_review | disconnected
    busy         TEXT DEFAULT '',              -- "" | "subagent" | free text; extends liveness TTL when set
    busy_since   TEXT,                          -- when busy was set; drives the max-busy ceiling (§7)
    last_seen    TEXT NOT NULL,                -- heartbeat (refreshed on any poll/claim/update)
    head_sha     TEXT DEFAULT '',              -- physics signal: git HEAD at last report (READ by the lie-check, §7)
    diff_hash    TEXT DEFAULT '',              -- physics signal: hash of uncommitted diff (READ by the lie-check)
    connected    INTEGER NOT NULL DEFAULT 1    -- live socket y/n (durable session survives disconnect)
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      TEXT,                         -- ticket this message concerns (nullable for session-to-session)
    to_session   TEXT NOT NULL,                -- recipient display name
    from_session TEXT NOT NULL,
    mtype        TEXT NOT NULL,                -- one of the 9 typed-nudge types (see §5)
    payload      TEXT NOT NULL DEFAULT '{}',   -- JSON, machine-readable, ~15-40 tokens
    correlation_id TEXT,                       -- links request→reply (review-request→review-verdict)
    created_at   TEXT NOT NULL,
    delivered_at TEXT,                         -- in-flight stamp set by poll(); NOT a clear — redeliver after visibility TTL
    acked_at     TEXT                          -- set by ack(); a message is DONE only when acked (at-least-once, §5)
);
CREATE INDEX IF NOT EXISTS ix_msg_inbox ON messages (to_session, acked_at, delivered_at);

CREATE TABLE IF NOT EXISTS votes (
    correlation_id TEXT NOT NULL,              -- the review-request being voted on
    task_id        TEXT NOT NULL,
    reviewer       TEXT NOT NULL,              -- session_id of the panel member (a DISTINCT lens, §6)
    lens           TEXT DEFAULT '',            -- the review lens this seat covers (keeps the panel diverse, not cloned)
    verdict        TEXT,                       -- APPROVE | CONCERN | REJECT | BUSY | NULL(pending)
    finding        TEXT DEFAULT '',            -- required non-empty when verdict = REJECT
    voted_at       TEXT,
    PRIMARY KEY (correlation_id, reviewer)
);
```

### §3 — Derived readiness (the query that replaces the wave manifest)

`ready` is **not a stored flag** — it is the answer to a query. A **task** ticket is claimable iff:

1. its `status = 'ready'` and `kind = 'task'` (checkpoints are barriers, never claimed as work), AND
2. it has **no open blocker edge** (every `blocked_by` is `done`), AND
3. its `owns[]` is **provably disjoint** from every `in_progress` ticket's `owns[]`.

Rules 1–2 are pure SQL; rule 3 is a Python post-filter over the small candidate set — and its
correctness is the whole point of blocker-fix #2. The v1 check used `fnmatch(path, pattern)`, which
answers "does this *path* match this *pattern*"; it **cannot** decide whether two *patterns* intersect
(`src/router/*.py` vs `src/*/handler.py` both return False → falsely "disjoint" → both claim the
concrete file). So v2 redefines the ownership vocabulary to be **decidably checkable**:

- an `owns[]` entry is a **directory prefix** (`src/router/`), a **concrete path** (`src/api.py`), or
  a **single-segment glob** (`src/router/*.py`) where the glob **never crosses `/`** — it matches
  within one path segment only.
- overlap is decided **segment by segment** (`fnmatchcase` per segment, `*` eats no `/`), with a
  documented **case-explicit** policy (`fnmatchcase`, case-sensitive by default; set
  `owns.case_insensitive` in config for case-folding filesystems).
- **Conservative policy: if disjointness cannot be PROVEN, treat as CONFLICT** (serialize) — never
  assume-disjoint. This is the safe direction: a false conflict costs a little concurrency; a false
  "disjoint" corrupts two worktrees.
- **Human escape hatch:** a ticket carrying `owns_verified_by_hand = 1` overrides the conservative
  verdict for a genuinely ambiguous case (mirrors the rig's advisory + human backstop).

```sql
-- Candidate set: status=ready, kind=task, no unfinished blocker, at-or-below the caller's tier.
-- (:caller_rank and the tier_rank() map are bound by the daemon from project config.)
SELECT i.id, i.owns, i.owns_verified_by_hand, i.tier
FROM   issues i
WHERE  i.status = 'ready' AND i.kind = 'task'
  AND  :caller_rank >= tier_rank(i.tier)          -- caller may take at-or-below its own tier
  AND  NOT EXISTS (
         SELECT 1 FROM edges e
         JOIN   issues b ON b.id = e.blocked_by
         WHERE  e.issue_id = i.id AND b.status <> 'done'
       )
ORDER BY tier_rank(i.tier) DESC,                  -- prefer own-tier (highest rank) first
         i.created_at ASC;                        -- then FIFO
```

```python
def owns_overlap(a_entries, b_entries):
    """CONSERVATIVE, DECIDABLE overlap. Returns True unless provably disjoint.
    Each entry normalizes to a list of segments; a glob segment matches per-segment only."""
    for a in a_entries:
        for b in b_entries:
            if _prefixes_can_collide(a, b):        # prefix/path/segment-glob intersection, * never eats '/'
                return True                        # unproven-disjoint counts as overlap
    return False

def ready_set(conn, caller_rank, config):
    """Rule 3 — hide any candidate not provably disjoint from an in_progress ticket's owns[]."""
    locked = []
    for (owns_json,) in conn.execute(
        "SELECT owns FROM issues WHERE status='in_progress'"):
        locked.extend(json.loads(owns_json))

    out = []
    for id_, owns_json, verified, tier in conn.execute(CANDIDATE_SQL, {...}):
        owns = json.loads(owns_json)
        if verified or not owns_overlap(owns, locked):
            out.append((id_, owns, tier))
    return out
```

This single derivation is what makes **work-stealing, reassignment, and "finished early → give me
work"** fall out for free — no hand-authored wave manifest, no `smart-routing.json`. **This is the
mechanized WCI** (work-composition-intelligence): no redundancy (each glob region owned once), no
contradiction (blocked_by graph respected), max concurrency (every non-overlapping ready ticket is
claimable simultaneously).

### §4 — Atomic claim (one transaction replaces flock + validate_board.sh)

**One asyncio daemon is the sole writer** (blocker-fix #4), so there is never a second process racing
this transaction — the concurrency is *N socket clients funnelling into one loop*, not N writers. That
lets the write section stay tiny: compute the ready-set + segment-glob scan **in memory on a read
snapshot** (§3), then do **ONE fast guarded UPDATE** whose `rowcount` decides the winner.

Two idiom fixes make the write correct and portable:
- **`won = (cur.rowcount == 1)`, NOT `conn.total_changes`** (blocker-fix #1). `total_changes` is
  cumulative for the life of the connection and never resets, so after the first successful claim it
  is always truthy → every subsequent loop iteration falsely "wins" → double-claims. `cursor.rowcount`
  is per-statement and is exactly 1 iff *this* UPDATE flipped the row.
- **`isolation_level=None` (autocommit) + explicit `BEGIN IMMEDIATE`/`COMMIT`** (blocker-fix #4). The
  `with conn:` + manual-`BEGIN` idiom is CPython-version-dependent and may not actually take the write
  lock up front. `BEGIN IMMEDIATE` on an autocommit connection reserves the writer deterministically;
  `PRAGMA busy_timeout` is the belt-and-suspenders backstop.

```python
# connection opened once by the daemon:  sqlite3.connect(db, isolation_level=None)
#   conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA busy_timeout=5000")

def claim_next(conn, session, caller_rank, config, patience_left, _pause=lambda: None):
    conn.execute("BEGIN IMMEDIATE")                     # deterministic write lock (autocommit conn)
    try:
        min_rank = caller_rank if patience_left > 0 else 0    # own-tier patience
        cands = ready_set(conn, caller_rank, config)          # read snapshot inside the txn
        for id_, owns, tier in cands:
            if tier_rank(tier) < min_rank:
                continue
            _pause()                                    # TEST SEAM: widen the read→UPDATE TOCTOU window
            cur = conn.execute(
                "UPDATE issues SET status='in_progress', assignee=?, "
                "  claim_epoch=claim_epoch+1, claimed_at=?, updated_at=? "
                "WHERE id=? AND status='ready'",         # status guard = optimistic lock
                (session, now(), now(), id_))
            won = (cur.rowcount == 1)                    # per-statement, NOT total_changes
            if won:
                epoch = conn.execute("SELECT claim_epoch FROM issues WHERE id=?", (id_,)).fetchone()[0]
                conn.execute("COMMIT")
                return {"id": id_, "claim_epoch": epoch}  # session records the fence for later guards
        conn.execute("COMMIT")
        return None                                     # nothing claimable → caller sleeps/patiences
    except BaseException:
        conn.execute("ROLLBACK")
        raise
```

- **`claim_epoch` is the fence** (blocker-fix #5). Every claim increments it; the caller records the
  returned epoch and stamps it on every later transition (`in_review`/`done`/`release`/heartbeat),
  which all guard `assignee=self AND claim_epoch=my_epoch`. A session that was reaped and revived
  fails the guard and is told to abandon — so a slow-but-live session can never collide with its
  replacement.
- **Down-tier stealing** — a `frontier` session with only `economy` work available claims it (drains
  strong/economy so the queue never stalls). Governed by `caller_rank >= tier_rank(ticket)`.
- **`--patience C`** — a session tries its *own* tier for `C` cycles before it steals down. Prevents a
  frontier session greedily draining cheap work a cheap session could do.
- **One gate.** The `status='ready'` guard + `rowcount` is the optimistic lock; `BEGIN IMMEDIATE`
  serializes the (single) writer. This one transaction does what `flock` + a separate
  `validate_board.sh` pass used to do in two places.

### §5 — Typed-nudge inbox (KEEP — best-in-class, unchanged in spirit)

One `messages` table keyed by `task_id`. **Poll, don't push.** `poll(session)` returns pending
messages AND refreshes liveness in one call.

**v1 was at-most-once and lost nudges** (blocker-fix #3): `poll()` stamped `read_at` and committed
*before* the bytes reached the session, so a crash/drop after the commit silently ate the message —
and a dropped `review-request` wedges a ticket in `in_review` forever. v2 uses **explicit ack** with a
visibility timeout, giving **at-least-once** delivery:

- `poll()` stamps `delivered_at` (in-flight) and does **NOT** clear the message. It returns messages
  that are unacked AND either never delivered or delivered longer ago than the **visibility timeout**.
- The caller does the work, then calls **`ack(message_ids)`**, which stamps `acked_at`. Only an acked
  message is done.
- A message delivered but not acked within the visibility timeout is **redelivered** on the next poll
  (the consumer crashed before acting). Because redelivery is possible, **idempotency is the caller's
  job** — a replayed nudge is the caller's to dedupe (e.g. via `correlation_id`); the store guarantees
  at-least-once, not exactly-once on the payload.
- **9 machine-readable message types**, ~15–40 tokens each:
  `review-request, review-verdict, scope-proposal, scope-response, handoff, collision-warning,
  block-notification, ping, pong`.
- **Poll cadence tuned to task duration.** Seconds-latency is fine (tasks run minutes); no push
  channel needed.

```python
def poll(conn, session, now_fn=now, visibility_s=120):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE sessions SET last_seen=? WHERE session_id=?", (now_fn(), session))
    # deliver: unacked AND (never delivered OR past the visibility timeout → redeliver)
    rows = conn.execute(
        "SELECT id, from_session, mtype, payload, correlation_id "
        "FROM messages "
        "WHERE to_session=? AND acked_at IS NULL "
        "  AND (delivered_at IS NULL OR delivered_at < ?) "
        "ORDER BY id ASC",
        (session, iso(now_fn() - visibility_s))).fetchall()
    ids = [r[0] for r in rows]
    if ids:
        conn.executemany("UPDATE messages SET delivered_at=? WHERE id=?",
                         [(now_fn(), i) for i in ids])      # in-flight stamp, NOT a clear
    conn.execute("COMMIT")
    return rows

def ack(conn, session, message_ids):
    """Caller calls this AFTER acting on the messages → the only thing that retires them."""
    conn.execute("BEGIN IMMEDIATE")
    conn.executemany("UPDATE messages SET acked_at=? WHERE id=? AND to_session=?",
                     [(now(), i, session) for i in message_ids])
    conn.execute("COMMIT")
```

### §6 — Consensus / adversarial review as a required transition (KEEP)

A ticket cannot move `in_review → done` without quorum. A `review-request` names a reviewer panel;
each verdict is `APPROVE | CONCERN | REJECT-with-finding`. **The daemon mechanizes the quorum** — it
knows the expected reviewer count and posts the consensus verdict automatically once enough votes
land.

**The panel is diverse-lens, not N clones** (operator ruling). Adversarial-review-to-consensus stays
a hard requirement, but each seat covers a **distinct review lens** (or an actual distinct peer
session) — recorded in `votes.lens` — rather than N identical model clones that mostly agree and waste
calls (exactly the shape of the 4-lens DTC that produced *this* revision). The cheap quorum
vote-tracking below is unchanged. Identity across a reconnect is a plain session-id; there is no
`reconnect_hash` crypto proof (no threat model on a loopback socket) — fencing is the `claim_epoch`.

Quorum table:

| Condition | Result |
|---|---|
| 2 × APPROVE | proceed (ticket → done) |
| any REJECT + non-empty finding | blocked (ticket → blocked, finding attached) |
| CONCERN (no REJECT) | proceed-with-notes |
| N reviewers return BUSY | **Skip-after-N-BUSY** — drop that reviewer, re-quorum on the rest |
| autonomous mode, panel can't reach quorum | **judge-panel fallback** binds |
| operator override | **always binding + logged** (supersedes any machine verdict) |

```python
def record_vote(conn, cid, task_id, reviewer, verdict, finding, expected_n):
    if verdict == "REJECT" and not finding:
        raise ValueError("REJECT requires a finding")
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE votes SET verdict=?, finding=?, voted_at=? "
                 "WHERE correlation_id=? AND reviewer=?",
                 (verdict, finding, now(), cid, reviewer))
    cast = conn.execute("SELECT verdict FROM votes WHERE correlation_id=? "
                        "AND verdict IS NOT NULL", (cid,)).fetchall()
    v = [r[0] for r in cast]
    live = [x for x in v if x != "BUSY"]          # Skip-after-N-BUSY: BUSY doesn't count
    if any(x == "REJECT" for x in live):
        out = _resolve(conn, task_id, "blocked")
    elif live.count("APPROVE") >= 2:
        out = _resolve(conn, task_id, "done", "with-notes" if "CONCERN" in live else "clean")
    elif len(v) >= expected_n:                     # everyone voted, no 2×APPROVE
        out = _resolve(conn, task_id, "needs-judge")   # → judge-panel fallback if autonomous
    else:
        out = "pending"
    conn.execute("COMMIT")
    return out
```

### §7 — Collision prevention (one machine-checked contract, one enforcement point)

`owns[]` **disjoint-file ownership** is the single source of truth for who may touch what, decided by
the **conservative, decidable segment-aware check** of §3 (blocker-fix #2). It **wins over anything the
work-spec prose implies**, and is enforced in **exactly one place** — the claim transaction's overlap
check (§4) — instead of the three places the file/flock plane spread it across.

Plus **per-session git worktree** off fresh `origin/master` (`worktree_root` from project config),
so two sessions never share a working tree even when their owns are disjoint.

**Fencing so the reaper can't re-introduce a collision** (blocker-fix #5). In v1 a live-but-slow
session could be reaped, its ticket returned to `ready`, and a second session claim it → two worktrees
on the same files — the exact collision `owns[]` exists to prevent. v2 fences every transition with
the monotonic `claim_epoch`:

```python
def guarded_transition(conn, id_, session, my_epoch, **cols):
    """in_review / done / release / ownership-heartbeat all go through here."""
    conn.execute("BEGIN IMMEDIATE")
    sets = ", ".join(f"{k}=?" for k in cols)
    cur = conn.execute(
        f"UPDATE issues SET {sets}, updated_at=? WHERE id=? "
        f"AND assignee=? AND claim_epoch=?",           # FENCE: self AND my epoch
        (*cols.values(), now(), id_, session, my_epoch))
    conn.execute("COMMIT")
    if cur.rowcount != 1:
        raise Fenced("reaped-and-revived: abandon this ticket")   # a revived session loses the guard
```

- A reaped-then-revived session fails the fence and is told to **abandon** — its replacement is the
  sole owner.
- **Max-busy ceiling** — `busy = 'subagent'` extends a session's liveness TTL, but v1 let a crashed
  session set `busy` and be exempt from reaping *forever*. v2 caps it: past `max_busy_s` (from
  `busy_since`) the ceiling is hit and the session is reaped regardless of `busy`.

**Physics lie-detection is now READ, not just stored** (smaller note). The reaper/health check compares
each working session's reported `head_sha` + `diff_hash` against the previous report: a session that
claims progress while **both** are unchanged since last heartbeat is **flagged** (stalled or lying),
surfaced in `obol status`, and eligible for reap. v1 stored these columns but never consulted them.

**Checkpoint / barrier primitive** (operator ruling). A `kind='checkpoint'` issue is a milestone node
that downstream tickets may `blocked_by` **without** a fabricated `real-dep:` marker — the disjoint-owns
dep validator explicitly allows a dep *onto* a checkpoint (a checkpoint owns nothing, so the
"disjoint-owns edge needs justification" rule doesn't apply). It is a barrier, never claimed as work
(§3 rule 1). Release semantics:
- **`release_mode='auto'` (default)** — the daemon releases the checkpoint (marks it `done`) the moment
  its upstream wave is all-`done` **and** the gate is green. It never blocks the operator.
- **`release_mode='manual'`** — opt-in, for when a human *does* want to eyeball the milestone; the
  operator issues `obol release <checkpoint-id>`. **Not the default** — no forced manual eyeball.

**Preserve "disjoint owns ≠ no dependency":** a `blocked_by` edge between two **task** tickets whose
`owns[]` do NOT overlap is suspicious (why would disjoint work block?) — it requires a `real-dep:
<why>` marker, or **the import validator rejects it** (Testing → import). This catches false blocking
(invented dependency that needlessly serializes) while still admitting a legitimate cross-cutting
dependency (e.g. a regression-guard test that is a genuine build prereq). Edges onto a checkpoint are
exempt.

### §8 — Cost/context wins to PRESERVE explicitly

- **Idle session = a sleeping bash shell burning ZERO model tokens.** The model process is spawned
  only at `claim`. This is the pooling win; the store must never require a warm model to hold a slot.
- **Ephemeral-per-ticket** — one session claims one ticket, does it, exits. Bounded context, no
  drift, no stale plan carried across tickets.
- **Structured typed messages** — a full review cycle is ~500–1000 tokens of typed payloads vs
  5–10k tokens of prose back-and-forth.
- **State is DERIVED from the store, never narrated.** No session writes a paragraph describing the
  board; it queries the board. Readiness, ownership, and quorum are computed, not prose-summarized.

### §9 — Bootstrap collapse

Replace the **5-document read-tax** with one `obol prime` command that prints, in a few hundred
tokens: the caller's **ready-set** (from §3), its claim, its unread nudges, and the **standing
orders** (the small set of invariant rules). Modeled on beads' `bd prime`. A session goes from
cold-start to first useful action after reading *one* short output, not five long docs.

```
$ obol prime --session yoda        # daemon is per-project; the project is implicit in its config
STANDING ORDERS: disjoint-owns is law · REJECT needs a finding · never narrate state · steal down when idle
YOUR TIER: frontier (may claim frontier|strong|economy)
YOUR CLAIM: none
READY (3): ATC-021 [strong owns=src/router/] · ATC-024 [economy owns=docs/*.md] · ATC-025 [strong owns=src/spend/]
INBOX (1): review-request from mace-windu on ATC-019 (cid=r-8f2a)  [ack after acting]
NEXT: `obol claim --session yoda`  or  `obol poll --session yoda`
```

---

## Portability & Deployment (first-class — deploy to ALL projects)

The whole point: **one reusable component, deployed to any project.** Charon first, SLOP/mediastack
second, future products later.

### Packaging
- A **standalone stdlib-python package** (min-Python 3.9), installable via `pipx install obol` /
  `uvx obol`, OR vendorable (copy `obol/` into a repo — it's stdlib, so it just runs).
- One CLI: `obol init | prime | claim | poll | ack | nudge | vote | release | import | status | dump | test | uninstall`.
- The daemon (`obold`) **starts on first use as a subprocess** (no systemd requirement); the CLI
  subcommands are thin clients that speak JSON-RPC via `proxy.py` (with reconnect-with-backoff).

### One daemon PER PROJECT (operator ruling)
- **Deploy-time stands up one `obold` for that project.** Its config names the single project it
  serves, so there is **no `project` key** in the schema, no cross-tenant WHERE-scoping, and no
  honor-system isolation hole (a whole class of v1 bug and its test are simply deleted). More
  processes, simpler mental model, real OS-level isolation between projects.
- Socket + DB live under `$XDG_RUNTIME_DIR/obol/<project>/` (fallback `~/.obol/<project>/`) —
  **never `/run`**. Transport is AF_UNIX on Linux/mac, AF_INET on 127.0.0.1 on Windows, chosen by the
  transport seam (§1).

### Per-project config (JSON — stdlib read+write, no `tomllib`)

```json
// .obol/config.json  (committed to each project repo; read AND written with stdlib json)
{
  "project": "charon",
  "worktree_root": "~/.obol/worktrees/charon",
  "autonomy": "gated",              // gated | autonomous (judge-panel binds when autonomous)
  "review_quorum": 2,               // APPROVEs required to proceed
  "visibility_timeout_s": 120,      // inbox redelivery window (§5)
  "max_busy_s": 1800,               // busy-ceiling before a 'busy' session is reaped anyway (§7)
  "tiers": { "frontier": 3, "strong": 2, "economy": 1 },
  "tier_aliases": { "opus": "frontier", "sonnet": "strong", "haiku": "economy" },
  "owns": { "case_insensitive": false }   // segment-aware, decidable owns (§3); case policy explicit
}
```

### Hand-rolled stdlib validator (no Pydantic)
`obol import` runs a small specified validator — no third-party dep:

```python
def validate_ticket(t):                        # returns [] on success, else list of error strings
    errs = []
    for f in ("id", "title", "tier"):          # required fields
        if not isinstance(t.get(f), str) or not t[f]:
            errs.append(f"{f}: required non-empty string")
    if t.get("kind", "task") not in ("task", "checkpoint"):
        errs.append("kind: must be 'task' or 'checkpoint'")
    owns = t.get("owns", [])                    # owns-shape: list of decidable entries
    if not isinstance(owns, list) or not all(isinstance(x, str) for x in owns):
        errs.append("owns: must be a list of strings")
    else:
        errs += _check_owns_shape(owns)         # prefix/path/single-segment-glob only; no '**', no mid-path '*'
    for e in t.get("blocked_by", []):           # dep-justification (checked graph-wide at import too)
        pass
    return errs
```

### Import path (waves become an import format, not runtime state)
`obol import waves/*.json` (or a `tickets/` dir) populates the issue graph and **runs the validator**.
The whole import is **one transaction — partial failure rolls back entirely** (nothing written).
Hard failures:
- **owns-collision** — two tickets whose owns are not provably disjoint (conservative check, §3).
- **duplicate-owns redundancy** — two tickets with identical owns (one is redundant).
- **false-blocking-dep** — a `blocked_by` edge between disjoint-owns **task** tickets with **no**
  `real-dep:` marker. Edges onto a `checkpoint` node are exempt (that's the whole point of §7's
  barrier primitive).
- **bad owns-shape** — an entry that isn't a prefix / concrete path / single-segment glob.
- **missing Dependencies & Sequence section** — a ticket spec lacking the required D&S block.

### Lifecycle & uninstall
- `obold` spawns on first use; optional auto-start is documented (systemd **user** unit, launchd
  `plist`, or Windows `nssm`) but **never required**.
- `obol uninstall` stops the daemon and removes the db + socket + `.obol/issues.jsonl` mirror for that
  project — a clean teardown a pipx user can run.

### Walkthrough — deploy to SLOP/mediastack
```
cd ~/code/mediastack
pipx install obol                       # or vendor obol/ into the repo
obol init                               # writes .obol/config.json (project="mediastack")
# edit tiers/owns-case-policy if mediastack differs
obol import tracking/tickets/*.json     # imports the 31 open SLOP tickets, runs the validator
obol prime --session <name>             # first use spawns this project's obold subprocess
# mediastack gets its OWN daemon; charon's daemon/db/socket are a separate process entirely.
```

### Walkthrough — deploy to a brand-new product
```
cd ~/code/newthing
pipx install obol
obol init --project newthing --tiers frontier,strong,economy
$EDITOR .obol/config.json               # set worktree_root, autonomy, quorum
# author waves/ or tickets/ as JSON (or hand-write issues via `obol new`)
obol import waves/*.json
obol prime --session <name>             # spawns newthing's own obold on first use
```
No database server, no rig files copied, no systemd requirement — the product ships with `obol` and
nothing from the home build-infra leaks in. `obol uninstall` tears it all down.

---

## Migration (two planes → one store, incremental + reversible)

Each phase is independently shippable and abortable; none destroys data the previous plane needs.

- **Phase 0 — stand up alongside.** Deploy `obold` + schema + `obol import`. Import current
  `waves/*.json` into the store. **Both planes coexist**; the store is read-only advisory. Abort =
  stop the daemon; nothing changed.
- **Phase 1 — cut claim/poll to the store.** Sessions claim via `claim_next` and poll via `poll`.
  **Retire the `state/{claims,submitted,done}/` file markers.** The store is now authoritative for
  claims and messages. Abort = repoint sessions at the file markers (still present as a mirror during
  this phase).
- **Phase 2 — retire waves-as-runtime + the separate collision pass.** `waves/*.json` becomes
  import-only; **retire `validate_board.sh` as a separate pass** (its check now lives in the claim
  transaction §4 + the import validator §7). Abort = re-enable the standalone pass.
- **Phase 3 — `prime` replaces the 5-doc bootstrap.** Sessions start with `obol prime` only. Abort =
  restore the 5-doc START-SESSION flow.

**Retire the 4 stale `server.py` instances** (per BRIDGE-DAEMON-PROPOSAL) as part of Phase 1 — they
are the old messaging plane; the daemon subsumes them.

---

## Testing (hermetic, no-network, deterministic — like the droid-harness's 10 hermetic tests)

The v1 suite couldn't catch bugs 1–5: it allowed `:memory:` (which can't do real WAL), never forced
the races, and never verified the guards were load-bearing. **v2 makes the tests force the failures.**
Everything runs against a **real temp-file SQLite DB in WAL mode**, driven by **concurrent socket
clients against the one daemon** (never `:memory:`/shared-cache). A fake clock is injected via a
`now()` seam and the **id-nonce / reconnect random is seeded** so ID/TTL/reconnect tests are
deterministic. No network, no sleeps-for-timing. Runner: `obol test` → a `pytest` hermetic suite, and
**this hermetic suite is the CI gate**.

### Concurrency / race (forced, with mutation checks)
- **Exactly-once claim (forced TOCTOU)** — N socket clients aligned on a `threading.Barrier` all call
  `claim_next` against M<N ready non-overlapping tickets, with the **injectable `_pause()` hook fired
  between the ready-set read and the UPDATE** to widen the window. Assert: each ticket has exactly one
  assignee, none double-claimed, none lost, N−M callers get `None`.
- **Mutation check (the guard is load-bearing)** — re-run the above with the `status='ready'` UPDATE
  guard removed **and** with `rowcount` swapped back to `total_changes`; assert the test now **FAILS
  (double-claims appear)**. This is what proves the guard actually prevents bug #1.
- **Overlapping-owns rejection** — two ready tickets with owns that are not provably disjoint, two
  barrier-aligned claimers; assert exactly one wins (in-transaction overlap check, not just the
  pre-read filter).
- **Segment-glob decidability + negative controls** — `src/router/*.py` vs `src/*/handler.py` →
  **CONFLICT** (unproven-disjoint); `src/router/` vs `src/spend/` and `a/b.py` vs `a/c.py` →
  **disjoint, NOT flagged** (the negative controls v1 lacked); `owns_verified_by_hand=1` overrides a
  conservative conflict.

### Readiness derivation
- **Blocker-graph fixtures** (chain, diamond, fan-out) — `ready_set` equals the hand-computed set.
- **Blocker completion flips dependent** — mark a blocker `done` → its dependent becomes ready.
- **In_progress hides overlap** — an `in_progress` ticket's owns hide an overlapping ready ticket.
- **Checkpoint is never claimed** — a `kind='checkpoint'` node never appears in a `ready_set`.

### Down-tier stealing + patience
- **Steal down** — a `frontier` session, only `economy` work → claims the economy ticket.
- **Patience holds** — with `--patience C`, own-tier work appearing within C cycles is taken;
  otherwise it steals on cycle C+1 (advance the injected cycle counter).

### Inbox (at-least-once, explicit ack)
- **Deliver-then-ack** — send → poll delivers once and stamps `delivered_at`; `ack` retires it; a
  later poll returns nothing.
- **Crash-before-ack redelivers** — poll (delivers) but never ack; advance the clock past
  `visibility_timeout_s` → next poll **redelivers** the message (proves the wedged-`in_review` bug is
  gone). Assert caller-side idempotency on the replay.
- **Poll refreshes liveness** — `last_seen` advances on poll.
- **Ordering + restart durability** — delivered in `id` order; unacked messages survive a daemon
  restart.

### Consensus (diverse-lens)
- `2×APPROVE → done`; `REJECT + finding → blocked` (empty finding **raises** at record time).
- **Skip-after-N-BUSY** — BUSY reviewers dropped, quorum recomputed on the rest.
- **Judge-panel fallback** — autonomous mode, no quorum → judge verdict binds.
- **Operator override wins** — supersedes a machine `done`/`blocked` and is logged.
- **Distinct lenses recorded** — each seat carries a distinct `votes.lens` (panel is diverse, not
  cloned).

### Liveness / recovery / fencing
- **Stale-session purge at TTL** — advance past TTL with no poll → session purged, claim → `ready`.
- **`busy` extends TTL, but the ceiling reaps** — `busy='subagent'` survives the base TTL; past
  `max_busy_s` it is reaped anyway (**wedged-busy ceiling**).
- **Reaped-then-revived fails the fence** — reap a claim, let another session take it (epoch++), then
  the original session tries a `guarded_transition` with its stale epoch → **raises `Fenced` / abandons**
  (proves bug #5 is closed).
- **Socket-disconnect-mid-claim** — kill a client's socket mid-claim; the orphaned claim is reconciled
  by epoch/TTL, no double-owner.
- **Daemon-kill-mid-transaction** — SIGKILL `obold` during a claim write; on restart the DB is
  all-or-nothing (the half-claim either fully landed or fully rolled back — WAL atomicity).
- **Lie-detection flags a liar** — a working session reports progress with **unchanged** `head_sha`
  AND `diff_hash` across two heartbeats → flagged in `obol status`.
- **Clock-moved-backward TTL** — `now()` jumps backward → TTL math doesn't underflow/false-reap.
- **Reconnect reconcile** — a session reconnects (seeded nonce) re-announcing id + claim + epoch; the
  daemon reconciles without a crypto handshake.

### Import / validator (each HARD-FAILs; whole import is one transaction)
- **owns-collision**, **duplicate-owns redundancy**, **bad owns-shape** → import aborts.
- **false-blocking-dep** — disjoint-owns task edge, no `real-dep:` → aborts; same edge *with* a valid
  `real-dep:` → succeeds (positive control); an edge **onto a checkpoint** with no marker → succeeds
  (exempt).
- **missing Dependencies & Sequence** → aborts.
- **partial-import rollback** — a batch where ticket 7 of 10 is invalid → **nothing** is written.

### Migration reversibility + coexistence
- For each phase (0→1→2→3), run forward, assert consistency, run the documented rollback, assert **no
  data loss** (claims, messages, votes, issue graph survive a round-trip).
- **Cross-plane double-claim during coexistence** — in the Phase-1 window where the file markers still
  mirror the store, assert a ticket cannot be claimed once in each plane (the store is authoritative;
  the mirror is one-way).

### CI wiring + dogfood
- **`obol test` (this hermetic suite) is the CI gate** — it runs on every push, needs no runner
  secrets, and falls back to hosted per the CI-runner pattern. Green here is required to merge.
- **Dogfood is a demo, NOT the gate.** "`obol` orchestrates its own build" (then a Charon tier) is a
  compelling proof of the subtraction, run with an **explicit pass/fail acceptance criterion**, but it
  is a demonstration — the hermetic suite above is what blocks the merge.

---

## Open decisions (operator-owned — flagged, not silently decided)

**Closed by the v2 DTC pass** (recorded for the audit trail):
- ~~One daemon per machine vs per project~~ → **CLOSED: one per project** (operator ruling; `project`
  column removed).
- ~~Config format~~ → **CLOSED: JSON** (`.obol/config.json`; no `tomllib` floor, stdlib writer).
- ~~Validation dependency~~ → **CLOSED: hand-rolled stdlib validator** (no Pydantic; core stays
  zero-dep).

**Still operator-owned:**
1. **Tool name.** Proposed `obol` (the coin paid to Charon — small, portable unit). Alternatives:
   **`ferry`** (what Charon does) or **`skiff`** (small boat, small footprint). The name touches CLI,
   package, socket path, config dir.
2. **Autonomy defaults.** Proposed default `gated` (operator confirms transitions; judge-panel only
   binds when `autonomous`). Alternative: default `autonomous` with operator-override-always. Ties
   into the review §6 fallback binding.
3. **ID scheme detail.** Proposed hash-based `ix-<sha1[:10]>` over `title+nonce` (project dropped from
   the hash inputs now that the daemon is single-project). Open: content-addressing on body vs nonce,
   and collision-length. Affects merge-collision-freedom.

**NEW open decisions the v2 fixes introduce:**
4. **Inbox visibility timeout + busy ceiling defaults.** `visibility_timeout_s=120` and
   `max_busy_s=1800` are guesses. Too-short redelivers mid-work (duplicate action pressure on the
   caller's idempotency); too-long wedges a genuinely dropped nudge. Operator/tuning call.
5. **Windows loopback transport exposure.** AF_INET on 127.0.0.1 is reachable by **any local process /
   user** on that host, unlike an AF_UNIX socket with file permissions. Do we need a per-daemon token
   on the Windows path, or is "single-user dev box, loopback only" acceptable? (No crypto on the socket
   was an explicit v2 decision for identity/fencing — this is a *different*, transport-exposure
   question.)
6. **Checkpoint auto-release "gate-green" definition.** `release_mode='auto'` fires when the upstream
   wave is all-`done` **and** the gate is green — but what counts as the gate (CI status? a review
   quorum on the wave? both?) needs a concrete rule.
7. **`issues.jsonl` mirror cadence.** Periodic export interval (and whether it also fires on every
   state transition) trades incident-response freshness against write churn.
8. **Segment-glob vocabulary ceiling.** v2 deliberately forbids `**` and mid-path `*` to stay
   decidable. If a real ticket needs recursive ownership, do we add a decidable recursive-prefix form,
   or require splitting the ticket? (Deferring keeps the checker provably correct.)

---

## Phasing tied to ADR-0007 / 0008

- This document **is ADR-0008 Phase 1** — the stdlib reference design that graduates the home fleet
  rig into an in-tree, shippable work-engine. The fleet rig remains the *reference implementation*;
  this store is the *product-grade* re-expression of it (per "Charon owns the work-engine" — promote
  ADR-0007 D10's engine in-tree sooner).
- **ADR-0007 D10** (engine in-tree) is the parent decision; the WCI mechanization in §3–§4 is the
  concrete realization of "Charon work-composition intelligence" as a *derived* query rather than a
  hand-authored manifest (per "WCI: rig-enforced now, product deferred" — this store is where the
  product WCI becomes opt-in + advisory-override capable, because readiness is a query the operator
  can inspect and override).
- **Product-vs-build-rig boundary** is honored by §0 (stdlib-only) and the Portability section: the
  shippable `obol` carries **nothing** from `fleet/`, SLOP, or the runner; the home rig is the
  reference, not a dependency.

---

*End of plan (v2). Reviewers: re-verify the seven blocker-fixes and three rulings via the DTC
Resolution table up top, then spot-check §0 (zero-dep holds through the whole core), §3–§4 (decidable
overlap + `rowcount`/`BEGIN IMMEDIATE` atomic claim), §5 (explicit-ack at-least-once), §7 (epoch
fencing + checkpoint), and the Testing section's forced-race + mutation-check cases before
approving Phase 0.*
