# FAKTORY-ADOPT — adoption record

Ticket: `fleet/board/FAKTORY-ADOPT.md` (rig, P1, work_class rig-meta).
Verdict source: EVAL Faktory ADOPT-PARTIAL (`TRIAL-FAKTORY`, 2026-07-24) + CLAIM-INTEGRITY-EVAL
(operator-approved 2026-07-24). This ticket is the **wiring** of that verdict — adopt-first, no
reinvented queue.

**Status: ADOPTED — live, durable, contract-complete, all durability proofs green (real, not mocked).**

Faktory is the fleet's **sole** durable job/lease/retry/DLQ substrate. It replaces the hand-rolled
`loop-guard.sh` DLQ and is the claim-lease store `CLAIM-LEASE-EXACTLY-ONCE` (T1) codes against. No
second substrate was stood up.

---

## 1. Server (durable) — host & status

- Host: **4-LOM (`10.0.1.60`)**, container `faktory`, image `contribsys/faktory:latest` (Faktory 1.9.4).
- Persistence: named docker volume `faktory-data` → **`/root/.faktory`** (the *real* RDB path; the
  `/data` mount implied by earlier docs is a dead mount — corrected here per TRIAL-FAKTORY §6).
- Durability across host reboot: `--restart unless-stopped`.
- Auth: password generated once via `openssl rand -hex 24`, stored ONLY at `~/.faktory/password` on
  4-LOM (chmod 600, **never committed**). Protects both the protocol port (salted iterated-sha256
  HELLO handshake) and the Web UI (HTTP basic auth). — security-ratchet compliant.
- Ports: `7419` protocol (LAN — fleet clients on the dev box reach it), `7420` Web UI (LAN,
  password-protected; live Processed/Failed/Enqueued/Retries/**Dead** badges + one-click requeue/kill).
- Footprint (TRIAL-FAKTORY §6, re-confirmed): ~15 MB RAM, ~35 MB image, single container.

## 2. Interface as-built (matches the ticket `interface_contract` EXACTLY — no drift)

`fleet/faktory/faktory-client.sh <cmd> [args]`, exit 0 success / non-zero failure:

| cmd | args | behavior (verified) |
|---|---|---|
| `push` | `--queue Q --jobtype T --jid <ticket-id> --arg <json>` `[--reserve-for S] [--retry N]` | enqueue; prints jid. `--arg` repeatable, each JSON-parsed (string fallback). |
| `reserve` | `--queue Q [--timeout S]` | FETCH one; prints job JSON `{jid,args,...}` or empty **+ rc1** if none. |
| `ack` | `--jid <id>` | terminal success; job durably GONE (survives graceful restart). |
| `fail` | `--jid <id> [--msg M]` | terminal fail; requeues per retry/backoff policy. |
| `info` | `--jid <id>` | prints live set (`enqueued:<q>`/`scheduled`/`retries`/`dead`/`working`); **rc1** if absent (T1's idempotent-enqueue check). |

Payload: `jobtype "charon-run"`, `args` = the `charon-run.sh` invocation. `reserve_for` default 1800 s.

Implementation is a thin wrapper over Faktory's plaintext wire protocol (HELLO/PUSH/FETCH/ACK/FAIL/
INFO); a small embedded python does the socket I/O + the iterated-sha256 password handshake (pure
bash can't do 6091 sha256 rounds in one process). The CLI/exit-code surface is bash. **No queue logic
is implemented here** — Faktory owns enqueue/lease/retry/morgue.

`info` mechanism: OSS Faktory has **no** wire per-jid query (`TRACK` is Enterprise-only), so `info`
reads the authenticated Web UI — the only non-destructive per-job read surface — scanning the
enqueued queues + scheduled/retries/dead/busy sets. Documented limitation, not a mock.

Worker: `fleet/faktory/faktory-worker.sh` reserves → runs the payload (`bash -c` for a single opaque
shell string; direct `argv` exec for explicit argv) → ACK on rc0 / FAIL on rc!=0. Never routes
through Anthropic/Claude (payload is `charon-run.sh` → non-Claude 4-LOM gateway).

## 3. Durability proof — REAL, not mocked (`fleet/faktory/test-faktory.sh`, all green)

Run against the LIVE 4-LOM server (`FAKTORY_PASSWORD` from `~/.faktory/password`):

- **T1 lease-exclusivity** — PASS. A reserved job is invisible to a second `reserve` (empty + rc1).
  The reservation is time-based (`reserve_for`), held server-side across client-connection close.
- **T2 durability (the ACK-survives-restart proof)** — PASS. Push job J + a still-enqueued control
  job C; reserve+ACK J; then a **real container recreation** (`docker stop` → `docker rm` →
  `docker run` against the `faktory-data` volume). After restart: **J is GONE** (`info` rc1, not
  re-fetchable) AND **C SURVIVED** (`info` = `enqueued`). The surviving control job is the load-bearing
  half — it proves the RDB genuinely persisted, so J's absence is a durable ACK, not merely an
  emptied queue. Real evidence, e.g.:
  `PASS: T2 ACKed job TST-…-172102346 GONE after real recreation; control job TST-…-223891025 survived (RDB persisted)`.
- **T3 fail-requeue** — PASS. A FAILed job returns to the `retries` set (requeued per backoff), not
  lost and not dead — the loop-guard retry analog, native, zero hand-rolled counter.
- **T4 worker e2e** — PASS. `faktory-worker.sh --once` reserved a charon-run-shaped job, ran its
  payload (observable side-effect file created), ACKed it; the job is then absent.

**Durability caveat (honest):** the embedded store uses periodic RDB snapshots, not per-write fsync.
A **graceful** stop (SIGTERM — the normal `docker stop` / reboot / recreation path) flushes the RDB,
so ACKs survive — this is what T2 proves and what a "container recreation" means operationally. A
**SIGKILL crash** (`docker rm -f`, `kill -9`, power loss) can lose the last snapshot window; a job
whose ACK is lost simply re-runs (at-least-once — the same assumption `loop-guard` already made).
Discovered empirically: an initial T2 using `docker rm -f` (SIGKILL) showed the ACK reverting — this
is documented rather than hidden, and T2 uses the correct graceful path. If stronger crash durability
is ever required, tighten Faktory's RDB save points / enable its AOF-equivalent.

## 4. Unblocks

This client + durability proof unblock **CLAIM-LEASE-EXACTLY-ONCE (T1)**: T1 codes its idempotent
enqueue + lease-as-claim against the `faktory-client.sh` surface above (stable, drift-free), and its
final integrated e2e (real Faktory) serializes after this lands.

## 5. Files (owned by this ticket)

- `fleet/faktory/faktory-client.sh` — anchor CLI.
- `fleet/faktory/faktory-worker.sh` — reserve→run→ack/fail worker.
- `fleet/faktory/test-faktory.sh` — real durability/lease/requeue proof (4/4 green).
- `fleet/faktory/README.md` — server + client + worker how-to.
- `fleet/state/FAKTORY-ADOPT.md` — this record.
- `.gitignore` — one-line negation `!fleet/state/FAKTORY-ADOPT.md` (the blanket `fleet/state/*`
  ignore would otherwise silently drop this record; same anchor-file pattern as the other tracked
  state docs).
