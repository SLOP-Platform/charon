# MARKER PROOF BACKFILL — 2026-07-19

Resolves the unverifiable done-marker class. `fleet/state/` is GITIGNORED, so the marker
edits themselves do NOT commit — this note is the durable record of what was written and why.

## Correction to the 2026-07-18 audit

The audit reported **36** markers that were unverifiable because they had "no `merged:` proof
AND no board file at all". **The board-file half of that claim is false.** The true figures:

| set | count |
|---|---|
| markers in `fleet/state/done/` | 177 |
| markers with NO `merged:` proof line | **99** |
| of those, having a board file in `fleet/board/archive/` | **99 (all)** |

Every one carries a `branch:` field, which is what made archaeology possible. The 36 figure
was the subset that failed a batch `verify_merged` sweep, not a set lacking board files.

## Method

Match ranked by strength, then the candidate sha was required to be reachable from that repo's
`origin/master` before any proof was written:

1. `scope` — conventional-commit scope `feat(<ID>):` / `fix(<ID>):` (strongest)
2. `branch` — a merge commit naming the board file's exact `branch:` value
3. `idword` — bare word-boundary ID mention; **NOT trusted on its own**, each hand-reviewed

13 `idword`/MISS candidates were hand-reviewed; 5 were accepted (the ID is the commit-subject
prefix), the rest were rejected as mere board/handoff mentions and sent to behaviour testing.

## Results

**86 markers backfilled with a verified `merged:<full-sha>`. All 86 now return rc=0 from
`fleet/verify-merged.sh`.** Gate discrimination re-confirmed: `BOGUS-TICKET-XYZ` returns rc=1,
so the passes are real and not a no-op.

Three rig-repo tickets (ACTION-PIN-POLICY, PREFLIGHT, SR-4) initially failed verification even
with a correct rig sha, because their archive board files carry no `repo:` field and
`verify_merged` fails closed rather than defaulting to the product repo. Adding
`repo: charon-private` to those three files fixed it. Those board edits DO commit.

### Backfilled (86)

| ticket | repo | match | proof sha |
|---|---|---|---|
| ACTION-PIN-POLICY | rig | scope | `acce34880049` |
| ACTUALS-LEDGER | prod | subject-prefix | `6d7ec5f3dd5f` |
| ADR-0015 | prod | scope | `c9fedf5bb5e0` |
| BILLING-EST-COST-FIX | prod | idword | `3b434dc15960` |
| CI1 | prod | branch | `60a3a9c0e5e3` |
| CLIENT-CONNECT | prod | branch | `8cd03e763c16` |
| CLIENT-CONNECT-GUI | prod | scope | `c9fedf5bb5e0` |
| CONSOLE-PROVIDER-MGMT | prod | scope | `c9fedf5bb5e0` |
| DEP1 | prod | branch | `39051026fc52` |
| DOCKER-INSTALL | prod | branch | `c9402326f2a8` |
| DOCS-TWO-MODE | prod | branch | `7834fd9253cc` |
| DRAIN-ROUTING | prod | idword | `8d65af464b07` |
| DTC-1 | prod | scope | `c9fedf5bb5e0` |
| DTC-2 | prod | scope | `c9fedf5bb5e0` |
| DTC-3 | prod | scope | `c9fedf5bb5e0` |
| DTC-4 | prod | scope | `c9fedf5bb5e0` |
| DTC-5 | prod | scope | `c9fedf5bb5e0` |
| DTC-7 | prod | scope | `c9fedf5bb5e0` |
| E0 | prod | branch | `a8384f00708f` |
| E1 | prod | scope | `17fcb2a5c2af` |
| E10 | prod | scope | `3a844ad6cf94` |
| E2 | prod | scope | `663e89091bb0` |
| E3 | prod | branch | `738db7fa63ea` |
| E4 | prod | branch | `627163ed091f` |
| E6 | prod | branch | `c8bf64991f68` |
| E7 | prod | scope | `b66fc78ac369` |
| E8 | prod | branch | `dcc728ad8207` |
| E9 | prod | scope | `3f7305d550ba` |
| FALLBACK-PROVIDER | prod | branch | `b28526a2044f` |
| FB1 | prod | branch | `5a4f58e57c9c` |
| FB3 | prod | branch | `9651ac98ace9` |
| FB4 | prod | branch | `123add598851` |
| FB5 | prod | branch | `dd50f99bc8fc` |
| FB6 | prod | branch | `2041284098ca` |
| FN1-MEMORY-STORE-ADOPT | rig | branch | `01313ab8d9f5` |
| FN2-BITEMPORAL-DECAY | rig | branch | `73a010ab425e` |
| FN3-CURATION-PASS | rig | scope | `1cc7c3d935d5` |
| FR1 | prod | scope | `8d48b01da047` |
| HARD1 | prod | scope | `c66019eb1c46` |
| INTAKE1 | prod | scope | `e0872e97d6be` |
| MODEL-DISCOVERY | prod | scope | `aee120db0568` |
| N1 | prod | branch | `86c8c5e42762` |
| N2 | prod | branch | `f98a267f6bc0` |
| N4 | prod | branch | `62f250869c3f` |
| N5 | prod | branch | `64b507a7d6c5` |
| NORMALIZE-CASE-QUANT-FIX | prod | idword | `249b7272e645` |
| OBS-CAPTURE | prod | scope | `c9fedf5bb5e0` |
| OBS-UI | prod | scope | `c9fedf5bb5e0` |
| PREFLIGHT | rig | scope | `af23db0c333a` |
| PROD-INSTALL | prod | scope | `1e7b0036e84f` |
| PUBLIC-CLEAN-LINT | prod | scope | `b28526a2044f` |
| RELEASE-SMOKE-FIX | prod | branch | `e922f2f15a82` |
| RESPONSE-ADAPTER-UNIVERSAL | prod | idword | `6096fb3a7fb6` |
| RFL-1 | prod | scope | `bc296ebc3feb` |
| RULE-SYNC-AUDIT | rig | branch | `95f645d8557f` |
| S1 | prod | branch | `952d65aaa3c3` |
| SECRET-SCAN-ENVVAR-FP | prod | branch | `778bc0d552cc` |
| SETUP-KEY-UX | prod | scope | `1ad15efff3e7` |
| SETUP-UX-A | prod | branch | `d85ed3968853` |
| SR-1 | prod | scope | `986293f04738` |
| SR-2 | prod | scope | `47f1c99a7afd` |
| SR-4 | rig | scope | `50af47ca96fc` |
| SR-5 | prod | scope | `e3e8c5bc2178` |
| SR-5b | prod | scope | `ef0eb7da493f` |
| SR-7 | prod | scope | `b45705ff8cc3` |
| T7 | prod | branch | `5d554e63a7c9` |
| T8 | prod | scope | `dee648548782` |
| TEST-HARDEN-CONTRACT | prod | idword | `3c82ab389ee3` |
| TEST-PORT-FLAKE | prod | branch | `6888c53a618d` |
| TIER-1 | prod | scope | `feff53f1a35d` |
| TIER-2 | prod | branch | `01b318ce2cfc` |
| TIER-3 | prod | scope | `0b584e1d5af8` |
| TIER-4 | prod | branch | `e4909d945b3e` |
| TIER-5 | prod | scope | `0b584e1d5af8` |
| TIER-6 | prod | scope | `0b584e1d5af8` |
| TIER-7 | prod | branch | `47b455222aba` |
| TIER7B | prod | branch | `1b1653ec675e` |
| TIER7B-FOLLOWUP | prod | scope | `2c16d93dc020` |
| WCI-FOLLOWON | prod | scope | `87e997d372e6` |
| WORK-AGENT-BEARINGS | prod | branch | `811a5c770c6a` |
| WORK-BEARINGS-WORKPATH | prod | branch | `5859d0bbe995` |
| WORK-CONVERGE-REVIEW | prod | branch | `3accc41472ee` |
| WORK-GATEWAY-WIRE | prod | branch | `ee0e3eb22941` |
| WORK-LAND-PR | prod | scope | `c5a413086fa0` |
| WORK-OBSERVABILITY | prod | scope | `dfc83c8f354c` |
| WORKTREE-ADD-FORCE | prod | branch | `bc7abfd0a4cc` |

## Behaviour-tested residue (13)

No receipt was written for these — nothing in either repo's history positively identifies a
landing commit. Classified by whether the feature is observably present on master. Exercised
with a targeted suite (`test_failover`, `test_gateway_failover`, `test_request_normalizer`,
`test_reconcile`, `test_agent_launch_routing`, `test_check_workflows`,
`test_check_test_patterns`): **113 passed**.

| ticket | class | observable |
|---|---|---|
| PROXY-FAILOVER-FIX | PRESENT | `forward_with_failover` invoked at `src/charon/proxy_server.py:451`; `proxy.py:110` `failover()`; failover suites green |
| INC-401-FAILOVER | PRESENT | `_UNSUPPORTED_STATUSES = {400, 401, 422}` `src/charon/proxy.py:84`; `_is_auth_error` `:238` called `:400`, branched `:439`; billing-401 handled `:220` |
| REQUEST-NORMALIZER | PRESENT | `tests/test_request_normalizer.py` green |
| WCI | PRESENT | `src/charon/engine/reconcile.py` + `tests/test_reconcile.py` green |
| CWD-CONFIG | PRESENT | `src/charon/ports/agent_launch.py`; `tests/test_agent_launch_routing.py` green |
| ORCH-ROUTE | PRESENT | same suite green; `docs/review-log/ORCH-ROUTE-STEP-0.md` on product master |
| CI-WORKFLOW-POLICY-GATE | PRESENT | `tools/check_workflows.py` + test green |
| DTC-8-TEST-PATTERNS | PRESENT | `tools/check_test_patterns.py` + test green |
| DIFFICULTY-SCHEMA | PRESENT | `fleet/validate_board.sh:209-218` hard-fails on a missing `difficulty:` |
| HANDOFF-PIPEFAIL | PRESENT | `fleet/handoff.sh:23` `set -euo pipefail`; mask documented `:287` |
| **SR-8** | **ABSENT** | see below |
| BRIDGE-HARDEN | UNKNOWN | primary `owns:` is `~/.config/opencode/session-bridge/server.py`, outside both repos and unversioned. Only `fleet/archive/BRIDGE-IMPROVEMENT-PLAN.md` landed. Would need a bridge behaviour probe to settle. |
| DS-PLAN-REVIEW | UNKNOWN | `owns:` is empty and the deliverable is a review, not an artifact. No `ds:` hard-fail exists in `fleet/validate_board.sh`. Nothing cheap to check. |

## SR-8 — ABSENT. Must return to the board.

This is a second REPO-DECL-CENTRAL: marked done, never built.

SR-8's board scope is explicit and operator-approved (2026-07-04): **"WIRE all 6 modules per
SR-8-RECS.md"** — Observability, RequestInspector, SessionAffinity, VirtualKeyManager,
SpeculativeExecutor, ConsensusRouter, each "WIRE always-on".

On product `origin/master` all six are imported, accepted as constructor kwargs
(`src/charon/proxy_server.py:498-500`) and stored (`:579-581`) — and then **never invoked**.
A grep for any call on `self.speculative_executor`, `self.consensus_router`,
`self.virtual_key_manager`, `request_inspector`, `session_affinity` or `observability`
across all of `src/charon/` returns **zero** call sites. Each module has exactly 2 references:
the import and the assignment.

Corroborating: rig commit `50af47c` (`docs(SR-4)`) cross-references SR-8 as the still-open
"wire-or-remove decision" follow-up. No commit in either repo carries an SR-8 scope, and SR-8
appears nowhere in product `docs/`, `src/` or `tests/`.

This is exactly the construct-but-never-invoke blind spot the audit flagged at §1.5 — and it
is why INERT-INSTANCE-DETECT remains a valid ticket. `check_inert_code` is green here.

## ACTUALS-LEDGER — PRESENT, but its owned files are gone (deliberately)

Worth recording because it looks like a phantom and is not. Landed at `6d7ec5f`
(`ACTUALS-LEDGER-WAVE1`, +629 lines incl. `src/charon/capability/actuals.py` and
`tests/test_actuals_ledger.py`), hardened by `aac85ac`, merged via `a541400`. Both files are
absent from master **today** because `317e589` (`fix(dedup-actuals-delete)`, #160)
intentionally removed them as a dedup. `src/charon/capability/scorecard.py` survives.
The ticket is genuinely done; owns-path presence would have wrongly called it a phantom.

## Money/trust path — verdict

| ticket | verdict |
|---|---|
| ACTUALS-LEDGER | BACKFILLED `6d7ec5f` — done, files later deduped away |
| DRAIN-ROUTING | BACKFILLED `8d65af4` (`feat: DRAIN-AND-PARK`) |
| SR-1 | BACKFILLED `986293f` `fix(SR-1)` silent-downgrade double-bill |
| SR-2 | BACKFILLED `47f1c99` `feat(SR-2)` |
| SR-4 | BACKFILLED `50af47c` `docs(SR-4)` (rig; needed `repo:` fix) |
| SR-5 | BACKFILLED `e3e8c5b` `feat(SR-5)` pricing capture |
| SR-5b | BACKFILLED `ef0eb7d` `feat(SR-5b)` cost_usd wiring |
| SR-7 | BACKFILLED `b45705f` `feat(SR-7)` spend-cap hardening |
| SETUP-KEY-UX | BACKFILLED `1ad15ef` |
| PROXY-FAILOVER-FIX | PRESENT by behaviour, no receipt |
| INC-401-FAILOVER | PRESENT by behaviour, no receipt |
| **SR-8** | **ABSENT — back on the board** |

The billing chain SR-1 -> SR-5 -> SR-5b -> SR-7 is fully receipted; failover is behaviourally
sound. The single money/trust hole is SR-8's six unwired modules.

## Nothing destructive was done

No marker deleted, no ticket retired, `retire-done.sh` and `done.sh` were never invoked.
