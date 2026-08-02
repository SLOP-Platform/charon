repo: charon
tier: strong
priority: 0
difficulty: 3
work_class: money-path
branch: fix/spend-metric-trustworthy
depends_on:
owns: src/charon/spend_limits.py, tests/test_spend_metric.py
serial_justified: |
  One number and its trustworthiness. Splitting the accrual fix from the cap-reload fix ships
  either a trustworthy number nothing enforces, or a cap enforcing a fictional number.
source: |
  Operator challenge 2026-08-01: "how is it spending that much and where? I don't have that much
  in any provider." They were right — the number is inflated and the manager had escalated on it.
note: |
  ## THE DEFECT — `spent_usd` IS NOT REAL BILLED SPEND
  `/data/spend.json` reported **$75.68** for 2026-08 while the operator had added $20 to
  OpenRouter and its console showed **$2.78** consumed. The counter is inflated; the account is not.

  `forwarder.py:_spend_to_record` documents the history in its own docstring:
  > "Billing the pre-flight `est_cost` floor on those $0 responses is the phantom-spend bug that
  >  inflated `spend.json` to the **fictional ~$223**: the old `cost if cost > 0 else est_cost`
  >  substituted the fabricated floor (`request_bytes/4 · $1.5e-6`) on EVERY free/flat completion."

  That bug was PARTIALLY fixed — a real `$0` from a free/flat route now records `0.0`. **The
  fabricated floor still applies to the `unpriced` case**, and we measured 2026-08-01 that the
  catalog carries NO price fields at all (only `cost_rank` on 212 of 859 entries). So a large
  share of completions land in `unpriced` and are billed at an invented number.

  ## WHY THIS IS WORSE THAN A LEAK
  We have **no trustworthy spend signal**. A real runaway and ordinary traffic look identical, so:
  - the operator cannot tell whether a burn is real (this ticket exists because they had to);
  - the manager escalated a non-emergency as urgent, on this number;
  - **every "cheapest-first" routing decision that keys on metered spend is keying on fiction** —
    see FORWARDER-COST-ORDER-FALLBACK, where the per-request reorder consumes metered spend.
  A wrong number that looks authoritative is more dangerous than a missing one.

  ## SECOND DEFECT — THE CAP CANNOT BE SET WITHOUT A RESTART
  `spend_limits.py:17` holds `self._limit_usd` from construction and **rewrites it into
  spend.json on every persist**. Editing the file on a running gateway is silently clobbered:
  a `monthly_limit_usd` of 50.0 was reverted to 0.0 by the running process. So the only ceiling
  the system has cannot be changed while it is running — and `0.0` currently means NO CAP.

  ## SCOPE
  1. **Never bill a fabricated floor.** An `unpriced` completion must be recorded as UNKNOWN and
     counted separately — never folded into a dollar total that reads as authoritative. Surface
     "N requests unpriced" beside the number.
  2. **Make the cap settable at runtime** (re-read on change, or an admin endpoint), so a ceiling
     can be imposed without a restart. Today the only way to cap a runaway is to restart it.
  3. **Reconcile against reality**: where a provider reports real cost, prefer it; expose a
     comparison so drift between our number and provider consoles is visible rather than assumed.
  4. Do NOT paper over it by hiding the number. The requirement is a number that is TRUE or
     explicitly marked unknown.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, offline, stubbed upstream:
    a. an `unpriced` completion does NOT increase `spent_usd`; it increments an explicit
       unknown-count. Revert -> RED. **This is the inflation bug.**
    b. a real `$0` free/flat completion records 0.0 (guards the earlier partial fix from regressing).
    c. a completion with a real provider cost records it verbatim.
    d. `monthly_limit_usd` changed on disk is picked up by a RUNNING limiter without restart,
       and is NOT clobbered back on persist. Revert -> RED. **This is why the cap could not be set.**
    e. ANTI-OVER-BLOCK: with a real cap set and real spend below it, requests still flow.
  Then dogfood: report `spent_usd`, the unpriced count, and the delta versus the OpenRouter console.

  ## ADVERSARIAL REVIEW REQUIRED (money-path)
  Reviewer != builder. The reviewer must confirm the new number cannot silently UNDER-report
  either — an under-reporting cap is a runaway with extra steps.

## Dependencies & Sequence
  - Related to FORWARDER-COST-ORDER-FALLBACK (in flight): that ticket falls back to `cost_rank`
    when the meter is empty. This ticket makes the meter itself honest. Independent, but note the
    ordering path consumes this number — coordinate if both touch the same call site.

## RE-SCOPE 2026-08-02 (operator-directed): DERIVE COST FROM THE PROVIDER, NOT FROM A TABLE

Operator: "why are costs not being derived directly from the providers?" Correct — they are
COMPUTED, not OBSERVED, and that is the root of the fiction.

MEASURED TODAY on the live gateway (/data/spend.json):
    spent_usd 1185.4428735774175 | month_start "2026-08" | monthly_limit_usd 0.0
$1,185 for TWO DAYS of August, with NO per-provider breakdown — the file has exactly three
fields. Prior measurements of the same meter: reported $0.000226 when real spend was $1.3372
across 50 sessions, and separately inflated to a fictional ~$223 via a fabricated est_cost floor.
The meter is wrong in BOTH directions, and no number it emits may drive a routing or capping
decision.

WHY: cost = tokens x a STATIC price table in the catalog. Only 10 of 861 models are priced, and
an unpriced model falls back to a FABRICATED FLOOR. A fabricated floor is worse than a null —
it converts "we do not know" into a confident wrong number that then steers routing.

REQUIRED SHAPE — a per-provider cost adapter, in this precedence:
 1. PROVIDER-REPORTED cost where the provider gives it (OpenRouter exposes actual cost per
    request at /api/v1/generation; most OpenAI-compatible providers return real `usage` in the
    response body). This is authoritative and has no table to rot.
 2. tokens x a LIVE-FETCHED price (PRICE-REFRESHER's feed) only as FALLBACK.
 3. UNKNOWN otherwise — emit null and mark the record unpriced. NEVER synthesise a floor.
 4. PER-PROVIDER attribution is mandatory. Today the question "which provider did we spend that
    on" is UNANSWERABLE from the gateway; that alone blocks the operator's capping decision.

ALSO CORRECTED: opencode's per-session accounting (GET /api/session) is REAL but EPHEMERAL —
verified 2026-08-02, no server is listening and no cost record persists anywhere under
~/.local/share/opencode. So this ticket is NOT "query opencode for the number"; it is INGEST
CONTINUOUSLY, because the ground truth only exists while a session lives.

ACCEPTANCE: a spend record that attributes cost PER PROVIDER, sourced from the provider's own
number where available, with unpriced calls counted as UNKNOWN rather than estimated — and a
fail-on-revert test proving a synthesised floor can never reappear.
