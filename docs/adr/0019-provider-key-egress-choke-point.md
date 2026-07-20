# ADR-0019 — Provider-key egress: why six rounds failed, and what actually lands

**Status:** Accepted (INTERIM / STOPGAP — see §5 and §6)
**Date:** 2026-07-20
**Supersedes:** nothing. **Superseded by:** the credential-injecting reverse-proxy
(credproxy) phase, which carries the real invariant; and the LiteLLM adopt
(ADR-0017), if it lands.

> **READ THIS FIRST — THE CHOKE POINT IS A CONVENTION, NOT AN ENFORCED
> INVARIANT.** Six rounds tried to enforce "only `netutil` may send a
> key-bearing request" mechanically. Every one was broken. Round 6's attempt —
> a Semgrep denylist plus a gate — was **not landed**, because the gate scanned
> zero files while printing `key-egress OK`, and its own test suite asserted the
> defect as a requirement. What this ADR describes is a set of helpers that make
> the safe path the easy path, plus a genuinely-enforced secret model (§2). It is
> exposure reduction. **The vulnerability in §1 is NOT closed by this ADR.** The
> invariant that closes it — that the gateway process holds no provider
> credential at all — lands in the credproxy phase. Do not cite this document as
> evidence that provider-key egress is prevented.

---

## 1. Context — the vulnerability

Charon holds provider API keys and forwards requests to provider endpoints on the
operator's behalf. A provider entry is a `(base_url, key)` pair. The original
storage model keyed secrets by the *name of an environment variable* (`key_env`),
not by the provider:

```
secrets.json   {"OPENROUTER_API_KEY": "sk-real-..."}     # keyed by ENV VAR NAME
providers.json {"openrouter": {"base_url": "...", "key_env": "OPENROUTER_API_KEY"}}
```

Because `key_env` is a shared namespace, **anyone who could write a provider entry
could point an arbitrary `base_url` at an existing `key_env`** and have Charon send
somebody else's key to a host of their choosing. The web setup handler was
remotely reachable, so this was a live exfiltration primitive, not a theoretical one.

The structural defect: **validation happened HERE and sending happened THERE.** The
handler validated a key against the base it was told about; a different code path
later resolved `os.environ[key_env]` and sent whatever it found to whatever
`base_url` was persisted. Nothing tied the two together.

---

## 2. The novel slice — what survives any substrate swap

If every line of transport code in this repository is deleted and replaced with a
third-party client, **these three things must be carried forward**. They are the
part that is about Charon's data model, not about urllib.

### 2a. Per-provider secrets keyed by provider id

```
secrets.json   {"provider:openrouter": "sk-real-...",
                "provider-base:openrouter": "https://openrouter.ai/api/v1"}
```

A secret belongs to a **provider id**, never to an env-var name. There is no
shared namespace, so there is nothing to alias into. `key_env` survives only as a
**read-only legacy hint** for `.env`-based deployments — it is never a write
target.

### 2b. The base-binding invariant, enforced ON READ

Every stored key carries the base it was stored for, and `get_provider_key()`
**fails closed** if that binding is absent or does not match the base being
resolved. This is the load-bearing invariant. Enforcing on read rather than on
write is deliberate: a write-time check is only as good as the enumeration of
write paths, and §3 is the story of enumeration failing five times. An overlooked
write path into `providers.json[name]["base_url"]` no longer exfiltrates anything,
because the read side refuses to hand over a key whose binding does not match.

Base comparison is by **normalised origin** — IDNA rather than `str.lower` (the
Kelvin-sign case), default-port equivalence, trailing dot, trailing slash. A
naive `.rstrip("/")` comparison was bypassable.

### 2c. The legacy env fallback is base-bound too

`.env` deployments still work, but a legacy `key_env` value is only sendable to a
base that a **built-in preset** binds that env var to. Presets are static in-repo
data and therefore a usable trust anchor; the persisted provider config is
attacker-writable and is not.

One deliberate exception: an **unclaimed** `key_env` (no preset claims it) stays
sendable to any base. This keeps the documented
`charon gateway --config charon.toml` deployment working, and buys an attacker
nothing — the web setup handler discards a caller-supplied `key_env` outright and
the `models` action never accepts one, so a remote caller cannot create one.

---

## 3. The failure history — six rounds, six bypasses

**This is the most important section of this document.** Each round's fix looked
obviously correct to the person who wrote it AND to at least one reviewer. If you
are re-deriving this fix from scratch, you will probably reproduce one of these.

| Round | The fix | Why it failed |
|---|---|---|
| 3 | Guard the setup handler: reject a repoint whose `key_env` is already owned by another provider. | Shape-based. It checked the *relationship between entries*, not the key↔base binding, and the several other write paths into `providers.json` were untouched. |
| 4 | Add the coupling guard `if key_env and not key and effective_base:` | **Skipped entirely whenever the attacker supplied a key.** POST a provider with `key_env=OPENROUTER_API_KEY` and `key=sk-attacker-own`: the guard does not run, the probe validates the attacker's own key against the attacker's own base, the entry persists, and `models/import` then reads `os.environ[OPENROUTER_API_KEY]` — the REAL key, because `apply_to_env` uses `setdefault` — and sends it to the attacker. The original vulnerability, through the same handler the fix targeted. |
| 4 (review) | Two independent adversarial reviews. | Both missed four send sites. See §4. |
| 5 | Hand-enumerate every send site and route it through a `netutil` choke point. | The enumeration was finally complete, but the **enforcement** was a hand-rolled AST linter written against the two call spellings that happened to exist. A reviewer EXECUTED a full exfil sender that it passed with exit 0. |
| 6 | Replace the linter with Semgrep; fix the gate's own holes. | **Three ways.** (a) The gate passed `src tools tests` as explicit targets, so semgrep resolved paths per target root and every `paths.include` glob matched nothing: it scanned **0 files** and exited 0 printing `key-egress OK`. (b) A reviewer built a 16-shape corpus — raw sockets, `getattr`/`importlib`/`__import__`, `functools.partial`, subprocess `curl`, `urlretrieve`, `FancyURLopener`, `asyncio`, `aiohttp`, `urllib3`, and subclassing `Request`/`HTTPSConnection` — and **all 16 passed** the rule. `Request` subclassing is the idiom round 6 itself introduced at `netutil.py`'s `_KeyedRequest`. (c) Three runtime bypasses using only sanctioned APIs, proven on the wire: `add_unredirected_header`, direct `req.headers[...]` assignment, and rewriting `req.full_url` after `validate_base_url` ran — the last makes the SSRF check a time-of-check/time-of-use bug on a genuinely-keyed request. |
| 6 (landed subset — this ADR) | Land only what survived review; drop the gate; state the limit honestly. | See the banner above. |

### Round 5's gate, specifically

The linter nested both of its checks inside
`isinstance(node.func, ast.Attribute)`, so **every bare-name call was invisible**:

```python
from urllib.request import Request, urlopen
_A = "Authorization"
def send(url, key):
    r = Request(url); r.add_header(_A, "Bearer " + key); return urlopen(r, timeout=30)
```

`urlopen` uses the default opener, which follows 302 **with the Authorization
header attached** — byte-for-byte the round-4 forwarder bug, reintroduced with
zero gate noise. It also:

- exempted any path *ending* in `charon/netutil.py`, so
  `src/charon/adapters/charon/netutil.py` was a gate-free zone;
- was invoked with no argument, so it rooted at `src/` and **never scanned
  `tools/` or `tests/`** — and `tools/` is shipped, operator-run, key-bearing code;
- required the header name to be an `ast.Constant`, so `"Auth" + "orization"`,
  an f-string, or a variable all walked past;
- knew nothing about `http.client`, `socket`, `requests`, or `httpx`;
- **had no test of its own**, which is how a gate that caught exactly two
  spellings was described as "structural" for an entire round.

### The lesson — name the quantifier, or round 7 fails identically

Every round stated the property as **∀ code in `src/`: the provider key does not
reach a non-provider host**, then enforced it with a **finite, fail-open
enumeration** of that set — call sites by hand, then an AST linter, then a
Semgrep denylist of transport *names*. Two structural properties make this
unwinnable:

1. **Fail-open.** An unlisted transport *passes*. The space of ways Python can
   move bytes is not enumerable, so every addition to the vocabulary is a patch.
2. **The verifier shares a trust domain with the thing verified.** Round 6's gate
   examined zero files and printed OK, and its own test asserted the buggy
   constant as a requirement — pinning the defect such that fixing the gate broke
   its test. Six rounds of green were, in aggregate, receipts for work that did
   not happen.

The one thing that has held is **§2 — the invariant enforced ON READ**, which is
quantified over a small, finite, inspectable object (the secret store) rather
than over an unbounded set of code paths, and which fails CLOSED.

**The fix is to change the quantifier, not to improve the enumeration.** Under
credproxy the property becomes *"the gateway process possesses no provider
key"* — one assertion over one object. Every one of the 19 bypasses above then
becomes a non-event, not because it was anticipated, but because there is
nothing in reach to steal.

---

## 4. The reviewer-fallibility record

**Two independent adversarial reviewers reviewed round 4. Both missed the same
four key-bearing send sites:** `routing_proxy.py`, `speculative_execution.py`,
`adapters/review.py`, `observability.py`.

Round 5's own reviewer then found that round 5's gate — the thing meant to make
further misses impossible — was itself evadable, and demonstrated it with executed
code.

State this plainly, because it is the part most likely to be re-invented:
**hand-enumeration does not converge, and adding more reviewers does not make it
converge.** Three careful passes over the same code by three different people
produced three different incomplete lists. Do not accept "I checked all the call
sites" — from a person or from a model — as evidence for this class of bug.

Nor is "the gate is green" evidence, which is round 6's contribution to this
record: the gate was green because it examined nothing. Accept only a property
that fails CLOSED, quantified over an object small enough to inspect — and a gate
that reports how much work it actually did (§5.7).

---

## 5. Decision

1. **One choke point.** `src/charon/netutil.py` is the only module that may
   construct or send an outbound request. `keyed_request()` is the only
   constructor of credential-bearing requests; `open_keyed()` is the only sender.
2. **Capability, not a stamp.** `keyed_request` returns a private
   `_KeyedRequest` subclass and `open_keyed` does an `isinstance` check. Round 5
   used `setattr(req, "_charon_keyed", True)`, which any caller could forge in one
   line, making the "only constructor" claim false.
3. **No redirects, ever.** `open_keyed` uses `build_opener(_NoRedirect())`.
   urllib does **not** strip `Authorization` cross-host, so a 302 from an upstream
   would hand the operator's key to whatever the `Location` names. A refused
   redirect is logged at WARNING naming the declined host, and classified as
   `failover=True` — round 5 refused the redirect but relayed a bare, empty 30x to
   the agent with no failover and no log line.
4. **SSRF validation on the base, by parsed address rather than by string.** See §7.
5. **There is NO gate, and the choke point is NOT mechanically enforced.** This
   is a decision, not an omission. The Semgrep gate built for round 6 was
   **dropped rather than landed**: it scanned zero files while reporting OK, its
   rule was a fail-open denylist that 16 transport spellings walked past, and its
   test suite pinned the defect as a requirement. Shipping it would have added a
   seventh false receipt to a merge path already carrying six. **An honest absent
   gate is strictly better than a gate that certifies nothing while looking
   green.** Treat "every send site goes through `netutil`" as a convention
   maintained by review, and verify it by reading the diff.
6. **`keyed_request` / `open_keyed` are convenience, not a boundary.** They carry
   `_NoRedirect`, the shared UA and base validation to every site, which is real
   value. They do **not** make an unsafe request unrepresentable: the object they
   return is mutable, so `add_unredirected_header`, `headers[...] = ...` and
   `full_url = ...` all reach the wire with the key attached, past the
   `isinstance` check and past `validate_base_url`. No static rule can see any of
   those — they happen at runtime on a well-formed object. Closing them requires
   either an immutable request plus re-validation inside `open_keyed`, or (better)
   removing the credential from the process entirely.
7. **The general defect that produced six false greens IS fixed, at the class
   level.** Two mechanisms, both in this branch, neither specific to this
   vulnerability:
   - **Same-tree** (`tools/run_gate.py`, `gate_runner._verify_same_tree`). The
     gate list came from the installed module while the check scripts were shelled
     CWD-relative, so a worktree run validated the *main checkout's* gate list —
     a branch's new gate silently never ran, and the run still printed "all checks
     passed". The repo-local runner cannot resolve to a different checkout;
     the runtime guard refuses to report a pass when they disagree.
   - **Zero work units** (`tools/gate_contract.py`). Every scanning gate declares
     `min_work_units` in `tools/gates.json`, emits `WORK-UNITS: <n>`, and the
     runner fails CLOSED when the count is missing or short — *even on exit 0*.
     "Examined nothing and passed" and "examined the tree and passed" are no
     longer the same receipt. Assert on the COUNT, never on a gate's source text:
     round 6's test asserted the literal `SCAN_TARGETS` value and thereby made
     fixing the gate a test failure.

---

## 6. STOPGAP — this code should be DELETED, not ported

**The hand-rolled transport hardening in `netutil.py` exists only because the core
is stdlib-only today.** `pyproject.toml` declares `dependencies = []` — the
privileged loop carries no unvetted third-party code (reconciliation BR-3).
Adding a runtime dependency would be the first breach of that invariant and is
being decided separately, on its own ADR.

If the **LiteLLM adopt (ADR-0017)** lands, the substrate provides natively what
this module hand-rolls:

| Hand-rolled here | Substrate equivalent |
|---|---|
| `_NoRedirect` opener | `httpx` does not follow redirects by default |
| "urllib does not strip Authorization cross-host" | `requests` strips it via `Session.rebuild_auth` |
| `keyed_request` / `open_keyed` | the client's own request/session API |

**When that happens, delete `_NoRedirect`, `_KeyedRequest`, `keyed_request` and
`open_keyed` rather than porting them.** Do not invest another round in
`netutil` — it is scheduled for removal under both ADR-0017 and the credproxy
phase, and every round spent hardening it has been spent on code with a deletion
date.

**What must NOT be deleted** is §2 — the per-provider secret model, the
base-binding invariant enforced on read, and the base-bound legacy fallback. Those
are Charon's, not the transport's, and no HTTP client provides them.

---

## 7. SSRF: fix the class, not the literal

Round 5 (and every round before it) guarded with:

```python
if host.startswith("169.254.") or host == "metadata.google.internal":
```

That is a **string** match against one spelling of an address the C resolver
accepts in several. All of these reach 169.254.169.254, the cloud-metadata
endpoint, and all of them passed:

| encoding | example |
|---|---|
| decimal | `http://2852039166/` |
| hex | `http://0xA9FEA9FE/` |
| octal | `http://0251.0376.0251.0376/` |
| 2-part inet_aton | `http://169.16689662/` |
| IPv4-mapped IPv6 | `http://[::ffff:169.254.169.254]/` |

The fix parses the host to a normalised address and classifies it with the stdlib
`ipaddress` module. Two non-obvious details, both of which cost a bug:

- **`ipaddress.ip_address` is deliberately STRICT** and rejects every permissive
  encoding above (zero-padded octets became a ValueError in a 2021 CVE fix). But
  `socket`/`inet_aton` — what urllib actually connects through — accepts them all.
  So the guard must reimplement inet_aton's permissive parsing. This is validated
  by a **differential test against `socket.inet_aton` itself** rather than a
  hand-listed corpus, because a hand-listed corpus is how the original guard came
  to cover exactly one spelling.
- **`ipaddress.ip_address("::ffff:169.254.169.254").is_link_local` is `False`** —
  IPv6 link-local means fe80::/10. The embedded IPv4 address must be unwrapped
  and classified in its own right.

### Scope decision: RFC1918 and loopback stay ALLOWED

Blocked in all encodings: **link-local, multicast, reserved, unspecified**, plus
the known metadata hostnames.

**Not** blocked by default: loopback and RFC1918. This is deliberate and is a
product constraint, not an oversight — the `lmstudio`, `jan`, `ollama`, `vllm` and
`local` presets all ship `http://localhost:PORT/v1` bases, and a self-hosted
gateway reaching an Ollama box on the LAN is the product's normal case. Blocking
RFC1918 wholesale would brick all five. Callers that genuinely need public-only
egress pass `validate_base_url(..., allow_private=False)`.

(`ipaddress.ip_address("::1").is_reserved` is `True`, so loopback must be exempted
*before* the reserved check or `http://[::1]:PORT` — the IPv6 spelling of those
preset bases — is silently refused.)

### KNOWN RESIDUAL RISK — DNS rebinding

`validate_base_url` checks the base **at the moment it is written**; the
connection resolves the hostname **again** at send time. A hostname that answers
with a public IP during validation and `169.254.169.254` at connect time defeats
every check in this ADR.

**In-process base validation cannot close this class.** Nothing in this repository
mitigates it today, and no amount of parsing will.

The mitigation is at the **network layer**: an egress allowlist enforced outside
the process — an outbound proxy, or a container egress policy — with the allowlist
derived from the existing provider manifest. Under that control the whole class is
unexploitable regardless of what in-process validation concludes, because a
rebound name simply cannot be reached. That is the named path forward; it is not
built.

---

## 8. Consequences

- One module to audit for egress instead of nineteen call sites. That is a
  review-cost reduction, not a guarantee.
- A new send site is **NOT** a gate failure. It is a review miss, and three
  independent reviewers have already demonstrated they miss them. This is the
  honest cost of dropping the gate, and it is accepted only because the gate that
  was on offer detected nothing.
- Every outbound call goes through one function, so a bug there is a bug
  everywhere. Mitigated by that function being small.
- `.env` deployments and the five localhost presets keep working unchanged, as do
  `0.0.0.0`/`::` bind-address bases (a regression introduced and then reverted
  within round 6).
- **Still exploitable after this ADR:** an attacker who can persist a provider
  entry through the token-gated `/charon/*` surface still causes the key to be
  sent to a host they chose, because the key is still in the process and the base
  is still attacker-supplied data. DNS rebinding (§7), the three runtime request
  mutations (§5.6), and LAN SSRF via RFC1918 bases all remain open. All of them
  close in the credproxy phase and none of them close here.
