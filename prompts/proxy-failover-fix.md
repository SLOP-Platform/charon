# PROXY-FAILOVER-FIX — Phase 1 (P1 + P5 ONLY)

Bounded `Retry-After` on the terminal 503 / 402·429 relays (**P1**) + browser-like outbound
User-Agent so Cloudflare-fronted providers stop 403ing (**P5**). Header-only, low-risk,
**NOT** money-path. This tab builds **Phase 1 only** — do NOT build P2 (cross-model/tier
substitution), P3 (balance-aware demotion), or P4 (that is a live-config pass done separately).

Design of record (read it first): `/home/stack/charon-private/scratch/failover-root-fix-design.md`
— sections **§2 P1** and **§2 P5** carry the exact mechanism, anchors, and acceptance tests.
Product source of record: `/home/stack/code/charon/src/charon/`.

Branch: `fix/proxy-failover`. Work in the Charon repo at `/home/stack/code/charon`.

---

## Scope: the two changes

### P1 — Bounded `Retry-After` on 503 (and on 402/429/503 relays)
Goal: the GATEWAY owns retry cadence — a transient dual-402 can never become an ~8h client
backoff stall. Purely header emission; no routing or spend logic changes.

Anchors (verify by grep at build time — line numbers may have drifted a few lines):
- `src/charon/proxy_server.py` `_send_resp_headers` **def ~line 483** (signature:
  `_send_resp_headers(self, status, ctype, provider, failovers, downgrade, cache_status=None)`).
- Terminal 503 synth: the `if failovers:` branch that calls `_send_resp_headers(503, ...)`
  and writes `all_providers_exhausted` (**~line 827**, design cites :826).
- Single-upstream relay: `self._send_resp_headers(status, ctype, route.label, failovers, False)`
  right after (**~line 840**, design cites :838) — relays a raw upstream non-200 as-is.
- Cooldown state: `self._cooldown` maps `route.upstream_base -> absolute monotonic expiry`
  (`set_cooldown` ~line 1146 stores `time.monotonic() + secs`, already clamped to
  `self.max_cooldown_s`); `self.default_cooldown` and `self.max_cooldown_s` already exist.
  `order_by_cooldown` (~line 1130) is the bucketing helper.

Implement:
1. Add optional param `retry_after: int | None = None` to `_send_resp_headers`. When it is
   truthy and `> 0`, emit `self.send_header("Retry-After", str(int(retry_after)))` **before**
   `self.end_headers()`. All existing callers keep today's behavior (param defaults to None →
   no header).
2. Add a small server method `retry_after_hint(self, chain) -> int`: over the chain's members,
   compute the soonest recovery from `self._cooldown`
   (`min(expiry - now)` across cooled members, `now = time.monotonic()`); when no member is
   cooled, fall back to `self.default_cooldown`; **clamp the result to `[1, self.max_cooldown_s]`**
   and return an `int`. (Guard the read with `self._cooldown_lock`, matching `order_by_cooldown`.)
3. At the terminal 503 call, pass `retry_after=srv.retry_after_hint(ordered)` (the already-ordered
   chain used by the serve loop — use whatever local holds the `order_by_cooldown(chain)` result;
   confirm the variable name in context).
4. At the single-upstream relay call, when `status in (402, 429, 503)` pass
   `retry_after=min(obs.retry_after or srv.default_cooldown, srv.max_cooldown_s)` so a raw upstream
   `Retry-After: 3420` is re-bounded to ≤ `max_cooldown_s` before it reaches the client.
   Do **NOT** set `retry_after` on `400/401/403` (client/auth errors — retrying does not help) or
   on any 2xx path.

### P5 — Browser-like outbound User-Agent (Cloudflare 1010 bot-block)
Goal: stop marking healthy, funded providers dead because a Cloudflare edge 403s a non-browser
UA. Live-confirmed (`scratch/six-provider-verify.md`): `groq`/`cerebras`/`together` return
HTTP 403 "error code: 1010" on `charon-proxy/0.1`; a browser-like UA flips all three to 200.

Anchors:
- `src/charon/proxy_server.py:71` `_DEFAULT_UA = "charon-proxy/0.1"` (NOT browser-like — this is
  the bug).
- `:74` `_BANNED_UA_PREFIXES = ("python-urllib", "python-requests")` (leave semantics; it only
  guards library-default UAs).
- `:542-546` serve-path egress: forwards the client UA when present + non-banned, else
  `_DEFAULT_UA`.
- `src/charon/balance.py:41`, `:70`, `:100` — deepseek / openrouter / nanogpt pollers each
  hardcode `req.add_header("User-Agent", "charon-proxy/0.1")`.

Implement:
1. Promote ONE shared **browser-like** UA constant so it cannot drift. Preferred: lift it to a
   tiny shared location both modules import (e.g. keep it defined in `proxy_server.py` and import
   it into `balance.py`, or a minimal shared symbol) — do NOT create two independent literals.
   Make `_DEFAULT_UA` browser-like (a current mainstream Chrome-on-Windows UA string is fine;
   pick one realistic value and comment WHY). The serve-path fallback at `:546` then uses the
   browser-like default automatically.
2. Replace the three hardcoded `"charon-proxy/0.1"` strings in `balance.py` (`:41/:70/:100`) with
   the shared constant.
3. Sweep the other urllib callers for any outbound provider/probe request that still sends a
   default/non-browser UA and fold them onto the same constant **only where they make an outbound
   provider/probe call**: `discover.py`, `connect.py`, `providers.py`, `recommend.py`,
   `observability.py`, `routing_proxy.py`, `speculative_execution.py`. The three balance pollers +
   the serve-path default are the confirmed-critical ones; the sweep is best-effort for the rest —
   do not invent new outbound calls, just normalize existing ones. Note in the PR which files you
   touched.
   (Per-provider UA override for the forwarded-client-UA case is an explicit fast-follow — OUT of
   scope here.)

---

## Acceptance tests (add/extend — must pass)

`tests/test_proxy_server.py` and `tests/test_balance.py`:

P1:
- Dual-402 pool → terminal 503 response carries a `Retry-After` header, integer-valued,
  `1 ≤ value ≤ 120` (= `max_cooldown_s`).
- Single-upstream `429` whose upstream `Retry-After: 3420` → the relayed header is clamped to
  `≤ 120`.
- A `400`/`401`/`403` relay carries **NO** `Retry-After` header.

P5:
- An outbound request built for a Cloudflare-fronted provider (groq/cerebras/together path)
  carries a browser-like UA — asserted NOT to start with `python-urllib` and NOT equal to
  `charon-proxy/0.1`.
- Each balance poller's built request (`balance.py` deepseek/openrouter/nanogpt) carries the
  shared browser-like UA constant.

Run the full ticket accept gate before committing:
```
PYTHONPATH=src python3 -m pytest tests/test_proxy_server.py tests/test_balance.py -v -q
```
Do not regress any other test: `PYTHONPATH=src python3 -m pytest -q` should stay green.

---

## Guardrails
- **Blast radius:** both changes are header-only / outbound-only. No routing decision, pool
  ordering, chain resolution, or spend logic changes. Do not touch `chain_for`,
  `order_by_cooldown`'s bucketing, `set_cooldown`'s clamp math, or any money-path code — those
  belong to P2/P3 (later phases).
- **Default-preserving:** every existing `_send_resp_headers` caller that does not pass
  `retry_after` must emit byte-identical headers to today.
- **Product ships STANDALONE.** Touch ONLY product-internal surfaces under `src/charon/` and
  their tests. Do NOT import or reference anything under the fleet/SLOP/build-rig, and do NOT
  introduce any `/home/stack` path, hostname, token, IP, or dev-meta into product source or tests
  (public repo). No new runtime dependency — stdlib `urllib` only.

## Dependencies & sequence
- **depends_on:** none. Phase 1 (P1 + P5) is self-contained — no build/correctness prereq.
- **Wave / concurrency safety:** this ticket owns `src/charon/proxy_server.py`,
  `src/charon/balance.py`, `tests/test_proxy_server.py`, `tests/test_balance.py`. `proxy_server.py`
  and `tests/test_proxy_server.py` are HOT files shared with several other live board tickets
  (GUI-SVELTE-BUILD, DRAIN-ROUTING, INC-401-FAILOVER, RFL-2/3/4, SR-13, SR-6). **Single writer
  rule:** no other tab may edit `proxy_server.py` concurrently — this ticket must run in a wave by
  itself with respect to that file (see the board collision check; the competing tickets are
  parked or sequenced before this launches). Edits here are a small, well-anchored header/UA diff,
  cheap for those larger tickets to rebase on top of afterward.
- **Internal order:** P1 and P5 are independent; do both in this one tab, one commit.

## LAST STEP (required)
Commit all changes on branch `fix/proxy-failover` with a clear message, then report the commit
SHA back in your final message.
do NOT push or merge.

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
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
