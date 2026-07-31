# GATE-RED-BRANCHES — why two LiteLLM branches fail the pre-push gate

Investigated 2026-07-24. Product repo `/home/stack/code/charon`. READ-ONLY on both target worktrees.

## TL;DR

Both branches fail the **same single check — `public-clean`** — and in **both cases the cause is
the branch's own added file**, not a stale base and not a pre-existing red. Neither RED has
anything to do with LiteLLM code or with master having moved.

| Branch | Failing check | Cause | Salvage verdict |
|---|---|---|---|
| `feat/gateway-litellm-live-wire` @ `42a7440` | `public-clean` (only) — 64-hex token in a captured log line | **branch's own file** | **preserve-as-evidence** (1-line redaction makes it fully green) |
| `spike/litellm-router-adapter` @ `f2cee9d` | `public-clean` (first) — `/home/stack` home path | **branch's own file** | **obsolete — delete** |

---

## Branch 1 — `feat/gateway-litellm-live-wire` @ `42a7440`

Worktree `/home/stack/code/charon/.claude/worktrees/agent-a4896ad6d2bfe5d06`.
Base (parent) = `7e16e4a` "feat(gateway): adopt litellm.Router (library) — first slice", 2026-07-20.
Master is **15 commits** ahead of that base.

### 1. What exactly fails

`PYTHONPATH=<wt>/src python3 -m charon.cli gate` → **exit 1**, fail-fast at check 6 of 16:

```
[ruff] OK  [mypy] OK  [host-boundary] OK  [version] OK  [gate-registry] OK
[public-clean] PUBLIC-CLEAN VIOLATION — personal/internal info found:
DOGFOOD-litellm-live.txt:7: hex token shape (>=40 chars): ... register_model: model=4ed9c...
```

The offending content is a **64-char hex model-id inside a captured `litellm` WARNING line**
that the probe's own transcript recorded. It is a hashed model identifier emitted by
`litellm.utils.register_model`, **not a secret** — but `tools/check_public_clean.py:32`
(`re.compile(r'\b[0-9a-fA-F]{40,}\b')`, "hex token shape") cannot tell the difference.
The rule is a blunt shape-matcher and this is a **false positive in substance**, though a
true positive by the rule as written.

### 2. Cause attribution — **branch's own changes** (settled by test, not inference)

Three independent pieces of evidence:

- **Base gate is fully green.** Throwaway worktree at `7e16e4a`, same command:
  all 16 checks OK incl. `[public-clean] OK` and `[pytest] OK` → `CHARON-GATE: all checks passed`,
  **exit 0**. So the base is not red. Rules out (c) pre-existing.
- **The violating file is branch-only.** `DOGFOOD-litellm-live.txt` is added by `42a7440`;
  it does not exist at the base. A base cannot fail on a file it does not contain.
  Rules out (b) stale base.
- **The rule predates the base.** `tools/check_public_clean.py` line 32 is **byte-identical**
  between the branch worktree and today's master, and was last touched by `db62c61`
  (2026-07-20 18:50), i.e. *before* the base `7e16e4a` (2026-07-20 22:53). The gate ran the
  branch's own copy of the checker. No tightening happened after the branch point.

**Note — the commit message's "Full gate green (16/16)" claim is false as committed.** The rule
and the offending line both existed at commit time. The transcript was almost certainly captured
(or re-captured) after the gate run. Worth logging under the standing "document model
self-report lies" directive.

### 3. Is `public-clean` the *only* red?

Tested directly: throwaway worktree at `42a7440`, redacted the 40+ hex run with
`sed 's/[0-9a-f]\{40,\}/HEXREDACTED/g'`, re-ran the full gate →
**all 16 checks OK, `CHARON-GATE: all checks passed`, exit 0.**

So the entire blocker is **one redaction on one line of a text transcript.** Nothing in the
branch's code is red.

### 4. Salvage verdict — **PRESERVE AS EVIDENCE**

The branch adds **no `src/` change**; external contract byte-identical. It is
`tools/dogfood_litellm_live_probe.py` (+190) plus its captured output (+51). Its value is the
**stop-signal**, and that signal was correct and was acted upon (below). Cost to land: one
redaction. Recommend redact-and-keep so the runnable probe survives; it is the only executable
artifact that demonstrates the live Router serve path plus the controls firing.

---

## THE MONEY-PATH STOP-SIGNAL (primary deliverable)

Source: commit message of `42a7440` + `DOGFOOD-litellm-live.txt`.

### What it found

The branch was tasked with the **live wire-in** — replace `forwarder.forward_with_failover` /
the `proxy_server` request loop so `litellm.Router` serves live traffic, deleting ~650–750 LOC
(accept #4). **It refused, and did not modify the money path.**

It **PROVED SAFE + LIVE** (probes 1–3): a real request served through
`make_router → litellm.Router.completion → loopback stub`, with base-bound key (#181),
SG-never-Anthropic (Anthropic leg dropped from `model_list` entirely), egress allowlist and
SSRF/link-local refusal all firing *before* the Router is built, Router constructed ONCE.

It **BLOCKED** on two un-built bridges:

- **[4] SR-1/SR-2 silent-downgrade guard NOT re-hosted.** A genuine downgrade is *detectable*
  (`observer.classify(...).pseudo_success = True` when `requested='ma'` returns
  `response.model='CHEAPER-SUBSTITUTE'`) but `complete_via_router` **returns the body UN-GATED**:
  no `observer.record`, no `X-Charon-Downgrade` header, no `failover_on_downgrade`
  serve-vs-refetch decision.
- **[5] Cost metering / drain-then-park NOT re-hosted.** `complete_via_router` never invokes
  `observer.record` / `balance_tracker.record_spend` / `spend_limiter.record`. litellm computes
  its **own** cost via its callback, and that was not bridged to `BalanceTracker` — so
  drain-then-park spend would not advance on the Router path.
- Plus streaming SSE relay + the ADR-0016 exhaustion envelope.

**The warning:** landing the wholesale forwarder replacement without those bridges would
**reintroduce the 2026-07-03 silent double-bill** and break metering — a half-migrated money path.

### Does it still reproduce on master today? — **NO for the danger; the STOP still holds for the wire-in**

Verified against current master (`6782236`):

- **The money path was never half-migrated. The whole LiteLLM plane is INERT.**
  `grep -rn "litellm" src/charon/forwarder.py src/charon/gateway.py src/charon/proxy_server.py`
  → **zero hits**. `grep -rn "litellm_plane" src/ ` outside the package itself → **zero hits**.
  `forwarder.py` (51 KB) is still the live money path. **There is no double-bill exposure today,
  because nothing routes through the Router.** The stop-signal was heeded.
- **Bridge 1 (downgrade) has since landed as code:**
  `src/charon/litellm_plane/litellm_router.py:301 complete_via_router_guarded(...)`, with
  `:260` explicitly documenting that plain `complete_via_router` is "Downgrade-unaware".
  So probe finding [4] is *still literally true of `complete_via_router`* — but that is now by
  design, with a guarded sibling provided (GW-BRIDGE-1).
- **Bridge 2 (metering) was resolved by decision, not by re-hosting.**
  `src/charon/litellm_plane/metering.py:1-11` — **ADR-0020 ACCEPTED verify-only**: the litellm
  cost callback runs *alongside* Charon's accounting as a cross-check, **not** as the money
  source of record. Charon's own cost computation "REMAINS the source of record advancing
  BalanceTracker + drain-then-park"; the module "must NEVER override, correct, freeze, or
  reorder" it. So probe finding [5] was answered by inverting it — don't re-host metering into
  litellm, keep Charon authoritative. (`LITELLM-COST-FIELD-FIX` fixed the field this reads.)
- **Bridge 3 (streaming) landed:** `src/charon/litellm_plane/streaming.py:1` —
  "SSE streaming relay for the adopted `litellm.Router` path (GW-BRIDGE-3)".

**Net:** the probe identified a real defect class, and it did **not** become a live defect —
the product respected the STOP and built the three bridges as separate modules instead.
The remaining open item is the wire-in itself (accept #4, deleting ~650–750 LOC from
`forwarder.py`), which is still **not done** and still gated on the plane being non-inert.
The stop-signal remains valid *as guidance for that future ticket*.

---

## Branch 2 — `spike/litellm-router-adapter` @ `f2cee9d`

Worktree `/home/stack/code/charon-fleet-LITELLM-SPIKE`.
Base (parent) = `4028819`, 2026-07-19. Master is **22 commits** ahead.
Uncommitted item is `.litellm-venv/` (untracked 218 MB venv — junk, gitignored by design).

### 1. What exactly fails

Same command → **exit 1**, fail-fast at check 6 of 16:

```
[public-clean] PUBLIC-CLEAN VIOLATION — personal/internal info found:
spike_litellm/SPIKE-FINDINGS.md:4: home path "/home/stack": worktree `/home/stack/code/charon-fleet-LITELLM-SPIKE`.
```

This is a **genuine** violation, not a false positive — a dev-box absolute path in a file
destined for a public repo, exactly what the standing "public repos: no personal/internal info"
and "no hardcoded cross-boundary paths" directives forbid.

### 2. Cause attribution — **branch's own changes**

`spike_litellm/SPIKE-FINDINGS.md` is added by `f2cee9d` and exists only on this branch;
the base cannot fail on it. The `public-clean` gate long predates the base
(wired in `1c54ef4`, 2026-07-07). Not stale-base, not pre-existing.

### 3. Salvage verdict — **OBSOLETE — DELETE**

- **The author already marked it disposable.** `SPIKE-FINDINGS.md:118` "## Throwaway note —
  `spike_litellm/` is disposable… `run_spike.py` is a rough harness (bare asserts, no test
  framework)." The commit subject says "Throwaway feasibility spike (NOT adoption)."
- **Its question is settled and its output superseded.** The spike asked "can `litellm.Router`
  sit UNDER Charon's policy layer?" and answered PASS with a ~55-LOC adapter. Master has since
  landed the real thing: the whole `src/charon/litellm_plane/` package
  (`litellm_router.py`, `metering.py`, `park_cooldown.py`, `streaming.py`) with `make_router`,
  `complete_via_router`, `complete_via_router_guarded`, plus GW-BRIDGE-1/2/3, `LITELLM-CI-DEPS`
  and `LITELLM-COST-FIELD-FIX`. `spike_litellm/litellm_router_adapter.py` — the one file the
  spike said was "worth keeping as a reference" — is now strictly worse than the shipped
  `litellm_plane/litellm_router.py`.
- Its proposed follow-up ticket (`ADOPT-SUBSTRATE-01`, "land the adapter behind a
  `gateway.backend` flag") has effectively been executed by the `litellm_plane` package.

**Only durable content worth extracting before deletion** (findings, not code — a few lines
into a doc/ADR if not already captured):
- Measured dependency cost: **218 MB** installed (204 MB excl. pip), **1.6 s** cold
  `import litellm`, **17 packages with native compiled extensions** on the request hot path —
  the concrete refutation of the stdlib-only / zero-native-dep property of the privileged
  key-holding core (ADR-0005). This is the one *measurement* the spike produced that the
  landed code does not record.
- The deletable-LOC inventory (`forwarder.py:181-235`, `:563-651`, `:825-915`, `failover.py`
  141 LOC, `translate.py` 142 LOC, `response_adapters.py` 106 LOC ≈ 650–750 LOC) — this is the
  same accept-#4 target branch 1 refused to execute, and is the useful input to that future
  wire-in ticket.

Recommend: confirm those two items exist in `ADOPT-MAP.md` / ADR-0020, then delete the branch
and the `.litellm-venv/` directory.

---

## Method notes

- Gate command used verbatim per branch:
  `cd <worktree> && timeout 1800 env PYTHONPATH=<worktree>/src python3 -m charon.cli gate`
- Base comparison used detached throwaway worktrees `/home/stack/code/charon-tw-base1`
  (at `7e16e4a`) and `/home/stack/code/charon-tw-b1` (at `42a7440`, hex redacted);
  **both removed** after the run.
- Nothing was committed, pushed, amended, rebased or modified in either target worktree.
- No run hung; every gate terminated well inside its timeout. Base and scrubbed-branch full
  gates (incl. pytest) each completed in roughly 20–30 min; the two RED runs fail-fast in
  under a minute at check 6.
- `feat/diff-cover-mutmut-adopt` was not touched.
