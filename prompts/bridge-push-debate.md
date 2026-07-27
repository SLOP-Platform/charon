# BRIEF — BRIDGE PUSH + SHARED DEBATE-THREAD primitives (B2/B8 core)

You are building the missing PUSH + shared-thread primitives on the session-bridge so that
multiple REAL sessions can debate directly (post rounds, get pushed replies, reach consensus)
with no central relayer. This is the reusable core; it will be adopted into SLOP after E2E proof,
so it MUST be portable: pure Python stdlib + POSIX shell, NO charon-only coupling, parameterized paths.

## Repo / safety (READ FIRST)
- CWD (already a git repo, baseline commit 077d654): `/home/stack/.config/opencode/session-bridge/`
- Work on a NEW branch: `git checkout -b feat/bridge-push-debate`. Commit at the end. There is NO remote — do NOT push, do NOT open a PR.
- The daemon is LIVE (two long-running `daemon.py` processes). **Do NOT restart, signal, or kill the live daemon. Do NOT touch its live DB.** ALL your testing runs against a SCRATCH DB in a tmp dir on a spare port. Deploy/restart is a separate gated step you do NOT perform.

## Code-confirmed starting facts (verify, then build — cite line numbers in your report)
- `daemon.py`: `board`/`update` return immediately — NO waiter registry; `poll_wait` is explicitly deferred (~daemon.py:23). The bus is strictly point-to-point: `nudge` writes ONE target's `nudge_messages` column (~daemon.py:606-643). So N sessions cannot share one debate log today.
- ALREADY BUILT — do NOT rebuild, WIRE/reuse: at-least-once delivery + `ack` + persisted `seq` (~daemon.py:153-189, 645-681); `idempotency.py` exists but is UNWIRED.
- `proxy.py` is the opencode-side client wrapper (schema mirror lives here); keep it in sync with new RPCs.
- `test_daemon.py` is the existing test suite — extend it.

## Build (three primitives)
1. **Shared debate-thread** (daemon.py + proxy.py mirror): an append-only `debate_posts` table
   (cols: thread_id, seq monotonic per thread, author_session, role, payload_json, ts) + RPCs
   `thread_open(thread_id, members)`, `thread_post(thread_id, author, role, payload)`,
   `thread_read(thread_id, since_seq)` → ordered posts after since_seq. Many members read/write ONE thread.
2. **Push** (start with ZERO daemon change): a client-side long-poll `bridge-watch.sh` (+ small py helper)
   that blocks on `thread_read(since_seq)`/`board` and fires when a new post/message arrives, so a session
   is *pushed* a reply instead of hand-polling. THEN, additively and FAIL-OPEN, add an optional `poll_wait`
   long-poll RPC to the daemon's selector loop (a real waiter registry) — must be byte-identical/no-op when unused.
3. **Wire ack + idempotency**: route delivery through the existing `ack`/`seq` path and wire `idempotency.py`
   so a redelivered post is de-duplicated (at-least-once → effectively-once for the reader).

## Acceptance — FAIL-ON-REVERT (extend test_daemon.py; each must go RED when the change is reverted)
- `thread_open/post/read`: multiple authors post to one thread; `thread_read(since_seq)` returns them in
  seq order with no gaps/dupes; seq is monotonic per thread.
- ack/idempotency: a duplicated `thread_post` (same idempotency key) is stored once; reader sees one.
- poll_wait (if added): a blocked reader is released within X ms of a new post; and with poll_wait unused the
  daemon behaves byte-identically to baseline (regression guard).

## E2E PROOF — green is NOT proof (the real deliverable)
Boot the daemon on a SCRATCH DB + spare port. Start **two** independent client processes (mock critics C1, C2).
Run a real debate round WITHOUT any central relayer:
  C1 `thread_post` an argument → C2 is PUSHED (via `bridge-watch.sh`, not a hand-poll) → C2 `thread_read`s it,
  posts a rebuttal → C1 is pushed C2's rebuttal → a consensus/verdict post is appended.
Dump the final ordered thread contents and the two watchers' wake events. Show that neither client polled in a
busy loop and no third "relayer" process moved messages. Paste the REAL transcript (not a description).

## LAST STEP (required)
- Run the FULL suite pipe-free: `python3 -m pytest test_daemon.py -q; echo "EXIT=$?"` → must be 0. (NEVER `| tail` before reading `$?`.)
- `git add -A && git commit` on `feat/bridge-push-debate`; report the SHA.
- Do NOT restart the live daemon. Do NOT push. Do NOT merge. (deliberate, separate line.)
- Write `/home/stack/charon-private/fleet/state/overnight/BRIDGE-PUSH-BUILD-REPORT.md`: files+lines changed,
  the fail-on-revert test list, the REAL E2E debate transcript, pytest EXIT code, branch SHA, and any deviation
  from this brief. Flag explicitly that the new push/thread primitives need an adversarial review (concurrency /
  race / lost-wakeup) before the live daemon is redeployed.
- Print `PACKET: fleet/state/overnight/BRIDGE-PUSH-BUILD-REPORT.md` + an ≤8-line honest summary. Real outputs only — never a fabricated SUCCESS line.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
