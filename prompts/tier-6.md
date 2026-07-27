De-hardwire the fleet launcher so it resolves a concrete Anthropic model from tier config.
Canonical tier for this ticket: **high** (mapped to fleet `opus`). Depends on TIER-3
(merged): `charon tier resolve <tier> --executor anthropic` returns a concrete model name.
Read `/home/stack/charon-private/fleet/DTC-tier-abstraction.md` §"Fleet consumption" (the
`fleet-droid.sh` block) and the decision "the fleet keeps its Anthropic executor; only the
engine consumes multi-provider pools" FIRST, plus the existing
`/home/stack/charon-private/fleet/fleet-droid.sh` (the current arg parse + `MODEL="$TIER"`
and the `claude -p --model "$MODEL"` launch).

GOAL: Widen the arg allowlist to canonical + legacy tiers; set
`MODEL=$(charon tier resolve … --executor anthropic)` with a `|| MODEL="$TIER"` fallback.

DESIGN ANCHORS (cite in your review note):
- `claude -p` speaks the Anthropic Messages API; the gateway is OpenAI-only. So the fleet path
  does NOT route through the gateway — it resolves tier→concrete Anthropic model NAME via a
  config lookup (`charon tier resolve --executor anthropic`). No Anthropic↔OpenAI shim.
- Exact pattern from the design:
    opus|sonnet|haiku|low|med|high) TIER="$1"; shift;;       # arg allowlist widened
    MODEL="$(charon tier resolve "$TIER" --executor anthropic)" || MODEL="$TIER"
    ...
    claude -p --model "$MODEL" --dangerously-skip-permissions "$prompt"
- `resolve … --executor anthropic` returns the cheapest live tier member whose provider is
  Anthropic-API-runnable; `|| MODEL="$TIER"` keeps half-migrated setups working (legacy
  `opus/sonnet/haiku` still launch unchanged when `tiers.json` is absent).

BUILD:
- /home/stack/charon-private/fleet/fleet-droid.sh — widen the tier-arg allowlist to accept
  canonical (`low|med|high`) AND legacy (`opus|sonnet|haiku`); replace `MODEL="$TIER"` with
  the `charon tier resolve … --executor anthropic` lookup plus the `|| MODEL="$TIER"`
  fallback. Leave the rest of the launch/claim flow intact. Verify a dry launch resolves a
  concrete model for a canonical tier and falls back cleanly when config is absent.

CONSTRAINTS: own ONLY the file in your board ticket's `owns:` line
(/home/stack/charon-private/fleet/fleet-droid.sh) — nothing else. fleet-droid.sh already
exists: EDIT it. Do NOT touch claim.sh (TIER-5) or any Charon source. Same wave as
TIER-4/5/7 (disjoint files). If your work needs a file outside `owns:`, STOP and report it
with a one-line reason. Fleet shell script — keep it POSIX-bash, no new deps. No secrets.
Conventional commits. Write your review note as `docs/review-log/TIER-6.md` in the Charon
repo (NEVER the shared `docs/REVIEW-LOG.md`). Commit ALL work on your branch and STOP — do
NOT push, do NOT open a PR, do NOT run submit.sh; the launcher publishes after you exit.

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
