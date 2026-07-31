# MONEY-PATH ADVERSARIAL REVIEW — agen-kolar (2026-07-24, read-only)

Independent review. Nothing edited/committed/pushed in either repo. All work in scratchpad.

| Target | Verdict |
|---|---|
| T1 `4b9d401` `fix/litellm-order-precall` (LITELLM-WIRE, unlanded) | **LAND-WITH-NITS** |
| T2 `4f33f87` / PR #264 merge `128605a` (rig broker, landed) | **SAFE — NEEDS-FOLLOWUP** |

Method key: **[EXEC]** = I ran it and observed the result. **[READ]** = code reading only.

---

## TARGET 1 — litellm `order` + `enable_pre_call_checks`

### What I proved by execution

1. **[EXEC] The suite is green as-shipped.** `pytest tests/test_litellm_router_e2e.py` in
   `/home/stack/code/charon-wt-LITELLM-WIRE` → **10 passed in 6.30s**.

2. **[EXEC] The 300/0/0 measurement is NOT vacuous — red-proof run.** I loaded a pytest plugin
   that strips `litellm_params['order']` and forces `enable_pre_call_checks=False` (feature
   reverted, source untouched). Result: **6 failed, 4 passed** — every one of the six new tests
   went RED, the four pre-existing ones stayed green. Concretely:
   - `test_e2e_first_leg_is_deterministic_not_shuffled` FAIL
   - `test_e2e_selection_follows_charon_chain_order_not_insertion_luck` FAIL
   - `test_e2e_funding_class_preorder_binds_free_leg_first` FAIL (`KeyError: 'order'`)
   - `test_e2e_order_stays_contiguous_when_a_control_drops_a_leg` FAIL
   - `test_e2e_leg_too_small_for_prompt_is_skipped_for_the_next_one` FAIL
   - `test_e2e_prompt_over_every_leg_fails_loud_without_dialing_anything` FAIL
   The tests measure hits on real loopback HTTP servers, not router internals. **Non-vacuity
   confirmed by execution.**

3. **[EXEC] Ordered FAILOVER is real and is strictly ascending — the diff's untested claim,
   now tested.** The diff asserts ordered failover in a docstring but ships **no failover
   test**. I built one (3 legs, one router, 30 completions):
   - leg1 always HTTP 500 → hits `{leg1: 5, leg2: 30}`, **leg3 never dialed**, 0 caller errors.
   - leg1 AND leg2 always 500 → hits `{leg1: 5, leg2: 5, leg3: 30}`, 0 caller errors.
   So order-1 exhausts its retries, then the chain rolls to order-2, then order-3 — never a
   random survivor. The claim holds under real HTTP failure.

4. **[EXEC/READ] `order` cannot leak to the provider payload.** `order: Optional[int]` is a
   declared field of litellm's params model (`litellm/types/router.py:366`), so it is a
   router-level key, not forwarded as an unknown kwarg. No 400s observed in 300+ live-loopback
   completions.

5. **[READ] The litellm mechanism matches the claim.**
   `litellm/utils.py:4475-4485` `_get_deployment_order` reads `litellm_params['order']` first,
   then `model_info['order']`. `litellm/router.py:10345-10349` and `:10748-10752` apply order
   filtering **after** `_pre_call_checks` (`:10329`, `:10740`) — so the diff's "context filter
   runs first, then order narrowing" ordering claim is correct as written.

### Findings

**T1-N1 (nit, docstring overstates) — pre-call checks fail OPEN on a token-counter error.**
`litellm/router.py:9896-9902`: if `litellm.token_counter` raises, `_pre_call_checks` does
`return _returned_deployments` — the **full, unfiltered** list. Failure scenario: a prompt shape
tiktoken chokes on (odd content parts / very large multimodal payload) silently disables the
context filter for that request, and `order` then pins it to the order-1 leg whose `max_context`
cannot hold it — exactly the wasted-request outcome the change claims to prevent. The
`make_router` docstring at `src/charon/litellm_plane/litellm_router.py:381-390` says the leg "is
dropped ... BEFORE selection, and if no leg fits litellm fails loud". That is true only when
counting succeeds. Not a spend control (it wastes one request, it does not misroute money), but
the docstring should not claim unconditional fail-loud. Same block is skipped entirely when
`messages is None` (embeddings/text-completion), which the docstring also does not say.

**T1-N2 (nit, latency-is-a-failure-class lens) — the flag puts tiktoken on the hot path.**
`enable_pre_call_checks=True` makes litellm run `litellm.token_counter(messages=...)` once per
request for any model group where at least one deployment declares `max_input_tokens` — i.e.
every chain whose routes carry `max_context` (`litellm_router.py:156-158`). Per-request CPU on
large prompts. Uncontroversial trade, but it is a new per-request cost with no measurement in
the diff.

**T1-N3 (nit, behaviour-surface expansion) — the flag turns on more than the context filter.**
`_pre_call_checks` (`litellm/router.py:9836-9849`) also filters on RPM limits and region.
Charon sets neither today so it is a no-op, but the docstring frames the flag as purely "the
switch that makes `max_input_tokens` live". If an rpm/region field is ever added to a
deployment it silently becomes a routing filter.

**T1-N4 (risk, code-read only, NOT reproduced) — litellm's order fallback fails OPEN when a
target level is unhealthy.** `litellm/utils.py:4489-4494`: with an explicit `target_order`, if
no deployment matches that level it **returns all healthy deployments** (comment: "target_order
doesn't match any deployment — return all"), and the shuffle strategy then picks among them.
Scenario: order-1 errors → fallback targets order-2 → order-2 is in cooldown from an earlier
request → the filter matches nothing → the request is served by a *random* remaining leg (which
may be a costlier one) with no diagnostic. My two probes did not hit this (the failing legs were
always still "healthy" in litellm's book). Worth a probe before the live cutover, not a blocker.

**T1-N5 (design question the diff does not resolve) — `order` is a STATIC declared sequence,
not live usage-capability.** `build_model_list` assigns rank 1..N once, at Router construction
(`litellm_router.py:180-192`). It encodes funding-class + parked-exclusion as computed at that
moment. It does **not** encode "cheapest USAGE-capable first": remaining balance, quota
exhaustion and gateway capped-state are only reflected if the Router is rebuilt. Roll-to-next
therefore happens **only on an upstream ERROR** (verified in #3 above). A free leg that silently
degrades — 200 responses from a downgraded model, or a soft quota that answers slowly rather
than 429 — never rolls, because litellm sees success. This is not a regression (the pre-fix
random shuffle was strictly worse) but it means the honest description is "the declared chain is
now binding", not "cheapest usage-capable first". Live re-ranking needs a Router rebuild cadence
or a `set_model_list` refresh; neither exists in this diff.

**T1-CONTEXT (blast radius: currently zero).** `grep` for `make_router` / `litellm_plane` across
`src/` outside the package itself returns **nothing** — the litellm plane has no caller in the
live gateway path (consistent with `064d197 stop(GW-CUTOVER-LIVE-WIRE)`). Nothing here can spend
money today; it is correctness-of-the-future-cutover.

### T1 verdict: LAND-WITH-NITS
The two claims that matter are true and I re-proved both by execution, including the failover
claim the diff asserts but does not test. Fix the fail-loud overstatement in the `make_router`
docstring, and ideally land the failover test (a 3-leg 500-then-roll case) so the ordered-failover
claim is covered by something a runner executes.

---

## TARGET 2 — rig broker (`4f33f87`, landed in PR #264 / `128605a`)

### What I proved by execution

1. **[EXEC] The rig test suite really runs and is green.**
   `bash fleet/tests/spill-up.test.sh` → **55 passed, 0 failed, exit 0**, including the detention
   carve-out cases (n1-n4). So although `fleet/gate.sh` never gated the merge, the change's own
   suite does execute and does pass post-land.

2. **[EXEC] The claimed defect is genuinely fixed, on the real HTTP path.** Matrix run of
   `fleet/capability/availability.py filter-capped`:

   | case | input | stdout | rc | loud? |
   |---|---|---|---|---|
   | C | unreadable snapshot file | *(empty)* | **8** | yes, stderr |
   | D | **live gateway, all token envs cleared** | *(empty)* | **8** | yes, stderr |
   | B | real snapshot, `eco1` capped | `eco2` | 0 | note on stderr |
   | A | **valid but empty snapshot `{}`** | `eco1`,`eco2` | **0** | note only |

   Case D is the live 4-LOM gateway unauthenticated — it now returns rc 8 and refuses to report
   models as un-capped. The specific "302 + 0-byte body read as nothing-capped" defect is
   **dead**. Error-vs-empty is genuinely disambiguated for *transport/parse* failure.

3. **[EXEC/READ] Cost cap cannot be bypassed by config.** `spill_ceiling_tier`
   (`fleet/fleet-droid.sh:196-202`) awk-extracts `SPILL_UP_COST_CEILING` from the SSOT, echoes
   **empty** on missing/blank/malformed/off-axis, and the caller (`:305-311`) maps empty to
   `ceiling := start band` — i.e. **zero** escalation, plus a `cost-cap-config-invalid` ledger
   row. There is deliberately no in-code default. The cap value can only come from a file; the
   only env seam (`CHARON_TIER_CANON`) is a **path**, never a number. Confirmed: unset/empty/
   malformed config = no spill-up, not unlimited spend.

4. **[READ] Detain does release, and does not leak.** `fleet-droid.sh:597-604`: when
   `resolve_runnable_chain` returns non-zero the dispatcher prints SKIP, calls
   `fleet/release.sh "$id"` (ticket back on the board, still claimable) and records one
   `loop-guard.sh` attempt, so a persistent outage quarantines rather than spins. Not a leak in
   the normal path.

### Findings

**T2-F1 (HIGH — the most dangerous thing I found; the fixed defect survives through a second
door). A well-formed but EMPTY/shape-degraded snapshot is still a silent keep-all at rc 0.**
`fleet/capability/availability.py:227-239` + `:245-259`. `_load()` sets `_error` only on a
transport/JSON exception. A `200 {}` body — or any future payload where the `pools` key is
renamed, empty, or not yet populated — parses fine, so `error()` is `None`, `_pools` is empty,
and `status()` hits `if not chain: return "unknown"  # fail open` for **every** model. Proven in
case A above: `filter-capped eco1 eco2` returned **both models, rc 0**. `capped_filter_chain`
reads rc 0 as "filtered against a snapshot we actually READ" and hands the full chain to the
work client. The only trace is an advisory `0 pooled model(s)` note on stderr that nothing
asserts on. **Failure scenario:** gateway restarts and answers `/charon/status` before its pool
config loads (or a status-shape change lands) → capped-exclusion no-ops → the fleet spends
against parked/drained/cooled providers, at rc 0, with no ledger row and no
`CAPPED-FILTER-UNAVAILABLE:` line. This is the *exact* class the commit message says it ended
("a zero-item result caused by an error can never read as a filtered chain") — it ended it for
"could not ask", not for "asked, and the answer was empty". Same lens as the 302/0-byte bug.

**T2-F2 (MEDIUM — per-model error-vs-empty conflation).** Same code path, per model:
`availability.py:250-252`, a model id that is not a key in the gateway's `pools` map returns
`"unknown"` → kept, with **no** diagnostic at all. Proven in case B: `eco2` was not in the
snapshot's pools and was silently kept. **Failure scenario:** naming drift between
`fleet/tier-models.tsv` ids and the gateway's pool keys makes the capped filter a per-model
no-op that is invisible from the outside — indistinguishable from "that model is fine".
Suggested follow-up: count unknown-to-pool models and either warn loudly per model or treat
"none of the candidates are known to the gateway" as UNAVAILABLE (rc 8) rather than rc 0.

**T2-F3 (MEDIUM — a real, sanctioned overspend path worth an explicit budget).** The detention
carve-out at `fleet-droid.sh:361-365` spills **above** the configured cost ceiling whenever a
band is wholly HARD-detained, and re-evaluates per hop, so a chain of detained bands can walk to
the frontier band. It is loud and ledgered (`cost-cap-bypass-detention`, tested by n1-n4), so it
is not silent — but it is the one path where the cap does not bind, and it has no per-hop or
per-ticket spend budget. Deliberate per the header comment; flagging so it is a decision, not a
surprise.

**T2-F4 (LOW — a fail-OPEN hole around the whole broker).** `fleet-droid.sh:605-607`: a ticket
with **no** `work_class:` field skips `resolve_runnable_chain` entirely — no detention filter, no
capped exclusion, no cost cap — and runs `RUN_MODELS=("${MODELS[@]}")`, the FULL unfiltered
chain, behind a `WARNING:` that cannot go RED. Mitigated: `fleet/validate_board.sh:160-176`
makes `work_class` a required, validated field (`work-class-missing` is a board RED), so a
compliant board cannot reach it. Still the single remaining bypass of every guard this PR
hardened; a hand-written ticket file or a schema change re-opens it. Suggested: make the
no-work_class branch SKIP + loop-guard rather than run unfiltered.

**T2-F5 (LOW — mis-attribution, fails closed so harmless).** `availability.py:283-284` returns
rc 0 with empty stdout when the candidate list is empty; `capped_filter_chain`
(`fleet-droid.sh:250`) treats rc-0-with-no-models as a contract violation → rc 8 → the operator
is told "gateway capped state unreadable / commonly a 401" when the actual cause is an empty
input chain. Wrong diagnosis, right (closed) decision.

**T2-F6 (LOW — the audit trail is best-effort).** `exhaust_led` (`fleet-droid.sh:211-215`) ends
every write in `|| true`; likewise `release.sh` at `:601` is `>/dev/null 2>&1 || true`. If the
ledger path is unwritable the "loud + ledgered" evidence for a cost-cap detain degrades to
stderr only; if `release.sh` fails the ticket stays claimed by a dead droid despite the message
promising it "is released and stays claimable". Low probability, silent when it happens.

### T2 verdict: SAFE — NEEDS-FOLLOWUP
No revert warranted. The change is a real, execution-verified improvement: it cannot overspend
on an unreadable snapshot, it cannot detain forever (release + loop-guard quarantine), the cost
cap cannot be bypassed by unset/empty/malformed config, and its 55-check suite genuinely runs
green. **But it can still silently no-op** — T2-F1 (empty/shape-degraded payload) and T2-F2
(model unknown to the pool map) are the same defect class one layer in, and neither is covered
by the new tests. Follow-up ticket recommended for F1+F2 together; F4 is a cheap one-line
hardening worth folding in.

---

## Lens sweep

| Lens | Result |
|---|---|
| Gates that cannot go RED | **HIT** — T2-F4 no-`work_class` WARNING runs the full unfiltered chain (board-validator mitigated) |
| Fail-OPEN paths | **HIT** — T2-F1/F2 (empty snapshot, unknown model); T1-N1 (token-counter error); T1-N4 (litellm target_order miss) |
| Vacuous passes (0 items = green) | **CLEAR for T1** — red-proof: 6/6 new tests fail when reverted. **PARTIAL for T2** — 55 checks pass, but zero cover the empty-snapshot case |
| Red-proofs no runner executes | **CLEAR** — I executed both suites and the revert proof myself |
| Budget/timeout silently disabling a check | **HIT (low)** — T1-N2 tiktoken on hot path; T2-F6 best-effort ledger/release writes |
| Error-vs-empty conflation | **FIXED for transport (proven live, rc 8), STILL OPEN for payload** — T2-F1 |
| Missing client reported as exhaustion | **CLEAR** — rc 8 (unavailable) is now distinct from rc 7 (all-capped), proven by the f2 case and my matrix |

## Execution ledger
- `pytest tests/test_litellm_router_e2e.py` (worktree) → 10 passed
- same suite with feature reverted via injected plugin → 6 failed / 4 passed (red-proof)
- custom 3-leg failover probe, 2 variants, real loopback HTTP 500s → strict ascending roll
- `fleet/tests/spill-up.test.sh` → 55 passed, exit 0
- `availability.py filter-capped` 4-case matrix incl. the **live** unauthenticated gateway → rc 8
- Read-only: no repo modified; scratch artifacts under the session scratchpad only.
