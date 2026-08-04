# LANE C — THREE-AXIS TOOL RE-EVALUATION (2026-08-04)

Commissioned under **D-009** after **D-001** ("the factory is the product, not the gateway") inverted
the thesis every prior verdict was scored against. All figures measured on this box.
Read with `DECISIONS.md` (authoritative) and `EVAL-REGISTRY.md` (the 76 rows being re-scored).

> ## THE HEADLINE FINDING
> ### "The dominant failure is not a wrong verdict — it is a right verdict never executed."
> **10 of ~34 re-scored rows are VOID-AS-DELIVERED.** Only **ONE** row in the entire registry
> (PyYAML) has a verified **negative** delta on our own line count. Every other "adoption" added code.

---

## AXIS 1 — RE-SCORE (does the verdict survive the corrected lenses?)

| tool / scope | old verdict | now | what killed it |
|---|---|---|---|
| LiteLLM — full gateway core | REJECTED–KEEP-CUSTOM *(conditional)* | **VOID** | L5: condition never held. `tiers.json` = 0 hits; `litellm_plane` (1,063 LOC) has **zero importers** |
| LiteLLM Router — "deletes 650–750 LOC" | ADOPT (ADR-0017 "PROVEN") | **VOID AS DELIVERED** | L2: nothing deleted, **+1,063 LOC**. Only wiring is a lazy import at `litellm_router.py:358` inside a plane nobody imports |
| LiteLLM — SLOP orchestration harness | REJECT "supply-chain" | **VOID** | registry already flags it unsubstantiated; D-001 makes orchestration substrate *the product* |
| LiteLLM — tool-call translation | mixed | **RE-TEST** | rests on "200MB in the privileged core"; under D-001 the gateway is not a privileged differentiator |
| semgrep · gitleaks · bandit | ADOPT ×3 | **VOID AS DELIVERED** | L4: run ONLY on the free-plan private rig repo, which returns **403** for branch protection. **371–384 green runs that block nothing** |
| bandit — Python SAST | ADOPT | **VOID** | L2: `ruff --select S --preview` reproduces 100% of its findings; second tool, zero deletion |
| pylint W0613 | ADOPT | **VOID** | L6: `ruff --select ARG` finds 50 vs pylint's 46 — incumbent was under-configured |
| pyscn | ADOPT | **VOID AS DELIVERED** | not installed; 0 refs in either `.github/` |
| GitHub Projects v2 | ADOPT ("recommended #1") | **VOID AS DELIVERED** | bridge never built |
| Linear · Plane | REJECT / WATCH | **RE-TEST** | rejected on *feature parity*; the thing being defended is 166 `.md` files + a 636-line validator, for an operator who does not read code |
| task-orchestrator | WATCH | **RE-OPEN** | L2: it is literally D-003's mechanism (phase-gated transitions, typed deps, schema-enforced gates) |
| Temporal · Prefect · Dagster · Kestra · Airflow · Windmill | "not a work manager" | **NEVER SCORED FOR THE REAL ROLE** | swept only as a PM layer. The measured failure is orphans/no-retry/lost work — the **durable-queue** role |
| Forgetful | rejected "avoids a new dependency" | **VOID** | L2 — scored **B +2**, the highest of any memory target |
| Mem0 · LangMem · Graphiti · Lucid · Evermind · Hypabase · Letta · mnemostroma | REJECT | **SURVIVES** | executed trials; every one needs an explicit write call |
| opencode HTTP control plane | ADOPT, "**retire** session-bridge" | **PARTIAL / L2 FAIL** | 506 LOC added; session-bridge **not retired**, still referenced in 4 files and still the only live MCP server |
| Zed ACP | ranked #2 | **RE-TEST** | D-001 demands agent-agnostic; the 5-verb adapter was never built (both launchers are opencode-specific) |
| OpenTelemetry | REJECT — "product ships `observability.py`" | **VOID** | that basis is **false**: the module was retired as inert by `54e0dc8` |
| Hypothesis | ADOPT-NARROW | **VOID AS DELIVERED** | installed; 0 refs in `pyproject.toml` or workflows |
| Featherless | conditional on RFL-5 | **RE-TEST** | L5: `context_shaper.py` now exists (315 LOC) but has **zero importers** — condition unmet for a new reason |
| Claude Code hooks | ADOPT "with CI backstop" | **RE-TEST** | the named backstop cannot exist on a free private repo |
| OPA/Rego | DEFER — "a hook will call it" | **RE-TEST** | that caller does not exist |
| vulture (replace-scope) | REJECT–KEEP-HANDROLL | **RE-TEST** (narrow core survives) | dependency veto; the reachability-vs-refcount finding is real |
| deadcode · vulture · shellcheck-SETE · pytest-bdd · behave · Cucumber · PyYAML · egress rejects | various | **SURVIVES** | executed, incumbent enumerated at full strength (textbook L6) |
| qodo-merge · aider · CodeRabbit | **UNEVALUATED** | **STILL OPEN** | `review-pool.sh` = 399 LOC hand-rolled; ticket minted, never claimed |
| **merge queue (native GitHub)** | **not in the registry at all** | **VOID AS DELIVERED** | `docs/review-log/MERGE-QUEUE-EVAL.md:3` = "ADOPT … configuration-only". `allow_auto_merge` **already true**; no `merge_group` in any workflow; deliverable stranded off master |

## AXIS 2 — RE-OPEN: categories the tainted filter never shortlisted
**Zero registry rows mention any of these.** All UNVERIFIED — each needs an executed trial.

| # | never-considered | why the old filter excluded it |
|---|---|---|
| 1 | **Durable execution**: Restate, DBOS, Hatchet, River, Inngest, Trigger.dev, procrastinate, Celery/RQ | "duplicative of our runner"; the queue was rig, and rig was "ours" |
| 2 | **Agent sandboxing**: Dagger container-use, devcontainers, microsandbox, E2B, Firecracker/gVisor, nsjail | isolation assumed solved by `git worktree`; containers read as "heavy dependency". **189 live worktrees, zero process/FS isolation** |
| 3 | **Merge/PR automation**: native merge queue, Mergify, Kodiak, Graphite/Aviator, Renovate | landing was "ours" (`land.sh`) |
| 4 | **Git-native work ledgers**: beads, Backlog.md, git-bug, Issues+blocked-by | the `.md` board was declared SSOT before any tool question was asked |
| 5 | **Out-of-band alerting**: ntfy, Gotify, Pushover, Healthchecks.io, Uptime Kuma | D-003 *requires* it; nothing was ever shortlisted |
| 6 | **Observability/dashboard**: Grafana+Loki, Prometheus, Sentry, Netdata, Streamlit, Backstage | "the gateway ships its own observability" — that module was retired as inert |
| 7 | **LLM cost/telemetry**: Helicone, Langfuse, OpenMeter, OpenLLMetry, tokencost | the cost meter was "the differentiator"; it is inert |
| 8 | **Coding-agent runners**: OpenHands, SWE-agent, Sculptor, Conductor, Crystal, Agent SDK | "launching is ours" — `fleet-droid.sh` grew to 1,540 LOC unchallenged |
| 9 | **Mutation/contract/spec testing**: Stryker, cosmic-ray, Schemathesis, CrossHair, Codecov | `mutmut`/`diff-cover` installed and unused, so no comparison ever ran |
| 10 | **Factory secrets**: SOPS/age, git-crypt, direnv, 1Password/Bitwarden CLI | secrets were scored only as gateway key custody; the rig's own tokens were never in scope |
| 11 | **Deploy**: Kamal, Dokku, Ansible, Watchtower, systemd | `deploy.sh` (387) predates adopt-first |
| 12 | **Decision/ADR durability**: log4brains, adr-tools, OPA-as-merge-gate | D-003 concluded "build instead" before any tool was named |

## AXIS 3 — GAP AUDIT (the operator's addition; the highest-value axis)

| capability | today | our LOC | tool exists? | what adopting DELETES |
|---|---|---|---|---|
| **durable work queue** | **hand-rolled; substrate ABSENT** — `faktory` not installed, nothing on :7419, `claim.sh` references the "ONLY sanctioned path that starts work" **zero times** | 🔴 **~6,000** (3,167 rig + 2,831 product) | **YES — never scored** | **the single largest deletion in the estate** |
| land automatically when green | hand-rolled | 1,431 (`land.sh`+`land-push.sh`+`pr-queue.sh`) | **YES — ADOPT verdict exists, config-only, still OFF** | staleness/rebase/landing logic; kills the draft-PR class |
| execute agents | hand-rolled `fleet-droid.sh` 1,540 + 5 launchers | ~2,700 | opencode HTTP (half-adopted), Agent SDK, OpenHands | most of the supervision/retry loop |
| prove quality w/o reading code | hand-rolled gates | `fleet/checks` 10,012 + `fleet/tests` 33,177 + `preflight` 1,209 | **already owned, 0% on**: mutmut, diff-cover, playwright, hypothesis | `gate-integrity.sh`'s hand-written assertions |
| route to cheap models | hand-rolled + 1,063 LOC inert adopter | ~4,254 | LiteLLM Router (verdict exists, unexecuted) | ~1,015 LOC of proxy/router/policy_router/failover |
| single work ledger | 166 `.md` + validator | ~1,450 | beads/Backlog.md/Issues; Projects v2 ADOPT-on-paper | board parsing + validation + lock layer |
| cost accounting | hand-rolled + inert meter | 1,607 | Helicone/Langfuse/OpenMeter | most of it |
| deploy | hand-rolled | 582 | Kamal/Dokku/Watchtower — never asked | most of it |
| decompose into non-colliding slices | hand-rolled ×2 | 3,838 | partial only | little — **correctly novel per D-001; KEEP** |
| isolate agents | **adopted** `git worktree` + glue | 163 | containers never considered | nothing — the one clean adoption |
| decision durability | hand-rolled, 1 day old | `DECISIONS.md` | log4brains/adr-tools; OPA merge-gate | n/a — legitimate build, but **the blocking edge has no mechanism yet** |
| secret handling | split, rig-only + non-blocking | 732 | factory-side secrets never scored | `leak-guard.sh` once gitleaks can block |
| **observability / alerting** | 🔴 **NOTHING** | **0** | ntfy = 1 container; Healthchecks = 1 curl | n/a — **this is what makes D-003's out-of-band notify unimplementable** |
| **lifecycle enforcement (blocks on unfinished work)** | 🔴 **NOTHING** | **0** | Temporal, task-orchestrator, Forgetful plans | n/a — **the top unmet need** |
| PR review automation | hand-rolled | 399+ | UNEVALUATED | diff fetch, prompt, verdict parse, comment post |
| scheduling / cadence | cron + `watchdog/` generating **monit config for a monit that is NOT INSTALLED** | 975 | systemd/Healthchecks/Windmill | the whole monit generator, which has no runtime |
| dependency upkeep | 🔴 **NOTHING** | 0 | Renovate/Dependabot (free) | n/a |

## TOP 5 MOVES (by lines deleted + work-spawned-avoided)
1. **Enable native merge queue + auto-merge on the product repo.** Config-only; ADOPT verdict already on master, never applied. Retires most of 1,431 LOC and delivers "the machine lands it". Add the missing registry row — there is none for "merge queue".
2. **Move semgrep/gitleaks/bandit to the repo that can enforce them.** Zero new tools, zero new LOC; converts three advisory gates into real ones. *(Authorised standing by D-013.)*
3. **Lane A config flags** — 176 + 196 real defects incl. 3 HIGH security for ~6 lines, and it removes the standing basis for both the bandit and pylint adoptions (deletes two dependencies rather than adding any).
4. **Score durable-execution engines for the queue role** — the one question never asked. Largest deletion target; D-008a explicitly blocks the Go supervisor until this is answered.
5. **Resolve `litellm_plane` in one direction** — 1,063 LOC, zero importers. Wire it and delete ~1,015 LOC of commodity money-path, or delete the plane. **Both outcomes are negative-LOC; the status quo is the only one that is not.**

**Runner-up, cheapest unmet need:** adopt **ntfy or Healthchecks.io** for out-of-band alerting.

## COULD NOT VERIFY (do not treat as settled)
`crontab -l` is denied to the manager, so the cron ADOPT is UNVERIFIED from the crontab itself
(confirmed instead from live logs + heartbeats) · Track A/C security adoptions on 4-LOM (no Docker
access from here) · every AXIS 2 candidate is named, **not executed** · `fleet/tests` LOC includes
some pytest-artifact noise under `fleet/state/tmpdir-*` that was not subtracted.
