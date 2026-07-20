# ADR-0019 — Provider-key egress: one choke point, and why five rounds failed

**Status:** Accepted (STOPGAP — see §6)
**Date:** 2026-07-20
**Supersedes:** nothing. **Superseded by:** the LiteLLM adopt (ADR-0017), if it lands.

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

## 3. The failure history — five rounds, five bypasses

**This is the most important section of this document.** Each round's fix looked
obviously correct to the person who wrote it AND to at least one reviewer. If you
are re-deriving this fix from scratch, you will probably reproduce one of these.

| Round | The fix | Why it failed |
|---|---|---|
| 3 | Guard the setup handler: reject a repoint whose `key_env` is already owned by another provider. | Shape-based. It checked the *relationship between entries*, not the key↔base binding, and the several other write paths into `providers.json` were untouched. |
| 4 | Add the coupling guard `if key_env and not key and effective_base:` | **Skipped entirely whenever the attacker supplied a key.** POST a provider with `key_env=OPENROUTER_API_KEY` and `key=sk-attacker-own`: the guard does not run, the probe validates the attacker's own key against the attacker's own base, the entry persists, and `models/import` then reads `os.environ[OPENROUTER_API_KEY]` — the REAL key, because `apply_to_env` uses `setdefault` — and sends it to the attacker. The original vulnerability, through the same handler the fix targeted. |
| 4 (review) | Two independent adversarial reviews. | Both missed four send sites. See §4. |
| 5 | Hand-enumerate every send site and route it through a `netutil` choke point. | The enumeration was finally complete, but the **enforcement** was a hand-rolled AST linter written against the two call spellings that happened to exist. A reviewer EXECUTED a full exfil sender that it passed with exit 0. |
| 6 (this one) | Replace the linter with Semgrep; fix the gate's own holes. | — |

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

### The lesson

Every round's fix was a *better enumeration*. Enumeration does not converge. The
only thing that has held is **making the unsafe request unrepresentable** and
**enforcing the invariant on read**, where correctness does not depend on having
listed every site.

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
sites" — from a person or from a model — as evidence for this class of bug. Accept
only a mechanically-enforced structural property plus a gate with a RED-proof
corpus.

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
5. **The gate is Semgrep** (`tools/semgrep-key-egress.yml`, run by
   `tools/check_key_egress.py`), scanning `src/`, `tools/` and `tests/`, wired into
   both the gate suite and CI. Semgrep is a CI/lint tool, never a runtime import,
   so it does **not** breach the stdlib-only core (`pyproject.toml`
   `dependencies = []`). It resolves import aliases natively — the specific
   property the hand-rolled linter could not cheaply reproduce.
6. **The gate fails loudly when absent.** `check_key_egress.py` exits 2, not 0,
   if semgrep is not installed. A green CI that never invoked the check is the
   known failure mode.
7. **The gate has a RED-proof corpus.** `tests/fixtures/key_egress/` holds every
   documented evasion; `tests/test_key_egress_gate.py` asserts each goes RED and
   that sanctioned `netutil` usage stays GREEN. A rule that matches nothing cannot
   pass this suite.

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
| `tools/semgrep-key-egress.yml` urllib patterns | retarget the same rules at the adopted client |

**When that happens, delete `_NoRedirect`, `_KeyedRequest`, `keyed_request` and
`open_keyed` rather than porting them.** Retarget the Semgrep rules at the adopted
client so the choke-point property survives the swap.

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

- One module to audit for egress instead of nineteen call sites.
- A new send site is a **gate failure**, not a silent reintroduction.
- Cost: every outbound call goes through one function, so a bug there is a bug
  everywhere. Mitigated by that function being small, and by the RED-proof corpus.
- The gate needs semgrep installed. It fails loudly rather than skipping.
- `.env` deployments and the five localhost presets keep working unchanged.
- DNS rebinding remains open (§7) and is the top candidate for the next pass.
