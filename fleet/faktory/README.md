# Faktory — the ONE durable job/lease substrate

Faktory (contribsys/faktory, a single ~15 MB Go container with an embedded Redis-protocol store) is
the fleet's **sole** durable job queue + lease + retry + dead-letter substrate. It replaces the
hand-rolled `loop-guard.sh` DLQ and is the claim-lease store that `CLAIM-LEASE-EXACTLY-ONCE` codes
against. **Do not stand up a second queue** — adopt this one.

This directory is a *thin* contract-shaped shell wrapper over Faktory's plaintext wire protocol. It
implements **no** queue logic of its own — Faktory owns enqueue, reservation/lease, backoff-retry,
and the dead set (morgue).

- `faktory-client.sh` — the anchor CLI (`push | reserve | ack | fail | info`).
- `faktory-worker.sh` — reserve → run a `charon-run.sh`-shaped payload → ACK / FAIL.
- `test-faktory.sh` — real (non-mocked) proof of the lease + durability + requeue contract.

## 1. The server (durable, on 4-LOM)

Faktory runs on **4-LOM (`10.0.1.60`)** as a container named `faktory`, with a named docker volume
mounted at the **real** RDB path (`/root/.faktory`, *not* `/data`) so job state survives container
recreation, and `--restart unless-stopped` so it survives host reboots. A password (generated once,
stored only in `~/.faktory/password` on 4-LOM — **never committed**) protects both the protocol port
and the Web UI.

```bash
# on 4-LOM (10.0.1.60). Password is generated once and kept out of git.
PW="$(cat ~/.faktory/password)"          # created via: openssl rand -hex 24 > ~/.faktory/password
docker volume create faktory-data
docker run -d --name faktory --restart unless-stopped \
  -v faktory-data:/root/.faktory \
  -e FAKTORY_PASSWORD="$PW" \
  -p 0.0.0.0:7419:7419 \                  # protocol port (LAN — clients on the dev box reach this)
  -p 0.0.0.0:7420:7420 \                  # Web UI (password-protected; live dead-set/retry badges)
  contribsys/faktory:latest /faktory -b :7419 -w :7420
```

Web dashboard: `http://10.0.1.60:7420/` (HTTP basic auth, empty user + the password). It shows live
Processed / Failed / Enqueued / Retries / **Dead** counts with one-click requeue/kill — the loud,
passive observability that `loop-guard.sh`'s stderr-only escalation lacked.

## 2. Client config (env; no secrets in git)

| Var | Default | Meaning |
|---|---|---|
| `FAKTORY_HOST` | `10.0.1.60` | 4-LOM (where the durable server runs) |
| `FAKTORY_PORT` | `7419` | protocol port |
| `FAKTORY_PASSWORD` | *(empty)* | **required** — our server has a password; fetch from 4-LOM `~/.faktory/password` |
| `FAKTORY_WEB` | `http://$FAKTORY_HOST:7420` | Web UI; the OSS read surface `info` uses |

```bash
export FAKTORY_PASSWORD="$(ssh -i ~/.ssh/4lom stack@10.0.1.60 'cat ~/.faktory/password')"
```

## 3. Client CLI (the anchor contract)

```
faktory-client.sh <cmd> [args]     # exit 0 success / non-zero failure
  push    --queue Q --jobtype T --jid <ticket-id> --arg <json> [--reserve-for S] [--retry N]
          # enqueue; prints the jid. --arg may repeat; each is parsed as JSON (string fallback).
  reserve --queue Q [--timeout S]
          # FETCH one job; prints job JSON {jid,args,...} or empty + rc1 if the queue is empty
  ack     --jid <id>                # terminal success; job durably GONE (survives graceful restart)
  fail    --jid <id> [--msg M]      # terminal fail; requeues per the retry/backoff policy
  info    --jid <id>                # prints the live set (enqueued:<q>|scheduled|retries|dead|working);
                                     # rc1 if the jid is absent everywhere (T1's idempotent-enqueue check)
```

Payload convention: `jobtype "charon-run"`, `args` = the `charon-run.sh` invocation. `reserve_for`
default **1800 s** (the lease window).

`info` note: OSS Faktory has **no** wire-protocol per-jid query (the `TRACK` command is
Enterprise-only), so `info` reads the authenticated Web UI — the only non-destructive per-job read
surface — scanning the enqueued queues plus the scheduled / retries / dead / busy sets.

### Example
```bash
JID=MYTICKET-1
faktory-client.sh push --queue default --jobtype charon-run --jid "$JID" \
  --arg '"bash /home/stack/charon-private/fleet/charon-run.sh /path/cwd /path/out.log /path/brief.txt model-x"'
faktory-client.sh info --jid "$JID"        # -> enqueued:default
faktory-client.sh reserve --queue default  # -> {"jid":"MYTICKET-1","args":[...],...}
faktory-client.sh ack --jid "$JID"         # -> terminal success
```

## 4. Worker

```
faktory-worker.sh [--queue Q] [--once] [--idle-sleep S]
```
Reserves a job, runs its payload (single-element `args` → `bash -c "<cmd>"`; multi-element `args` →
`exec argv` directly), then **ACK** if the payload exits 0 or **FAIL** (→ requeue/backoff, and to the
morgue after retries exhaust) otherwise. `--once` processes one job and exits (rc 0 = ran, rc 3 =
queue empty). NEVER routes through Anthropic/Claude — the payload is `charon-run.sh`, which targets
the non-Claude 4-LOM gateway.

```bash
# one-shot drain:
faktory-worker.sh --queue default --once
# long-running worker (detach so it survives /quit — see MEMORY: background-jobs-detach):
setsid faktory-worker.sh --queue default >/var/log/faktory-worker.log 2>&1 &
```

## 5. Tests (real, non-mocked)

```bash
export FAKTORY_PASSWORD="$(ssh -i ~/.ssh/4lom stack@10.0.1.60 'cat ~/.faktory/password')"
bash fleet/faktory/test-faktory.sh
```
Proves, against the LIVE server: (T1) a reserved job is invisible to a second reserve; (T2) an ACKed
job is durably GONE while a still-enqueued control job SURVIVES a **real graceful container
recreation** (`docker stop` → `rm` → `run`); (T3) a FAILed job requeues (retries set, not lost, not
dead); (T4) `faktory-worker.sh` runs a charon-run-shaped payload end-to-end and ACKs.

**Durability caveat (documented, not hidden):** the embedded store uses periodic RDB snapshots, not
per-write fsync. A **graceful** stop (SIGTERM, the normal recreation / reboot path) flushes the RDB,
so ACKs survive — proven by T2. A **SIGKILL crash** (`docker rm -f`, `kill -9`, power loss) can lose
the last snapshot window. For the fleet's job/lease use this is acceptable (a lost-ACK job simply
re-runs — the same at-least-once semantics `loop-guard` already assumed); if stronger crash
durability is ever needed, enable Faktory's more aggressive RDB save points or its AOF-equivalent.
