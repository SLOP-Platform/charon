Harden CI / supply-chain per the 2026-06-27 fragility audit (THEME 8). Read the existing
workflows in .github/workflows/ (ci.yml, heavy.yml, release.yml, windows-exe.yml) and
pyproject.toml FIRST. These run on a single self-hosted [self-hosted, 4-lom] runner pool.

FIX (each is independent; keep all existing behavior green):
1. **Job timeouts + concurrency** — add `timeout-minutes:` to EVERY job in ci.yml, heavy.yml,
   release.yml, windows-exe.yml (a wedged step otherwise holds the only runner up to 6h).
   Add to ci.yml: `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` so
   rapid pushes auto-cancel stale runs instead of serializing.
2. **SHA-pin windows-exe.yml** — it uses floating `@v4`/`@v5` action tags while every other
   workflow SHA-pins; this is the release lane that produces the distributed charon.exe. Pin
   each `uses:` to the same commit SHAs the other workflows already use.
3. **Fast-gate wheel/import smoke** — the standalone-wheel (INV-B6) + image smoke run only in
   heavy.yml's weekly cron, so a PR breaking the wheel merges green and is caught ≤7 days
   later. Add to ci.yml's gate (or a fast parallel job), triggered on src/packaging changes:
   `python -m build --wheel` then install it into a CLEAN venv and import `charon` + run a
   trivial CLI smoke. Keep it fast.
4. **mypy scope** — pyproject.toml `[tool.mypy]` has `files=[src/charon]` + `follow_imports=skip`,
   so tools/ and tests/ are untyped and cross-module errors are masked. Expand `files` to
   include tools/ and tests/, drop `follow_imports=skip` (fix or `# type: ignore` any fallout
   minimally — do not silence broadly).
5. **Wire the new gates** — add gate steps that run `python3 tools/render_review_log.py --check`
   (fails if the REVIEW-LOG rollup is stale vs fragments) and `python3 tools/check_decisions.py
   --check` (the decision-register lint from FB6, which is merged before this ticket). Both must
   be RED-on-violation.
6. **check_version edge (LOW)** — ensure check_version.py / the windows-exe tag-match actually
   fails when the package is absent or the tag doesn't match (today it can pass vacuously);
   tighten if trivially in scope of the workflow, else note it in the PR body.

CONSTRAINTS: own ONLY the files in board/FB5.md `owns:` (the four workflow files + pyproject.toml)
— nothing else. Do not touch tools/check_decisions.py or render_review_log.py (just CALL them).
Gate green every commit. Write your review note as docs/review-log/FB5.md. Conventional commits.
Open a DRAFT PR base=master; do NOT merge.

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
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
