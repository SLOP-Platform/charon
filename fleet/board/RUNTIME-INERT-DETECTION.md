repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 1
branch: eval/runtime-inert-detection
depends_on:
owns: fleet/state/RUNTIME-INERT-DETECTION.md
serial_justified: |
  ONE question — "what did the running system actually execute" — measured across one candidate
  family against one corpus. The candidates only rank against each other in a single comparison.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. EVAL lane: measure and report. Wire NOTHING here.
source: |
  Operator, 2026-08-01: "I would add Coverage.py (maybe as a middleware to run in the background),
  or a lightweight APM to find unwired FastAPI routes/endpoint? Opentelemetry.io to the evaluations"
note: |
  ## THE INSIGHT THIS TICKET EXISTS FOR (operator's, and it reframes the whole class)
  Every inert-detector we own is STATIC: `check_inert_code.py` (reachability-from-entrypoint),
  vulture (reference-counting), `gate-integrity.sh` (grep for callers). Static analysis answers
  **"COULD this be reached?"**. The question that actually matters for built-but-inert is
  **"WAS this ever reached?"** — and only the RUNNING SYSTEM can answer that.

  This is a different DETECTION AXIS, not another tool in the same family. It is complementary to
  DEADCODE-TOOL-REDERIVE (static axis), not a duplicate — read that ticket's matrix before starting
  and extend it with a runtime column rather than rebuilding it.

  ## WHY IT WOULD HAVE CAUGHT WHAT WE MISSED (measured 2026-07-31/08-01)
    - **Faktory**: server up 7 days on 4-LOM, `lease-enqueue.sh` self-describes as "the ONLY
      sanctioned path that starts work", ZERO workers, `claim.sh` never calls it. A runtime signal
      showing zero invocations would have flagged this on DAY ONE instead of day seven.
    - **REVIEWER-TAB-POOL B1**: a guard comparing disjoint namespaces. Static analysis sees a
      called function. Runtime would show the guard's REJECT branch had never once executed.
    - **F2 auto-done-on-merge** — believed working, never observed firing.
  Note the pattern: in every case the code EXISTS and is statically reachable. Static tooling is
  structurally incapable of catching them. That is the gap.

  ## CONFIRMED SURFACE (verified 2026-08-01, do not re-derive)
    - Product IS FastAPI: `src/charon/service/app.py`, `src/charon/service/__init__.py`,
      `src/charon/litellm_plane/litellm_router.py`.
    - **6 route decorators** (`@app|@router .get/.post/.put/.delete/.patch`) across the tree.
    - `pyproject.toml` contains **ZERO** references to coverage or opentelemetry. Nothing is
      instrumented today.

  ## CANDIDATES (hunt expansively; these are the floor, not the ceiling)
    1. **Coverage.py** — including the operator's suggestion of running it as MIDDLEWARE / in the
       background against a live or dogfood process, not only under pytest. Investigate
       `coverage run --parallel` on the gateway process, and whether the overhead is tolerable for
       a long-lived service. Test-coverage and PRODUCTION-coverage are different products of the
       same tool; the second is the interesting one here.
    2. **OpenTelemetry** (opentelemetry.io) — auto-instrumentation for FastAPI
       (`opentelemetry-instrumentation-fastapi`). Per-route spans mean a route with zero spans over
       a window is provably unwired. Also covers outbound calls (which providers are ACTUALLY hit).
       Check what backend is needed and whether a file/console exporter suffices — we do NOT want a
       Jaeger/Grafana stack for a solo rig unless it earns itself.
    3. **Lightweight APM alternatives** — evaluate at least a couple (e.g. Pyroscope/Phoenix/
       py-spy sampling, Sentry perf, Prometheus + FastAPI instrumentator) on the same axis.
    4. Consider the CHEAPEST possible thing honestly: a route-hit counter written by existing
       middleware may beat all of the above [[best-not-defensible]]. If so, SAY SO — the simplest
       thing that fully solves it wins, and "we already ship a middleware layer" is a real argument.

  ## THE DELIVERABLE
  Answer, with EXECUTED evidence, not docs:
    a. Which candidate can tell us **"this route / function / module has never executed in N days
       of real use"** — the exact question. Rank by how directly it answers it.
    b. Overhead measured on the real gateway, not quoted from a README.
    c. Ops cost: does it need a backend/daemon/storage? A solo rig should not inherit a
       Grafana stack to find dead routes. Weigh this as ops burden, NOT as "size" — size is not a
       rejection criterion.
    d. Does it work for the RIG's bash surface too, or is it Python-only? (Faktory's wiring gap is
       in BASH. If every candidate is Python-only, that is a valuable finding: state it plainly.)
    e. What it would have caught from the three real incidents above. A candidate that catches none
       of them is not a contender.
    f. RECOMMEND ONE, with the integration shape, or an honest "none earns its keep, here is why".

  ## HARD RULES
  - Verdicts land in `fleet/state/EVAL-REGISTRY.md`; long-form in the owned file. A verdict not in
    the registry gets paid for twice.
  - Size / dep-count are NOT rejection criteria. Ops burden and control direction ARE.
  - Wire NOTHING in this ticket. Recommend; a separate ticket wires.

D&S — Deps & Sequence:
  - Depends on: nothing. Pure measurement, collision-free (owns only its own state file).
  - Sibling: DEADCODE-TOOL-REDERIVE covers the STATIC axis. Read it; extend its matrix with a
    runtime column instead of starting a second one.
