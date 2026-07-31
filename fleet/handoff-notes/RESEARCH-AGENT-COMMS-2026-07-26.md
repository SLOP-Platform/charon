# RESEARCH — manager↔worker agent-session comms (2026-07-26)

**Verdict: ADOPT opencode's own HTTP control plane. Do not extend the session-bridge; retire it.**
The mechanism we need already ships inside the binary we already run. I verified it live against
opencode 1.18.5 on this box — created sessions, steered a running one, interrupted it, streamed
events, and authenticated cross-host. Zero new dependencies, zero new protocol, zero model cooperation.

Legend: **[V]** = I verified it myself on this box (command + observed output). **[VD]** = verified by
reading spec/docs. **[I]** = inferred, not proven.

---

## 0. The finding that decides everything

`opencode` is *already* a client/server program. The TUI is just one client of an HTTP server that
every opencode process can host. **[V]**

```
$ opencode serve --port 47311 --hostname 127.0.0.1
opencode server listening on http://127.0.0.1:47311
$ curl -s localhost:47311/doc      # full OpenAPI 3.1 spec, 180+ operations
```

This inverts our problem. We have been trying to get the *model* to report in. We never needed the
model at all — the **harness** exposes everything, whether the model likes it or not.

### The five needs, mapped to verified endpoints

| # | Need | Endpoint | Status |
|---|------|----------|--------|
| 1 | See who is alive / what they're doing | `GET /api/session/active`, `GET /api/session`, `GET /api/session/{id}` (auto-generated `title`, `cost`, `tokens`), `GET /session/{id}/todo` | **[V]** |
| 2 | Send a directive into a RUNNING session | `POST /api/session/{id}/prompt` with `{"delivery":"steer"}` | **[V]** |
| 3 | Launch work on an idle session | `POST /api/session` then `POST /api/session/{id}/prompt` | **[V]** |
| 4 | Receive results/status | `GET /api/event` (SSE push), `GET /api/session/{id}/event`, `GET /api/session/{id}/message` | **[V]** |
| 5 | Detect dead/hung, reclaim | `GET /api/health`, `POST /api/session/{id}/interrupt`, `POST /api/session/{id}/wait`, `session.next.step.failed` events, `POST /sync/steal` | **[V]** (steal **[I]**) |

Bonus, and it is not a small one — **`POST /api/session/{id}/question/{reqID}/reply`** and
**`POST /api/session/{id}/permission/{reqID}/reply`**, with `GET /api/question/request` and
`GET /api/permission/request` to enumerate pending ones. **[V]** (endpoints live, returned `{"data":[]}`).
This is the direct fix for the long-standing "background agents block forever on a prompt" problem
in `background-agent-liveness`. The manager can now *see* a blocked worker and answer it.

### Verified transcript — steer + interrupt on a live running session

```
SID=ses_0604b9907ffe616NO77EnKO4Vx     (created via POST /api/session)
# fired a long prompt, then 22s later:
GET /api/session/active
  → {"data":{"ses_0604b9907ffe616NO77EnKO4Vx":{"type":"running"}}}          # NEED 1
POST /api/session/$SID/prompt  {"prompt":{"text":"STOP counting. Reply only: SWITCHED"},
                                "delivery":"steer"}
  → {"data":{"admittedSeq":3,"id":"msg_f9fb4c04a001FCzL4RszTXarBa",
             "delivery":"steer",...}}                                        # NEED 2
POST /api/session/$SID/interrupt
GET /api/session/active
  → {"data":{}}                                                             # idle. NEED 5
```

On a second run the steered directive was confirmed **durably admitted into the conversation** as a
`user` message and it triggered a fresh agent step — i.e. `steer` is not a side-channel note, it
enters the model's context mid-turn. **[V]**

`delivery` accepts `"steer"` (inject into the current turn) or `"queue"` (deliver after the current
turn). Spec text: *"Durably admit one session input and schedule agent-loop execution."* **[VD]**

---

## 1. THE CRITICAL CONSTRAINT (empirically discovered — this changes the recipe)

Read this before designing anything.

> `POST /api/session/{id}/interrupt` — *"Interrupt active execution **owned by this OpenCode process**.
> Idle interruption is a no-op."* **[VD]**

I proved what that means in practice. **[V]**

- **Reads are global.** All opencode processes share one store (`~/.local/share/opencode/opencode.db`,
  currently 6.5 GB). Any server instance can *list and read* every session on the box, including
  sessions belonging to other processes. I saw live fleet tickets (`"Executing SW-STATIC-LEGS-RETIRE
  prompt"`) from a server I had just started.
- **Control is process-local.** Steer/interrupt only work on sessions whose *agent loop* is running
  inside the process you are talking to.

I tested `opencode run --attach http://…` (the shape `charon-run.sh:209` uses). The attached server
**could see** the session — correct title, cost, tokens, `"Counting 1 to 400 with comments"` — but
`interrupt` was a **no-op**: the run process owns the loop, so the server had nothing to interrupt.
The hung process stayed hung. **[V]**

**Therefore: the worker process must itself be the server.** Two supported shapes, both verified:

| Shape | Command | Operator sees TUI? | Manager control? |
|---|---|---|---|
| Interactive tab | `opencode --port <N> --model charon/<m>` | **yes** | **yes** **[V]** |
| Headless droid | `opencode serve --port <N>` + drive via HTTP | no | **yes** **[V]** |
| ~~Attached run~~ | `opencode run --attach <url>` | no | **see-only, no control** **[V]** |

The first row is the important one: I launched `opencode --port 47399` under a pty, and it served the
**full** API (`/api/health` → `{"healthy":true}`) while running a normal interactive TUI. The operator
keeps the watchable tab *and* the manager gets control. That is a rare win — no tradeoff.

Note the current 8 fleet workers listen on **nothing** (`ss -tlnp` → no listener for any of the 8
`opencode --model …` pids). **[V]** The default `--port 0` means "ephemeral" but the TUI does not bind
unless a port is given. So this is a launcher-flag change, not a free upgrade.

Other verified operational details:
- **Cross-host works and is authenticated.** `OPENCODE_SERVER_PASSWORD=… opencode serve --hostname
  0.0.0.0 --port 47355` → bound `0.0.0.0`; unauthenticated `GET /api/health` = **401**, wrong creds =
  **401**, `-u opencode:<pw>` = `{"healthy":true}`. HTTP basic auth, built in. **[V]** Without the env
  var it prints `Warning: OPENCODE_SERVER_PASSWORD is not set; server is unsecured.` **[V]**
- **The API is location-scoped.** Most endpoints take a `?directory=` query param and default to the
  server's cwd. `GET /api/session/active` returned `{}` until scoped correctly. This cost me a false
  negative during testing — the manager must always pass `directory`. **[V]**
- `--mdns` gives service discovery (defaults hostname to 0.0.0.0). **[VD]** — useful for cross-host
  discovery, untested here.
- `/tui/append-prompt`, `/tui/submit-prompt`, `/tui/show-toast`, `/tui/execute-command` exist and
  return `true`, but in my headless-pty test they produced **no turn and no events** — they publish to
  an attached TUI client that long-polls `/tui/control/next`. **Do not build on `/tui/*`; use
  `/api/session/{id}/prompt`.** **[V]**
- Events are event-sourced with `durable:{aggregateID,seq,version}` and there are `sync.replay` /
  `sync.history` / `sync.steal` endpoints — a replayable log, so a restarted manager can catch up
  rather than lose state. **[V]** for the shape, **[I]** for the semantics.

---

## 2. Why the current session-bridge cannot be saved

**It is bigger than we think.** Not ~500 LOC — **3,073 LOC** of Python across
`/home/stack/.config/opencode/session-bridge/` **[V]**:

```
865 daemon.py   716 server.py   478 proxy.py   103 idempotency.py
297 test_daemon.py   345 test_proxy.py   149 verify_idle_proof.py   120 verify_kill_proof.py
```

plus a SQLite store, a per-session `proxy.py` sidecar process (one per worker — I count 8 running),
an SSH-forwarded unix socket, and bespoke lease/purge/nudge logic. That is a product-sized artifact
doing a job the vendor already does.

**The adoption failure is measurable, right now.** `/home/stack/.charon/session-bridge.db` **[V]**:

| live opencode workers | rows in `sessions` | real, current registrations |
|---|---|---|
| **8** | 3 | **2** |

The third row is `rival-proof`, a `TICKET-KILL-PROOF` test artifact whose lease expired at 17:17 and
which has since accumulated an auto-nudge *"lease expired > 600s ago"*. So the board the manager
relies on is showing 2 of 8 workers, plus one ghost.

**And I caught the root cause on camera.** During an unrelated test, a worker spontaneously did this:

```
> build · minimax-m3-free
I'll register this session and then count.
⚙ session-bridge_register {"session_id":"counter-1","name":"Count from 1 to 400...",...}
```

It registered — *and then hung there indefinitely*, never counting, until I killed it. **[V]** That is
the whole indictment in five lines: registration is a **model decision** (this one chose to, most
choose not to), it **steals the worker's actual task**, and the tool call itself became a **liveness
hazard**. A mechanism that is simultaneously unreliable, distracting, and hang-prone is not
fixable by tightening the prompt.

The generalisation is already in memory as `dynamic-tools-never-on-demand` and the
"put it in the TRANSPORT, never in the prompt" pattern. The bridge is the counter-example that proves it.

---

## 3. Candidates evaluated

### 3.1 MCP bidirectional — **the honest answer is NO** (and this exonerates our code)

There is no way for an MCP server to push a message that alters or interrupts what the model is
doing without the model electing to call a tool. The 8-of-8 failure was **not a bug in our server; it
is the protocol's design.** **[VD]**

- Server→client requests exist (`sampling/createMessage`, `elicitation/create`, `roots/list`) and
  Streamable HTTP genuinely allows unsolicited server messages. But **sampling** is a nested,
  isolated LLM call whose result returns *to the server* — it never enters the agent's conversation;
  **elicitation** targets the human; **notifications** (`progress`, `logging`, `list_changed`) are
  consumed by client plumbing, not spliced into model context. There is **no `interrupt`, `inject`,
  or `steer` primitive anywhere in MCP.**
- The trend runs *away* from us. In the **2026-07-28** revision: Roots, Sampling and Logging are
  **deprecated** (SEP-2577, migration advice: "integrate directly with LLM provider APIs instead");
  **SEP-2322 removes server-initiated requests entirely** in favour of client-pull
  `InputRequiredResult`; the protocol goes stateless (handshake, `Mcp-Session-Id`, SSE resumability
  all removed).

**Do not spend another hour making MCP a control plane.** Keep MCP for giving workers *capabilities*.
Licence: MIT (SDKs). https://modelcontextprotocol.io/specification/2025-06-18/basic/transports ·
https://modelcontextprotocol.io/specification/draft/changelog

### 3.2 Zed ACP (Agent Client Protocol) — **strong #2, and our agent-agnostic hedge**

Genuinely excellent, and `opencode acp` already implements it. I confirmed the handshake myself **[V]**:

```
$ echo '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' | opencode acp
{"protocolVersion":1,"agentInfo":{"name":"OpenCode","version":"1.18.5"},
 "agentCapabilities":{"loadSession":true,
   "sessionCapabilities":{"close":{},"fork":{},"list":{},"resume":{}}, ...}}
```

- Control is genuinely client-owned: `session/cancel` (may be sent any time during a turn; agent MUST
  stop LLM + tool calls and resolve with `StopReason::cancelled`), `session/set_config_option` (swap
  the model mid-session), `session/set_mode` (force `plan` = strip edit tools), `session/close`.
  Agent→client `session/update` notifications stream unprompted. The model never gets a vote. **[VD]**
- **Python dependency weight is the best in this entire report: `pydantic` and nothing else.**
  (`agent-client-protocol` 0.11.0 on PyPI, Apache-2.0.) **[VD]**
- Maturity is real: `zed-industries/agent-client-protocol`, Apache-2.0, **100 commits in 11 days**
  (2026-07-15→07-26), co-maintained by Zed **and JetBrains**. Agents speaking it: opencode, Gemini
  CLI, Claude Code (adapter), Codex, Goose, Cline, Cursor Agent. **[VD]**
- **Why it is #2 and not #1, for *us*:**
  1. **stdio-only.** The HTTP transport is a draft proposal. The manager must *own the subprocess's
     stdin* — which means **the operator loses the interactive TUI tab**. Our HTTP option keeps it.
  2. Cross-host is DIY (`ssh host opencode acp` — clean, but ours to build and babysit).
  3. Adds a dependency and a one-maintainer bus factor on the Python SDK (community-run inside the
     official org, not Zed-staffed).
  4. `stopReason: cancelled` could **not** be empirically confirmed (probe runs hit empty gateway
     responses); mid-turn `session/prompt` was accepted but queue-vs-interleave is **unverified**.
     Our HTTP `steer` **was** verified.
- **Where it wins later:** ACP is the *agent-agnostic* standard. Our standing directive
  `charon-modular-agent-and-provider-agnostic` says no hardcoded agent. opencode's HTTP API is
  opencode-specific. **This is the one real tension in this recommendation** — see §5.
  https://agentclientprotocol.com/protocol/overview · https://opencode.ai/docs/acp/

> **Disambiguation:** IBM/BeeAI's "Agent Communication Protocol" (also "ACP") is a *different, dead*
> protocol — it merged into A2A (LF AI & Data, 2025-08-29) and development wound down. Zed's ACP is
> unrelated beyond the collided acronym. Always search "Zed ACP". **[VD]**

### 3.3 A2A (Agent2Agent) — wrong layer

v1.0, Apache-2.0, Linux Foundation, 25k stars, JSON-RPC/gRPC/REST bindings, real server→client push
(SSE + signed-JWT webhooks). Mature and cross-host-native. **[VD]**

**Disqualified:** A2A is for peer agents delegating *opaque* tasks — its own framing is that agents
collaborate "without exposing their internal state, memory, or tools." "Steering" = a follow-up
message on the same `taskId`, which the remote agent handles as it likes; `CancelTask` is a **request
the agent may decline**. Nothing in A2A reaches into opencode's turn loop, opencode doesn't speak it,
and we'd maintain an A2A↔ACP shim. Deps are heavy (`httpx`, `pydantic`, `protobuf`, `google-api-core`,
`json-rpc`, `googleapis-common-protos`, …). **[I]** It is the right layer *above* ACP for
manager↔manager federation across hosts, if we ever want that. https://a2a-protocol.org/latest/specification/

### 3.4 AG-UI — wrong shape

MIT, 14.9k stars, genuinely active (2,764 commits). Does claim interrupts and "agent steering". **[VD]**
**Disqualified:** it is an agent↔*frontend* contract — the agent backend must be *written* to emit and
honour AG-UI events. It cannot wrap an opaque CLI; opencode doesn't speak it; **Python has no
completed SDK**. Its steering is cooperative by construction. Relevant only if we later want a browser
dashboard. https://docs.ag-ui.com/introduction

### 3.5 Faktory — **keep it, but for dispatch, not control** (already running here)

Why it was deployed: it is already our durable job/lease store (`fleet/lease-enqueue.sh`,
`fleet/work-lease.sh`; tickets WORK-LEASE-GATE #204, FAKTORY-ADOPT #243, CLAIM-LEASE-EXACTLY-ONCE #245).

- **Pull-only.** No server→worker push; producers target a *queue*, not a worker. Targeted delivery
  needs a queue-per-worker (`q.<wid>`) convention. **[VD]**
- `BEAT` every ~15s; the reply can carry `quiet` (stop fetching) or `terminate` (FAIL + exit ≤30s) —
  a real but **coarse** out-of-band control channel. Not "switch to ticket X".
- **Reclaim latency trap:** a dead worker leaves Busy after 60s, but **its jobs are not recovered
  until `reserve_for` elapses — default 1800s (30 min)**. Tune this down if we rely on it. **[VD]**
- `MUTATE` only touches Retries/Dead/Scheduled — **cannot kill a running job**; docs call it
  best-effort and "not for application logic". **[VD]**
- Licence: server **AGPLv3**; **Bring-Your-Own-Redis is Enterprise-only** (OSS embeds its own Redis —
  so do **not** try to share Faktory's Redis). Batches/Throttling/Expiry/Unique/Tracking are
  Enterprise. **[VD]**
- Python clients are weak (`faktory_worker_python` ~62★, stale, open reconnect bug; `pyfaktory` more
  current). The wire protocol is small text-over-TCP. **[VD]**
- **Verdict: right tool, different job.** Faktory models *jobs*, not long-lived interactive sessions —
  an 8-hour session as one "job" fights `reserve_for`. Keep Faktory as **work dispatch + exactly-once
  claim + reclaim**; it has no answer for needs 1, 2, 4. It is complementary to, not competing with,
  the opencode control plane.

### 3.6 NATS / Redis-Valkey / ZeroMQ / MQTT / gRPC

- **NATS (+JetStream)** — the best *pure* substrate if we ever outgrow the above: single Apache-2.0 Go
  binary, no deps; per-worker subjects; request/reply native; **two real presence primitives** —
  KV bucket with per-key TTL (server ≥2.11) and `$SYS.ACCOUNT.*.CONNECT/DISCONNECT` advisories, so the
  broker *tells* you a worker died with zero polling. `nats-py` is pure-Python with no hard deps.
  Covers all 5 needs alone. Caveat: `$SYS` advisories are per-node in a cluster (nats-server#3177).
  **[VD]** — **but it solves the wrong half.** It moves *messages*; it cannot make opencode stop.
- **Redis Streams / Valkey** — `XAUTOCLAIM` (6.2+) is a one-command reclaim of a dead consumer's
  pending list; consumer groups for dispatch; key TTL for liveness. Licence churn matters: BSD →
  RSALv2/SSPL (2024) → tri-licensed +AGPLv3 (Redis 8.0, 2025); **Valkey** is the LF BSD fork. Reclaim
  is *polled*, presence is DIY. **[VD]**
- **ZeroMQ** — brokerless, no persistence, no presence; you hand-roll the whole reliability layer
  (Paranoid Pirate). Anti-adopt-first. ✗
- **MQTT** — Last-Will-and-Testament + retained messages is genuinely good presence, but no leases, no
  reclaim, weak request/reply. NATS supersedes (and even speaks MQTT). ✗
- **gRPC bidi** — right shape, but we author the service, reconnect, registry and liveness. Large
  surface, zero adopted machinery. ✗

### 3.7 Temporal — right semantics, wrong weight (today)

Models our problem almost exactly: worker-session = long-running Activity; `heartbeat_timeout` →
server reassigns on silence; heartbeat *details* = progress checkpoint; `start_to_close` catches
hangs; **Signals** inject directives into a running workflow; **Queries** read state. **[VD]**
Costs: Temporal server + Postgres/Cassandra (+ Elasticsearch); `temporalio` Python SDK is a compiled
PyO3/Rust extension; workflow code must be **deterministic** — a constraint that will bite. Activity
cancellation is *delivered via the heartbeat response*, so the activity must heartbeat to learn it
was cancelled — cooperative again. **Correct answer if this becomes a product; wrong answer for a
solo dev with a Faktory already running.**

### 3.8 Multi-agent frameworks — all disqualified

Blunt answers to *"can an external manager inject a directive into an already-running agent process
it did not spawn?"* **[VD]**

| Framework | External inject? | Reality |
|---|---|---|
| AutoGen / AG2 | **NO** | In-process Python lib; owns the agent loop; nothing to talk to from outside |
| CrewAI | **NO** | `kickoff()` owns the loop; no server, no external control surface |
| LangGraph | **PARTIAL** | `interrupt()`+checkpointer is **cooperative** (graph must contain the node); true out-of-process control needs LangGraph Platform. Must own the loop → cannot wrap an opencode CLI |
| OpenAI Agents SDK | **NO** | In-process `Runner.run()`; "Sessions" = memory, not addressable live agents |
| Letta / MemGPT | **YES**, but | Genuine agents-as-services (`POST /agents/{id}/messages`) — but it's Letta's *own* runtime; it will not host opencode |
| Ray | **YES**, but | Named detached actors are a real cross-host control plane — but the worker must *be* a Ray actor; heavy cluster dep for 8 procs on one box |

Four of six assume they own the agent loop. The two exceptions demand we rewrite the worker into
*their* runtime. **None is adoptable here.**

### 3.9 tmux send-keys — **reject**

Documented, reproducible breakage: send-keys races shell init and silently drops keystrokes
(anthropics/claude-code#23513); bracketed-paste submit race leaves the prompt typed-but-unsubmitted
(obra/claude-session-driver#20); bracketed paste under tmux can wedge into permanent "still pasting"
(neovim#38021, microsoft/terminal#19418). **[VD]**
Best prior art (`obra/claude-session-driver`) is instructive: it drives input by keystroke but
**refuses to scrape the TUI for state** — workers emit lifecycle events to JSONL and the controller
tails those. That split (keystrokes in, structured events out) is exactly what we get *for free* from
opencode's HTTP API, without the races. Keystroke injection is a last resort for agents with **no**
API. opencode has one.

---

## 4. Ranked recommendation

| # | Option | Why |
|---|--------|-----|
| **1** | **opencode HTTP control plane** (`--port` on every worker) | Already in the binary. All 5 needs **verified live**. Zero deps, zero new protocol. Keeps the interactive TUI. Auth + cross-host built in. |
| 2 | Zed ACP (`opencode acp`) | Equally model-proof, one dep, agent-**agnostic**. Costs the TUI (stdio-only) and DIY cross-host. **Our hedge — see §5.** |
| 3 | Keep Faktory for dispatch/lease/reclaim | Already adopted, already working. Complementary — no overlap with 1. |
| 4 | NATS, *only if* we outgrow Faktory | Best pure substrate; solves messaging, not control. |
| 5 | Temporal | Right semantics, wrong weight today. Revisit if this becomes a product. |
| ✗ | MCP-as-control, A2A, AG-UI, AutoGen/CrewAI/LangGraph/Agents-SDK/Letta/Ray, ZeroMQ/MQTT/gRPC, tmux send-keys | See §3 |

### Why #1 wins, in one sentence
The MCP bridge failed because tool calls are **model-elective**; the HTTP server is
**harness-elective** — the manager talks to the *process*, and the model has no vote and no way to
decline.

### What we LOSE versus the current bridge — honestly

1. **Ticket semantics.** opencode knows about *sessions*, not tickets, claims, branches or blockers.
   Atomic claim/release and the ticket board are **not** replaced by this. → They shouldn't be:
   that's Faktory's job (#245 already proved exactly-once claim). The bridge was conflating two
   layers; this splits them correctly.
2. **Jedi-name identity.** `cal-kestis` → `ses_0604b99…`. We need a `name → (host, port, sessionID)`
   registry. That is a small file the *launcher* writes — not something an agent must call. **[I]**
3. **The nudge queue.** Superseded, and by something better: `delivery:"steer"` puts the directive in
   the model's context *now* instead of parking it until the agent chooses to poll.
4. **Cross-host lease liveness.** The bridge deliberately used leases, not pids, for cross-host. HTTP
   health-check + `/api/session/active` is a *reachability* probe, which is arguably stronger — but
   a worker whose host drops off the network is now "unreachable" rather than "lease-expired", and
   the reclaim policy must be re-decided. **This is the one genuine regression to design around.**
   Faktory's `reserve_for` already covers work reclaim; use it, and tune it down from 1800s.
5. **~3,073 LOC and 8 sidecar processes deleted.** Counting this as a loss would be dishonest.

---

## 5. The one real tension: agent-agnosticism

Standing directive `charon-modular-agent-and-provider-agnostic` says **no hardcoded agent**. Adopting
opencode's HTTP API *is* agent-specific — and that must be stated plainly rather than glossed.

Mitigation, and it is cheap: the manager's control surface is only five verbs —
`list / launch / steer / interrupt / events`. Put those behind a thin adapter interface with an
**opencode-HTTP** backend now. If we ever add a non-opencode worker, write an **ACP** backend
(Gemini CLI, Codex, Claude Code adapter and Goose all speak ACP) and the manager doesn't change.
That keeps the directive satisfied without paying ACP's costs today. **[I]**

---

## 6. Smallest spike to prove it (< 1 day, honestly ~2 hours)

**Goal: one manager script drives one real worker, end to end, with no MCP and no model cooperation.**

1. **Launch one droid tab with a port** (the entire product change is one flag):
   ```
   opencode --port 47001 --model charon/<m>          # instead of: opencode --model charon/<m>
   ```
   Record `name → port` in a launcher-written file. Set `OPENCODE_SERVER_PASSWORD` for anything
   non-loopback.
2. **Write `fleet/session-ctl.sh`** — thin curl wrapper, ~60 lines, stdlib only, **always passing
   `?directory=`**:
   | verb | call |
   |---|---|
   | `board` | `GET /api/session/active` + `GET /api/session` (title/cost/tokens) |
   | `steer <name> <text>` | `POST /api/session/{id}/prompt` `{"delivery":"steer"}` |
   | `stop <name>` | `POST /api/session/{id}/interrupt` |
   | `launch <name> <text>` | `POST /api/session` → `POST …/prompt` |
   | `watch` | `GET /api/event` (SSE) |
   | `unblock` | `GET /api/permission/request` → `POST …/permission/{id}/reply` |
3. **Acceptance test — all four must pass on a REAL ticket session:**
   - `board` shows the worker as `running` with a correct title, **without the worker calling anything**;
   - `steer` visibly changes what the worker does mid-run;
   - `stop` returns it to idle;
   - kill the worker's process → `board` reports it gone within one interval.
4. **Then, and only then:** point `dark-work-check.sh` at `session-ctl.sh board` instead of the
   bridge DB, and retire `proxy.py` from the launcher. Delete the bridge once the board has been
   green for a full session.

**Explicitly NOT in the spike:** ticket claim (Faktory owns it), the ACP adapter (hedge, not now),
NATS/Temporal.

**Re-verify before committing** — my two unproven assumptions: (a) `POST /sync/steal` semantics for
reclaiming a session from a dead process; (b) whether `--mdns` is a usable cross-host discovery
mechanism or just LAN-toy.

---

## 7. Reproduce my results

```bash
opencode serve --port 47311 --hostname 127.0.0.1 &     # or: opencode --port 47311 --model charon/<m>
curl -s localhost:47311/doc | python3 -m json.tool | less    # 180+ operations, OpenAPI 3.1
D=/home/stack/charon-private
SID=$(curl -s -X POST localhost:47311/api/session -H 'content-type: application/json' \
      -d "{\"agent\":\"build\",\"model\":{\"providerID\":\"charon\",\"id\":\"minimax-m3-free\"},\"location\":{\"directory\":\"$D\"}}" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')
curl -s -X POST localhost:47311/api/session/$SID/prompt -H 'content-type: application/json' \
      -d '{"prompt":{"text":"Count to 400, one per line."}}' &
sleep 20; curl -s "localhost:47311/api/session/active?directory=$D"        # → running
curl -s -X POST localhost:47311/api/session/$SID/prompt -H 'content-type: application/json' \
      -d '{"prompt":{"text":"STOP. Reply only: SWITCHED"},"delivery":"steer"}'
curl -s -X POST localhost:47311/api/session/$SID/interrupt
```
Gotchas that cost me time: `ModelRef` key is **`id`** not `modelID`; `PromptInput` requires **`text`**
(not `parts`); a malformed URL falls through to the **web SPA** and returns HTML, not a JSON error;
and **everything is `?directory=`-scoped**.

*All test processes were cleaned up; the 8 live fleet workers were never touched — verified before
and after.*
