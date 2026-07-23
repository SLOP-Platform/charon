# WORKLOOP-INTEGRITY-STACK-SPIKE — Review Log

## Ticket
WORKLOOP-INTEGRITY-STACK-SPIKE: R0 lead-lens verdict (attempt 3, 2026-07-23 →
fresh session — re-briefed again after attempt 2 / PR #172 was bounced narrow)

## What was done (vs attempt 2 / PR #172)

Attempt 2 (PR #172) was bounced narrow with a single specific complaint:
**2 of 4 verdicts violated adopt-first ranking** — `ao` §1.3 ranked
"Hand-rolled thin orchestrator (~200 LOC)" #1 above `adnanh/webhook` +
Windmill, and `Archon` §4.3 ranked "Hand-rolled Python approval gate
(~200 LOC)" #1 above `pydantic`/`cerberus`. Ranking a hand-roll #1
before every adopt option is executed-and-disproven is auto-reject
drift (AP-5/AP-7, `HAND-ROLL-IS-NEVER-THE-DEFAULT`). The Omnigent +
Windmill verdicts were already correctly adopt-led and were left
unchanged.

Attempt 3 is NARROW: re-execute the two demoted adopt candidates, and
land each in a separate commit (EVAL-REGISTRY provenance).

**Executed adopt-candidate trials (2 layers, 2 sub-trials each):**

- **`adnanh/webhook` (ao seam, §1.4)** — built `webhook 2.8.3` Go
  binary on 4-LOM (12.9 MB, MIT, ~3s build). Wired a single hook
  (`ci-fail-retrigger`) against a scratch `git init` repo, with
  `value` trigger-rule (ref=`refs/heads/main`), command-execution
  on match, and a separate `payload-hmac-sha1` trigger-rule for the
  HMAC sub-trial. Receiver was a `python3 BaseHTTPRequestHandler` on
  `:9090` that logs every request and treats `/retrigger` as the
  fan-out target. 4 sub-trials:
  - Trial 1 (PASS, rc=0): push to main, build passes, no re-trigger.
  - Trial 2 (FAIL, rc=7): push to main, build fails, re-trigger fires
    via `POST /retrigger {reason: CI_FAIL, after: ...}`. Receiver
    logged it.
  - Trial 3 (wrong ref): push to `refs/heads/side`, trigger-rule
    rejected with "Hook rules were not satisfied."; `ci-gate.log`
    unchanged (still 7 lines), `retrigger.log` unchanged (still 1
    line).
  - Trial 4 (HMAC): push to main with valid `X-Hub-Signature` →
    "evaluated-hmac"; push with wrong secret → 500 "Error occurred
    while evaluating hook rules." + "invalid payload signatures
    [6a75af1e...]" in webhook log.

- **`pydantic` (Archon approval-gate seam, §4.4)** — `pydantic 2.13.4`
  (MIT, preinstalled on 4-LOM). Wrote `TicketFrontmatter(BaseModel)`
  with `Literal` tier, `pattern`-checked branch, and 2 custom
  `field_validator`s (`owns` non-empty, `work_class` in
  `WORK_CLASSES` taxonomy). Plus `cerberus 1.3.8` (ISC, installed
  via `pip3 install --break-system-packages`) with a dict-based
  schema mirroring the same intent. 5 fixtures:
  - `fx_valid.yaml` → ALLOW (both engines).
  - `fx_missing_field.yaml` (no `branch`) → DENY (both engines).
  - `fx_bad_type.yaml` (`tier=999`, `owns: src/charon/foo.py`) →
    DENY (both engines; both `tier` and `owns` errors caught).
  - `fx_bad_workclass.yaml` (`work_class: not-a-real-class`) →
    DENY (both engines).
  - `fx_money_no_test.yaml` (money-path without test in owns) →
    ASK (both engines; soft policy fail, schema OK).

**Adopt-first re-ranking applied (corrected attempt-2):**
- ao seam §1.3: adnanh/webhook LEADS (ADOPT, EXECUTED), Windmill
  second, hand-roll moved to after-adopt-disproven fallback.
- Archon seam §4.3: pydantic LEADS (ADOPT, EXECUTED), cerberus
  second (ADOPT, EXECUTED, alternate), Windmill third, hand-roll
  moved to after-adopt-disproven fallback.
- The other two layers (Omnigent, Windmill) and the methodology
  patterns (§5) are UNCHANGED from attempt 2 — their adopt-first
  ranking was already correct.

**Corrections to attempt 2 (the bounce reasons):**
| Attempt 2 verdict | Attempt 3 verdict | Executed evidence |
|---|---|---|
| ao §1.3: hand-roll #1, adnanh/webhook #2 | ao §1.3: adnanh/webhook #1 (EXECUTED), hand-roll after-adopt-disproven fallback | §1.4 — 4 sub-trials, end-to-end |
| Archon §4.3: hand-roll #1, pydantic/cerberus buried at #3 | Archon §4.3: pydantic #1 (EXECUTED), cerberus #2 (EXECUTED, alternate), hand-roll after-adopt-disproven fallback | §4.4 — 5 fixtures, tri-state verdict matrix |

**EVAL-REGISTRY provenance (per the launcher's "land each... in a
SEPARATE commit" rule):** The two new ADOPT rows for the EVAL-REGISTRY
landed in TWO separate commits:
- Commit `89320e6` (ao seam): adnanh/webhook ADOPT row + the ao
  row's updated evidence-link.
- Commit `d89a0ef` (Archon seam): pydantic ADOPT row + cerberus
  ADOPT row + the Archon row's updated evidence-link.

## Decisions taken (none escalated to operator)
- Wrote trial transcripts as fenced code blocks in the verdict doc
  (not screenshots) for grep-ability and review reproducibility —
  same as attempt 2.
- pydantic is the LEAD validator (type-hint ergonomics), cerberus is
  the ALTERNATE (lighter-weight dict schema). Both are ADOPT, with
  the WLS-4b ticket's choice between them made at build time.
- The hand-roll stays in §4.3 / §1.3 as the after-adopt-disproven
  fallback, not the leading recommendation. This is the
  HARD-REQUIRED fix per `[[no-rig-as-product-adopt-dont-handroll]]`
  + AP-5/AP-7.
- The `owns:`-line constraint held: only
  `fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md` was edited. The
  EVAL-REGISTRY backfill (§9 blocker in the verdict doc) is left for
  a follow-up `WLS-REG` ticket per the launcher's REVIEW NOTE rule.

## Gate / verification
- `git diff --name-only master...HEAD` → single file in `owns:`.
- File is `fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md` (matches
  ticket's `owns:` line exactly).
- This is a docs-only deliverable; no product code, no test code,
  no `src/` or `tests/` edits.
- No gate run needed for a state-doc-only change (the launcher's
  gate targets product code; `fleet/state/*.md` is operator review
  material).
- Two SEPARATE commits on `feat/workloop-stack-spike-run`:
  - `89320e6 design(workloop-integrity): re-rank ao seam adopt-first`
  - `d89a0ef design(workloop-integrity): re-rank Archon approval-gate seam adopt-first`

## What the operator should review
1. The two re-ranked verdicts (§1.3 / §4.3 of the verdict doc) and
   the integrated plan (§6).
2. The two executed adopt-candidate trials (§1.4 for adnanh/webhook;
   §4.4 for pydantic + cerberus) — these are the bounce-fix evidence.
3. The two NEW ADOPT rows in the §9 EVAL-REGISTRY table
   (adnanh/webhook, pydantic, cerberus) — needs a follow-up
   `WLS-REG: backfill-workloop-spike-rows` ticket to land them in
   `fleet/state/EVAL-REGISTRY.md` (this ticket's `owns:` line is
   the verdict doc only).
4. The four honest open questions (§8) — sequencing decisions the
   operator should make.

## Provenance
- Trials executed: 2026-07-23 on 4-LOM (10.0.1.60, primary). 4-LOM
  has Go 1.23.4, Docker 29.6.0, pydantic 2.13.4 preinstalled.
- Re-brief: 2026-07-23 (after attempt 2 / PR #172 was bounced
  narrow).
- Evidence base: `fleet/state/WORKLOOP-INTEGRITY-RESEARCH.md`
  (2026-07-22, 23 sources, 25 claims 3-vote-verified).
- Trial artifacts: `/tmp/wltrial/{transcript,hooks*.json,ci-gate.sh,
  receiver/server.py,pydtrial/dod_schema.py,fx_*.yaml}` on 4-LOM.
